#!/usr/bin/env python3
"""
Глубокое обогащение ВСЕХ компаний из множества источников:
1. DuckDuckGo Search → найти сайт компании
2. Crawl сайта → emails, phones, socials, INN
3. RusProfile → ИНН, руководитель, юр. лицо
4. Поиск ЛПР (директор, учредитель)
5. Lead scoring пересчёт

Запуск: python scripts/deep_enrich.py [--limit N] [--skip-search] [--skip-crawl]
"""
import os
import sys
import re
import json
import time
import argparse
from urllib.parse import quote_plus, urljoin, urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from src.database import engine
from src.database.models import Base, Company, Contact, Person, Intelligence
from src.ai.brain import calculate_lead_score
from src.recon.web_crawler import crawl_website

Base.metadata.create_all(engine)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8',
}

# Домены которые не являются сайтами компаний
SKIP_DOMAINS = {
    'yandex.', 'google.', 'wildberries.', 'ozon.', 'avito.', 'ya.ru',
    'youtube.', 'vk.com', 'instagram.', 'facebook.', 'wikipedia.',
    't.me', 'market.yandex', 'hh.ru', '2gis.', 'dzen.ru', 'zen.yandex',
    'ok.ru', 'mail.ru', 'bing.', 'rusprofile.', 'duckduckgo.',
    'pinterest.', 'twitter.', 'x.com', 'reddit.', 'tiktok.',
    'apple.com', 'play.google', 'apps.apple', 'amazonaws.',
    'livejournal.', 'rutube.', 'irecommend.', 'otzovik.',
}


# ══════════════════════════════════════════════════════════════
#  ИСТОЧНИК 1: Поиск сайта через DuckDuckGo HTML
# ══════════════════════════════════════════════════════════════

def search_company_website(company_name: str, niche: str = "спортивное питание") -> str | None:
    """Search for company website using DuckDuckGo HTML."""
    queries = [
        f"{company_name} {niche} официальный сайт",
        f'"{company_name}" производитель',
    ]
    
    for query in queries:
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            resp = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36',
            }, timeout=10)
            
            if resp.status_code != 200:
                continue
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # DuckDuckGo HTML results have class "result__url"
            for result_link in soup.select('.result__url'):
                href = result_link.get('href', '') or result_link.get_text(strip=True)
                if not href:
                    continue
                
                # Clean URL
                if not href.startswith('http'):
                    href = 'https://' + href.strip()
                
                parsed = urlparse(href)
                domain = parsed.netloc.lower().lstrip('www.')
                
                if any(s in domain for s in SKIP_DOMAINS):
                    continue
                
                if '.' in domain and len(domain) > 3:
                    return f"https://{parsed.netloc}"
            
            # Try result__a links as fallback
            for a_tag in soup.select('.result__a'):
                href = a_tag.get('href', '')
                if not href or 'duckduckgo' in href:
                    continue
                
                # DDG wraps URLs, extract real one
                if '//duckduckgo.com/l/' in href:
                    import urllib.parse
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    if 'uddg' in qs:
                        href = qs['uddg'][0]
                
                parsed = urlparse(href)
                domain = parsed.netloc.lower().lstrip('www.')
                
                if any(s in domain for s in SKIP_DOMAINS):
                    continue
                
                if '.' in domain and len(domain) > 3:
                    return f"https://{parsed.netloc}"
            
            time.sleep(1.5)
            
        except Exception as e:
            continue
    
    return None


# ══════════════════════════════════════════════════════════════
#  ИСТОЧНИК 2: RusProfile — ИНН, руководство, юр. форма
# ══════════════════════════════════════════════════════════════

