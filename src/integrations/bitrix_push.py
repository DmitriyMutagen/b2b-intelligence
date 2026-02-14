#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  B2B Intelligence Platform — Bitrix24 Push Module
  Интеллектуальная собственность АО «Арагант Групп»
  Copyright (c) 2024-2026 АО «Арагант Групп». Все права защищены.
═══════════════════════════════════════════════════════════════════

Push обогащённых лидов В Bitrix24 CRM.
Создаёт/обновляет контакты, лиды, компании со всеми полями.
Прикрепляет AI-досье и КП.

Запуск: python src/integrations/bitrix_push.py [--limit N] [--dry-run]
"""
import os
import sys
import json
import time
import requests
import argparse
from typing import Optional, Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from sqlalchemy.orm import Session
from src.database import engine
from src.database.models import Company, Contact, Person, Intelligence


WEBHOOK_URL = os.getenv("BITRIX24_WEBHOOK_URL", "").rstrip("/")
if not WEBHOOK_URL:
    print("❌ BITRIX24_WEBHOOK_URL не настроен в .env")
    sys.exit(1)


def bitrix_call(method: str, params: dict = None) -> dict:
    """Call Bitrix24 REST API."""
    url = f"{WEBHOOK_URL}/{method}.json"
    try:
        resp = requests.post(url, json=params or {}, timeout=15)
        data = resp.json()
        if "error" in data:
            print(f"  ⚠️ Bitrix error: {data['error_description']}")
        return data
    except Exception as e:
        print(f"  ❌ Bitrix API error: {e}")
        return {"error": str(e)}


def find_or_create_company(company: Company) -> Optional[int]:
    """Find existing company in Bitrix24 or create new one."""
    # Search by name
    result = bitrix_call("crm.company.list", {
        "filter": {"TITLE": company.name},
        "select": ["ID", "TITLE"]
    })
    
    if result.get("result"):
        return int(result["result"][0]["ID"])
    
    # Create new company
    fields = {
        "TITLE": company.name,
        "COMPANY_TYPE": "CUSTOMER",
        "INDUSTRY": "MANUFACTURING",
        "COMMENTS": f"[B2B Intelligence] Score: {company.lead_score}/100",
    }
    
    if company.website:
        fields["WEB"] = [{"VALUE": company.website, "VALUE_TYPE": "WORK"}]
    if company.inn:
        fields["UF_CRM_INN"] = company.inn
    
    result = bitrix_call("crm.company.add", {"fields": fields})
    return result.get("result")


def create_contact_in_bitrix(person: Person, company_id: int, contacts: List[Contact]) -> Optional[int]:
    """Create a contact in Bitrix24."""
    name_parts = (person.full_name or "").split()
    
    fields = {
        "NAME": name_parts[0] if name_parts else "Неизвестно",
        "LAST_NAME": " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
        "POST": person.role or "",
        "COMPANY_ID": company_id,
        "SOURCE_ID": "WEB",
        "COMMENTS": f"[B2B Intelligence] Источник: {person.source or 'enrichment'}",
    }
    
    # Add phones
    phones = [c for c in contacts if c.type in ("phone", "tel")]
    if phones:
        fields["PHONE"] = [{"VALUE": p.value, "VALUE_TYPE": "WORK"} for p in phones]
    
    # Add emails
    emails = [c for c in contacts if c.type == "email"]
    if emails:
        fields["EMAIL"] = [{"VALUE": e.value, "VALUE_TYPE": "WORK"} for e in emails]
    
    result = bitrix_call("crm.contact.add", {"fields": fields})
    return result.get("result")


def create_lead_in_bitrix(company: Company, company_id: int, contact_id: int,
                           intelligence: Optional[Intelligence], session: Session) -> Optional[int]:
    """Create a lead in Bitrix24 with AI analysis data."""
    
    # Build description from AI intelligence
    description_parts = [f"🏢 {company.name}"]
    
    if company.website:
        description_parts.append(f"🌐 Сайт: {company.website}")
    if company.inn:
        description_parts.append(f"📋 ИНН: {company.inn}")
    if company.revenue_total:
        description_parts.append(f"💰 Выручка: {company.revenue_total:,.0f} ₽")
    if company.wb_present:
        description_parts.append("🛒 Wildberries: Да")
    if company.ozon_present:
        description_parts.append("🛒 Ozon: Да")
    
    # AI Intelligence
    if intelligence:
        description_parts.append("\n━━━ AI ДОСЬЕ ━━━")
        if intelligence.summary:
            description_parts.append(f"📝 {intelligence.summary}")
        if intelligence.approach_strategy:
            description_parts.append(f"💡 Стратегия: {intelligence.approach_strategy}")
        if intelligence.pain_points:
            try:
                pains = json.loads(intelligence.pain_points)
                description_parts.append(f"🎯 Боли: {', '.join(pains[:3])}")
            except: pass
        if intelligence.brand_dna:
            try:
                dna = json.loads(intelligence.brand_dna)
                if dna.get("strengths"):
                    description_parts.append(f"💪 Сильные стороны: {', '.join(dna['strengths'][:3])}")
                if dna.get("competitors"):
                    description_parts.append(f"⚔️ Конкуренты: {', '.join(dna['competitors'][:3])}")
                if dna.get("products"):
                    description_parts.append(f"📦 Продукты: {', '.join(dna['products'][:5])}")
            except: pass
    
    description = "\n".join(description_parts)
    
    # Lead score → priority
    if company.lead_score >= 70:
        priority = "HIGH"
    elif company.lead_score >= 40:
        priority = "NORMAL"
    else:
        priority = "LOW"
    
    fields = {
        "TITLE": f"[B2B AI] {company.name} — контрактное производство",
        "COMPANY_ID": company_id,
        "CONTACT_ID": contact_id,
        "STATUS_ID": "NEW",
        "SOURCE_ID": "WEB",
        "PRIORITY_ID": priority,
        "COMMENTS": description,
        "UF_CRM_LEAD_SCORE": str(company.lead_score),
    }
    
    # Contacts
    contacts = session.query(Contact).filter_by(company_id=company.id).all()
    phones = [c for c in contacts if c.type in ("phone", "tel")]
    emails = [c for c in contacts if c.type == "email"]
    
    if phones:
        fields["PHONE"] = [{"VALUE": p.value, "VALUE_TYPE": "WORK"} for p in phones[:3]]
    if emails:
        fields["EMAIL"] = [{"VALUE": e.value, "VALUE_TYPE": "WORK"} for e in emails[:3]]
    
    if company.website:
        fields["WEB"] = [{"VALUE": company.website, "VALUE_TYPE": "WORK"}]
    
    result = bitrix_call("crm.lead.add", {"fields": fields})
    return result.get("result")


def push_to_bitrix(limit: int = 50, dry_run: bool = False):
    """Push enriched companies to Bitrix24."""
    session = Session(engine)
    
    # Get top scored enriched companies
    companies = session.query(Company).filter(
        Company.lead_score > 0
    ).order_by(Company.lead_score.desc()).limit(limit).all()
    
    print(f"\n{'='*70}")
    print(f"  🔄 PUSH В BITRIX24 — {len(companies)} компаний")
    print(f"  {'DRY RUN — без записи' if dry_run else 'LIVE — запись в CRM'}")
    print(f"{'='*70}")
    
    stats = {"companies": 0, "contacts": 0, "leads": 0, "errors": 0}
    
    for idx, company in enumerate(companies, 1):
        persons = session.query(Person).filter_by(company_id=company.id).all()
        contacts = session.query(Contact).filter_by(company_id=company.id).all()
        intel = session.query(Intelligence).filter_by(company_id=company.id).first()
        
        print(f"\n[{idx}/{len(companies)}] {company.name} (score={company.lead_score})")
        print(f"  👤 {len(persons)} ЛПР, 📇 {len(contacts)} контактов, {'🧠' if intel else '—'} AI")
        
        if dry_run:
            print(f"  [DRY] Пропуск")
            continue
        
        # 1. Create/find company
        bx_company_id = find_or_create_company(company)
        if bx_company_id:
            stats["companies"] += 1
            print(f"  ✅ Компания #{bx_company_id}")
        else:
            stats["errors"] += 1
            continue
        
        # 2. Create contacts
        bx_contact_id = None
        for person in persons[:3]:  # Max 3 contacts
            cid = create_contact_in_bitrix(person, bx_company_id, contacts)
            if cid:
                stats["contacts"] += 1
                if not bx_contact_id:
                    bx_contact_id = cid
                print(f"  ✅ Контакт #{cid}: {person.full_name}")
        
        # 3. Create lead
        lid = create_lead_in_bitrix(company, bx_company_id, bx_contact_id, intel, session)
        if lid:
            stats["leads"] += 1
            print(f"  ✅ Лид #{lid}")
        
        time.sleep(0.5)  # Rate limiting
    
    # Summary
    print(f"\n{'='*70}")
    print(f"  📊 ИТОГИ PUSH В BITRIX24")
    print(f"{'='*70}")
    print(f"  Компаний:  {stats['companies']}")
    print(f"  Контактов: {stats['contacts']}")
    print(f"  Лидов:     {stats['leads']}")
    print(f"  Ошибок:    {stats['errors']}")
    print(f"{'='*70}")
    
    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push leads to Bitrix24")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", help="Test without writing to CRM")
    args = parser.parse_args()
    
    push_to_bitrix(limit=args.limit, dry_run=args.dry_run)
