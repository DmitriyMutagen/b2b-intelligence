#!/usr/bin/env python3
"""
AI-powered Deep Enrichment с использованием Gemini API.
Для каждой компании: ищет информацию через Google Search (Grounding),
анализирует и извлекает структурированные данные.

Запуск: python scripts/ai_enrich.py [--limit N]
"""
import os
import sys
import json
import time
import argparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from sqlalchemy.orm import Session
from src.database import engine
from src.database.models import Base, Company, Contact, Person, Intelligence
from src.ai.brain import calculate_lead_score

Base.metadata.create_all(engine)

# Gemini API
import google.generativeai as genai

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)


def ai_research_company(company_name: str, existing_data: dict) -> dict:
    """Use Gemini to research a company and extract structured data."""
    
    model = genai.GenerativeModel("gemini-2.0-flash-exp")
    
    prompt = f"""Ты — бизнес-аналитик. Найди максимум информации о российской компании в сфере спортивного питания / БАД / здорового питания.

Компания: {company_name}
Имеющиеся данные: выручка={existing_data.get('revenue', 'неизвестно')}, маркетплейсы={'WB' if existing_data.get('wb') else ''} {'Ozon' if existing_data.get('ozon') else ''}, сайт={existing_data.get('website', 'неизвестно')}

НАЙДИ и верни в JSON формате:
{{
    "website": "официальный сайт компании (URL) или null",
    "inn": "ИНН компании (10-12 цифр) или null",
    "ogrn": "ОГРН или null",
    "description": "краткое описание компании (1-2 предложения)",
    "director": "ФИО генерального директора или null",
    "director_role": "должность директора",
    "founder": "ФИО основателя/учредителя или null",
    "address": "юридический адрес или null",
    "phone": "основной телефон или null",
    "email": "основной email или null",
    "telegram": "telegram канал/бот или null",
    "vk": "группа VK или null",
    "instagram": "instagram или null",
    "year_founded": "год основания или null",
    "employees_count": "примерное число сотрудников или null",
    "main_products": ["перечень основных продуктов/брендов"],
    "competitors": ["основные конкуренты"],
    "strengths": ["сильные стороны для B2B продаж"],
    "pain_points": ["возможные боли/потребности для B2B предложения"],
    "approach_strategy": "рекомендация по подходу к этой компании для B2B продаж"
}}

Отвечай ТОЛЬКО JSON, без markdown, без пояснений."""

    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Clean JSON from markdown blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        
        data = json.loads(text)
        return data
        
    except json.JSONDecodeError as e:
        print(f"    ⚠️ JSON parse error: {e}")
        return {}
    except Exception as e:
        print(f"    ❌ Gemini error: {e}")
        return {}


def save_ai_enrichment(session: Session, company: Company, data: dict) -> int:
    """Save AI enrichment results to database."""
    added = 0
    
    # Website
    if data.get("website") and not company.website:
        url = data["website"]
        if url.startswith("http") and "." in url:
            company.website = url
            added += 1
    
    # INN
    if data.get("inn") and not company.inn:
        inn = str(data["inn"]).strip()
        if inn.isdigit() and len(inn) in (10, 12):
            company.inn = inn
            added += 1
    
    # Director as Person
    if data.get("director"):
        director_name = data["director"]
        role = data.get("director_role", "Генеральный директор")
        if not session.query(Person).filter_by(company_id=company.id, full_name=director_name).first():
            session.add(Person(company_id=company.id, full_name=director_name, role=role, source="gemini_ai"))
            added += 1
    
    # Founder as Person
    if data.get("founder") and data.get("founder") != data.get("director"):
        if not session.query(Person).filter_by(company_id=company.id, full_name=data["founder"]).first():
            session.add(Person(company_id=company.id, full_name=data["founder"], role="Основатель", source="gemini_ai"))
            added += 1
    
    # Contacts
    contact_map = {
        "phone": ("phone", "Основной телефон"),
        "email": ("email", "Основной email"),
        "telegram": ("telegram", "Telegram"),
        "vk": ("vk", "VKontakte"),
        "instagram": ("instagram", "Instagram"),
        "address": ("address", "Юр. адрес"),
    }
    
    for field, (ctype, label) in contact_map.items():
        value = data.get(field)
        if value and str(value).lower() not in ("null", "none", ""):
            if not session.query(Contact).filter_by(company_id=company.id, type=ctype, value=str(value)).first():
                session.add(Contact(company_id=company.id, type=ctype, value=str(value), source="gemini_ai", label=label))
                added += 1
    
    # Intelligence (AI analysis)
    intel = session.query(Intelligence).filter_by(company_id=company.id).first()
    if not intel:
        intel = Intelligence(company_id=company.id)
        session.add(intel)
    
    if data.get("pain_points"):
        intel.pain_points = json.dumps(data["pain_points"], ensure_ascii=False)
    if data.get("strengths"):
        intel.brand_dna = json.dumps({"strengths": data["strengths"], "products": data.get("main_products", []), "competitors": data.get("competitors", [])}, ensure_ascii=False)
    if data.get("approach_strategy"):
        intel.approach_strategy = data["approach_strategy"]
    if data.get("description"):
        intel.summary = data["description"]
    
    # Re-score
    company_dict = {
        "name": company.name, "revenue_total": company.revenue_total,
        "sales_total": company.sales_total, "wb_present": company.wb_present,
        "ozon_present": company.ozon_present, "avg_price": company.avg_price,
        "website": company.website,
    }
    company.lead_score = calculate_lead_score(company_dict)
    company.enrichment_status = "enriched"
    
    return added