def search_rusprofile(company_name: str) -> dict:
    """Search RusProfile.ru for company legal info, director, INN."""
    result = {"inn": None, "director": None, "legal_form": None, "address": None, "ogrn": None}
    
    try:
        search_url = f"https://www.rusprofile.ru/search?query={quote_plus(company_name)}&type=ul"
        resp = requests.get(search_url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return result
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        
        # Extract INN from search results page
        inn_match = re.search(r'ИНН\s*:?\s*(\d{10,12})', text)
        if inn_match:
            result["inn"] = inn_match.group(1)
        
        # Extract OGRN
        ogrn_match = re.search(r'ОГРН\s*:?\s*(\d{13,15})', text)
        if ogrn_match:
            result["ogrn"] = ogrn_match.group(1)
        
        # Extract director/head
        dir_patterns = [
            re.compile(r'(?:Руководитель|Директор|Генеральный директор|ИП)\s*[-—:,]?\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)', re.IGNORECASE),
        ]
        for pat in dir_patterns:
            match = pat.search(text)
            if match:
                name = match.group(1).strip()
                if len(name) > 5 and len(name) < 60:
                    result["director"] = name
                    break
        
        # Extract address
        addr_match = re.search(r'(\d{6},?\s*(?:г\.|Москва|Санкт-Петербург|обл\.)[^.]{10,120})', text)
        if addr_match:
            result["address"] = addr_match.group(1).strip()[:200]
        
    except Exception:
        pass
    
    return result


# ══════════════════════════════════════════════════════════════
#  DEEP RESEARCH: поиск максимума информации
# ══════════════════════════════════════════════════════════════

def deep_research_company(company_name: str, inn: str = None) -> dict:
    """Full deep research on a company — search everything available."""
    info = {
        "emails": [], "phones": [], "socials": {},
        "persons": [], "address": None, "description": None,
        "inn": inn, "ogrn": None, "website": None,
    }
    
    # 1. RusProfile
    rp = search_rusprofile(company_name)
    if rp["inn"]:
        info["inn"] = rp["inn"]
    if rp["ogrn"]:
        info["ogrn"] = rp["ogrn"]
    if rp["director"]:
        info["persons"].append({"full_name": rp["director"], "role": "Генеральный директор", "source": "rusprofile"})
    if rp["address"]:
        info["address"] = rp["address"]
    
    time.sleep(0.5)
    
    # 2. DuckDuckGo: find website
    website = search_company_website(company_name)
    if website:
        info["website"] = website
        # 3. Crawl the website deeply
        try:
            crawl_result = crawl_website(website, max_depth=3, max_pages=20)
            data = crawl_result.to_dict()
            info["emails"].extend(data.get("emails", []))
            info["phones"].extend(data.get("phones", []))
            info["socials"].update(data.get("social_links", {}))
            if data.get("inn") and not info["inn"]:
                info["inn"] = data["inn"]
            if data.get("description"):
                info["description"] = data["description"]
        except Exception as e:
            pass
    
    time.sleep(0.3)
    
    # 4. Search for more contacts/LPR via DuckDuckGo
    try:
        query = f'"{company_name}" директор OR руководитель OR email OR телефон'
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        resp = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
        }, timeout=10)
        if resp.status_code == 200:
            text = resp.text
            # Extract emails
            email_re = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
            found_emails = email_re.findall(text)
            for em in found_emails:
                if not em.endswith(('.png', '.jpg', '.gif')) and 'duckduckgo' not in em:
                    info["emails"].append(em.lower())
            
            # Extract Russian full names near role keywords
            soup = BeautifulSoup(text, 'html.parser')
            page_text = soup.get_text(separator=' ', strip=True)
            
            name_pat = re.compile(
                r'(?:директор|руководитель|основатель|CEO|владелец|учредитель)'
                r'\s*[-—:,]?\s*'
                r'([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)',
                re.IGNORECASE
            )
            for m in name_pat.finditer(page_text):
                fn = m.group(1).strip()
                if 5 < len(fn) < 60 and not any(p["full_name"] == fn for p in info["persons"]):
                    role = "Руководство"
                    ctx = page_text[max(0, m.start()-30):m.start()].lower()
                    if 'генеральн' in ctx or 'ceo' in ctx: role = "Генеральный директор"
                    elif 'основат' in ctx or 'учредит' in ctx: role = "Основатель"
                    elif 'коммерч' in ctx: role = "Коммерческий директор"
                    info["persons"].append({"full_name": fn, "role": role, "source": "web_search"})
    except Exception:
        pass
    
    # Deduplicate
    info["emails"] = list(set(info["emails"]))[:10]
    info["phones"] = list(set(info["phones"]))[:10]
    info["persons"] = info["persons"][:5]
    
    return info


# ══════════════════════════════════════════════════════════════
#  SAVE TO DB
# ══════════════════════════════════════════════════════════════

def save_enrichment(session: Session, company: Company, info: dict):
    """Save deep research results to database."""
    added = 0
    
    # Website
    if info.get("website") and not company.website:
        company.website = info["website"]
    
    # INN
    if info.get("inn") and not company.inn:
        company.inn = info["inn"]
    
    # Emails
    for email in info.get("emails", []):
        if not session.query(Contact).filter_by(company_id=company.id, type="email", value=email).first():
            session.add(Contact(company_id=company.id, type="email", value=email, source="deep_research", label="Deep research"))
            added += 1
    
    # Phones
    for phone in info.get("phones", []):
        if not session.query(Contact).filter_by(company_id=company.id, type="phone", value=phone).first():
            session.add(Contact(company_id=company.id, type="phone", value=phone, source="deep_research", label="Deep research"))
            added += 1
    
    # Socials
    for platform, link in info.get("socials", {}).items():
        if not session.query(Contact).filter_by(company_id=company.id, type=platform, value=link).first():
            session.add(Contact(company_id=company.id, type=platform, value=link, source="deep_research"))
            added += 1
    
    # Address
    if info.get("address"):
        if not session.query(Contact).filter_by(company_id=company.id, type="address").first():
            session.add(Contact(company_id=company.id, type="address", value=info["address"], source="rusprofile", label="Юр. адрес"))
            added += 1
    
    # Persons (LPR)
    for p in info.get("persons", []):
        if not session.query(Person).filter_by(company_id=company.id, full_name=p["full_name"]).first():
            session.add(Person(company_id=company.id, full_name=p["full_name"], role=p["role"], source=p["source"]))
            added += 1
    
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


# ══════════════════════════════════════════════════════════════
#  MAIN PIPELINE
# ══════════════════════════════════════════════════════════════

def deep_enrich(limit: int = 672, skip_search: bool = False):
    """Full enrichment pipeline for all companies."""
    session = Session(engine)
    
    # Process companies without enrichment first, then those with partial data
    companies = session.query(Company).order_by(
        Company.lead_score.desc().nulls_last()
    ).limit(limit).all()
    
    total = len(companies)
    print(f"\n{'='*70}")
    print(f"  DEEP RESEARCH — {total} компаний")
    print(f"  Источники: DuckDuckGo, RusProfile, Web Crawling, LPR Search")
    print(f"{'='*70}")
    
    stats = {"total": 0, "websites": 0, "contacts": 0, "persons": 0, "inns": 0, "errors": 0}
    
    for idx, c in enumerate(companies, 1):
        had_website = bool(c.website)
        had_inn = bool(c.inn)
        existing_contacts = session.query(Contact).filter_by(company_id=c.id).count()
        existing_persons = session.query(Person).filter_by(company_id=c.id).count()
        
        # Skip fully enriched
        if had_website and had_inn and existing_contacts >= 3 and existing_persons >= 1:
            continue
        
        print(f"\n[{idx}/{total}] {c.name} (score={c.lead_score})")
        
        try:
            if skip_search and c.website:
                # Just crawl existing website
                info = {"emails": [], "phones": [], "socials": {}, "persons": [], "website": c.website}
                try:
                    result = crawl_website(c.website, max_depth=3, max_pages=20)
                    data = result.to_dict()
                    info["emails"] = data.get("emails", [])
                    info["phones"] = data.get("phones", [])
                    info["socials"] = data.get("social_links", {})
                except:
                    pass
            else:
                info = deep_research_company(c.name, c.inn)
            
            added = save_enrichment(session, c, info)
            stats["total"] += 1
            stats["contacts"] += added
            
            if info.get("website") and not had_website:
                stats["websites"] += 1
            if info.get("inn") and not had_inn:
                stats["inns"] += 1
            if info.get("persons"):
                stats["persons"] += len(info["persons"])
            
            # Print summary for this company
            e = ", ".join(info.get("emails", [])[:2]) or "—"
            p = ", ".join(info.get("phones", [])[:2]) or "—"
            w = info.get("website", "—") or "—"
            lpr = ", ".join(f'{x["full_name"]}' for x in info.get("persons", [])[:2]) or "—"
            inn = info.get("inn", "—") or "—"
            print(f"  🌐 {w}")
            print(f"  📧 {e} | 📞 {p}")
            print(f"  👤 {lpr} | 📋 ИНН: {inn}")
            
        except Exception as ex:
            print(f"  ❌ {ex}")
            stats["errors"] += 1
        
        # Commit every 5 companies
        if idx % 5 == 0:
            session.commit()
            print(f"\n  💾 Сохранено ({idx}/{total}) | "
                  f"сайтов: +{stats['websites']}, контактов: +{stats['contacts']}, "
                  f"ЛПР: +{stats['persons']}")
    
    session.commit()
    
    # ── Final Summary ──
    total_companies = session.query(Company).count()
    with_website = session.query(Company).filter(Company.website.isnot(None), Company.website != "").count()
    with_inn = session.query(Company).filter(Company.inn.isnot(None)).count()
    total_contacts = session.query(Contact).count()
    total_persons = session.query(Person).count()
    
    print(f"\n{'='*70}")
    print(f"  📊 ИТОГИ DEEP RESEARCH")
    print(f"{'='*70}")
    print(f"  Обработано:       {stats['total']}")
    print(f"  Сайтов найдено:   +{stats['websites']}")
    print(f"  Контактов:        +{stats['contacts']}")
    print(f"  ЛПР найдено:     +{stats['persons']}")
    print(f"  ИНН найдено:      +{stats['inns']}")
    print(f"  Ошибок:           {stats['errors']}")
    print(f"{'='*70}")
    print(f"  ВСЕГО В БД:")
    print(f"    Компаний:  {total_companies}")
    print(f"    С сайтом:  {with_website}")
    print(f"    С ИНН:     {with_inn}")
    print(f"    Контактов: {total_contacts}")
    print(f"    ЛПР:       {total_persons}")
    print(f"{'='*70}")
    
    # Top 15
    top = session.query(Company).order_by(Company.lead_score.desc()).limit(15).all()
    print(f"\n  🏆 ТОП-15:")
    for i, c in enumerate(top, 1):
        cc = session.query(Contact).filter_by(company_id=c.id).count()
        pc = session.query(Person).filter_by(company_id=c.id).count()
        site = "🌐" if c.website else "—"
        inn = "📋" if c.inn else "—"
        print(f"    {i:2d}. [{c.lead_score:3d}] {c.name[:30]:30s} rev={c.revenue_total or 0:>12,.0f}  {site} {inn}  📇{cc} 👤{pc}")
    
    session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deep research pipeline")
    parser.add_argument("--limit", type=int, default=672, help="Number of companies (default: all 672)")
    parser.add_argument("--skip-search", action="store_true", help="Skip web search, only crawl existing sites")
    args = parser.parse_args()
    
    deep_enrich(limit=args.limit, skip_search=args.skip_search)