def ai_enrich(limit: int = 50):
    """AI-powered enrichment pipeline."""
    session = Session(engine)
    
    # Get companies ordered by lead score, prioritize those without intelligence
    companies = session.query(Company).outerjoin(Intelligence).filter(
        Intelligence.id.is_(None)
    ).order_by(Company.lead_score.desc()).limit(limit).all()
    
    if not companies:
        # All have intelligence, get those with lowest data
        companies = session.query(Company).order_by(Company.lead_score.desc()).limit(limit).all()
    
    total = len(companies)
    print(f"\n{'='*70}")
    print(f"  🤖 AI ENRICHMENT (Gemini) — {total} компаний")
    print(f"{'='*70}")
    
    stats = {"processed": 0, "contacts_added": 0, "persons_added": 0, "websites": 0, "inns": 0, "errors": 0}
    
    for idx, c in enumerate(companies, 1):
        print(f"\n[{idx}/{total}] {c.name} (score={c.lead_score})")
        
        existing = {
            "revenue": c.revenue_total, "wb": c.wb_present, "ozon": c.ozon_present,
            "website": c.website, "inn": c.inn,
        }
        
        data = ai_research_company(c.name, existing)
        
        if data:
            had_website = bool(c.website)
            had_inn = bool(c.inn)
            
            added = save_ai_enrichment(session, c, data)
            stats["processed"] += 1
            stats["contacts_added"] += added
            
            if data.get("director"):
                stats["persons_added"] += 1
            if not had_website and c.website:
                stats["websites"] += 1
            if not had_inn and c.inn:
                stats["inns"] += 1
            
            # Print summary
            d = data.get("director", "—")
            w = data.get("website", "—") or "—"
            desc = (data.get("description", "") or "")[:60]
            print(f"  👤 {d}")
            print(f"  🌐 {w}")
            print(f"  📝 {desc}...")
            if data.get("approach_strategy"):
                print(f"  💡 {data['approach_strategy'][:80]}...")
        else:
            stats["errors"] += 1
        
        # Rate limiting (Gemini free tier: 15 RPM)
        time.sleep(4)
        
        # Commit every 5
        if idx % 5 == 0:
            session.commit()
            print(f"\n  💾 Сохранено ({idx}/{total})")
    
    session.commit()
    
    # Summary
    total_contacts = session.query(Contact).count()
    total_persons = session.query(Person).count()
    total_intel = session.query(Intelligence).count()
    
    print(f"\n{'='*70}")
    print(f"  📊 ИТОГИ AI ENRICHMENT")
    print(f"{'='*70}")
    print(f"  Обработано:       {stats['processed']}")
    print(f"  Сайтов найдено:   +{stats['websites']}")
    print(f"  ИНН найдено:      +{stats['inns']}")
    print(f"  Контактов:        +{stats['contacts_added']}")
    print(f"  ЛПР:              +{stats['persons_added']}")
    print(f"  Ошибок:           {stats['errors']}")
    print(f"{'='*70}")
    print(f"  В БД: {total_contacts} контактов, {total_persons} ЛПР, {total_intel} AI-досье")
    print(f"{'='*70}")
    
    # Top 10
    top = session.query(Company).order_by(Company.lead_score.desc()).limit(10).all()
    print(f"\n  🏆 ТОП-10:")
    for i, c in enumerate(top, 1):
        cc = session.query(Contact).filter_by(company_id=c.id).count()
        pc = session.query(Person).filter_by(company_id=c.id).count()
        intel = session.query(Intelligence).filter_by(company_id=c.id).first()
        ai = "🧠" if intel else "—"
        print(f"    {i:2d}. [{c.lead_score:3d}] {c.name[:30]:30s} {ai} 📇{cc} 👤{pc}")
    
    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI enrichment pipeline")
    parser.add_argument("--limit", type=int, default=30, help="Companies to process (default: 30)")
    args = parser.parse_args()
    
    ai_enrich(limit=args.limit)
