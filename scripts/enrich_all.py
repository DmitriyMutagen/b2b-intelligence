#!/usr/bin/env python3
"""
Массовое обогащение компаний:
1. Lead scoring (rule-based) для ВСЕХ компаний
2. Web crawling сайтов → извлечение контактов (email, phone, socials)
3. Сохранение контактов в таблицу contacts

Запуск: python scripts/enrich_all.py
"""
import os
import sys
import time

# Ensure project root is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from sqlalchemy.orm import Session
from src.database import engine
from src.database.models import Base, Company, Contact
from src.ai.brain import calculate_lead_score
from src.recon.web_crawler import crawl_website

# Create tables if needed
Base.metadata.create_all(engine)


def enrich_lead_scores(session: Session):
    """Phase 1: Calculate lead score for all companies."""
    companies = session.query(Company).filter(
        Company.enrichment_status.in_(["new", None, ""])
    ).order_by(Company.revenue_total.desc().nulls_last()).all()

    print(f"\n{'='*60}")
    print(f"ФАЗА 1: Lead Scoring — {len(companies)} компаний")
    print(f"{'='*60}")

    scored = 0
    for c in companies:
        company_dict = {
            "name": c.name,
            "revenue_total": c.revenue_total,
            "sales_total": c.sales_total,
            "wb_present": c.wb_present,
            "ozon_present": c.ozon_present,
            "avg_price": c.avg_price,
            "website": c.website,
        }
        score = calculate_lead_score(company_dict)
        c.lead_score = score
        c.enrichment_status = "scored"
        scored += 1

        if scored % 100 == 0:
            print(f"  ...scored {scored}/{len(companies)}")
            session.commit()

    session.commit()
    print(f"✅ Lead scoring завершён: {scored} компаний обработано")

    # Show top 10
    top = session.query(Company).order_by(Company.lead_score.desc()).limit(10).all()
    print(f"\n🏆 ТОП-10 по lead score:")
    for i, c in enumerate(top, 1):
        print(f"  {i:2d}. [{c.lead_score:3d}] {c.name} — выручка: {c.revenue_total or 0:,.0f}")


def enrich_web_crawl(session: Session, limit: int = 100):
    """Phase 2: Crawl websites for contact info."""
    # Get companies with websites that haven't been crawled yet
    companies = session.query(Company).filter(
        Company.website.isnot(None),
        Company.website != "",
        Company.enrichment_status.in_(["scored", "new", None])
    ).order_by(Company.lead_score.desc().nulls_last()).limit(limit).all()

    print(f"\n{'='*60}")
    print(f"ФАЗА 2: Web Crawling — {len(companies)} компаний с сайтами")
    print(f"{'='*60}")

    if not companies:
        # Check if there are websites at all
        total_with_site = session.query(Company).filter(
            Company.website.isnot(None), Company.website != ""
        ).count()
        print(f"  Компаний с сайтами в БД: {total_with_site}")
        if total_with_site == 0:
            print("  ⚠️  Ни у одной компании нет поля website в БД.")
            print("  Данные Website берутся из колонки 'Website' в Excel файле.")
        return

    crawled = 0
    contacts_found = 0
    errors = 0

    for c in companies:
        url = c.website.strip()
        if not url:
            continue

        print(f"\n  [{crawled+1}/{len(companies)}] {c.name}: {url}")

        try:
            result = crawl_website(url, max_depth=2, max_pages=10)
            data = result.to_dict()

            # Save contacts
            for email in data.get("emails", []):
                existing = session.query(Contact).filter_by(
                    company_id=c.id, type="email", value=email
                ).first()
                if not existing:
                    session.add(Contact(
                        company_id=c.id, type="email", value=email,
                        source="web_crawl", label="С сайта"
                    ))
                    contacts_found += 1

            for phone in data.get("phones", []):
                existing = session.query(Contact).filter_by(
                    company_id=c.id, type="phone", value=phone
                ).first()
                if not existing:
                    session.add(Contact(
                        company_id=c.id, type="phone", value=phone,
                        source="web_crawl", label="С сайта"
                    ))
                    contacts_found += 1

            for platform, link in data.get("social_links", {}).items():
                existing = session.query(Contact).filter_by(
                    company_id=c.id, type=platform, value=link
                ).first()
                if not existing:
                    session.add(Contact(
                        company_id=c.id, type=platform, value=link,
                        source="web_crawl"
                    ))
                    contacts_found += 1

            # Update INN if found
            if data.get("inn") and not c.inn:
                c.inn = data["inn"]

            c.enrichment_status = "enriched"
            crawled += 1

            emails_str = ", ".join(data.get("emails", [])[:3]) or "—"
            phones_str = ", ".join(data.get("phones", [])[:2]) or "—"
            socials_str = ", ".join(data.get("social_links", {}).keys()) or "—"
            print(f"    📧 {emails_str}")
            print(f"    📞 {phones_str}")
            print(f"    🔗 {socials_str}")

            session.commit()

        except Exception as e:
            print(f"    ❌ Ошибка: {e}")
            errors += 1
            c.enrichment_status = "failed"
            session.commit()

    print(f"\n{'='*60}")
    print(f"✅ Crawling завершён:")
    print(f"   Обработано: {crawled}")
    print(f"   Контактов найдено: {contacts_found}")
    print(f"   Ошибок: {errors}")


def print_summary(session: Session):
    """Print final enrichment summary."""
    total = session.query(Company).count()
    scored = session.query(Company).filter(Company.lead_score > 0).count()
    enriched = session.query(Company).filter_by(enrichment_status="enriched").count()
    with_website = session.query(Company).filter(
        Company.website.isnot(None), Company.website != ""
    ).count()
    total_contacts = session.query(Contact).count()

    print(f"\n{'='*60}")
    print(f"📊 ИТОГО:")
    print(f"   Компаний в БД: {total}")
    print(f"   С lead score > 0: {scored}")
    print(f"   С сайтом: {with_website}")
    print(f"   Обогащено (crawled): {enriched}")
    print(f"   Контактов найдено: {total_contacts}")
    print(f"{'='*60}")

    # Score distribution
    from sqlalchemy import func
    segments = [
        ("🔴 Холодные (0-30)", 0, 30),
        ("🟡 Тёплые (31-60)", 31, 60),
        ("🟢 Горячие (61-80)", 61, 80),
        ("🔥 Топ (81-100)", 81, 100),
    ]
    print(f"\n📈 Распределение по lead score:")
    for label, lo, hi in segments:
        cnt = session.query(Company).filter(
            Company.lead_score >= lo, Company.lead_score <= hi
        ).count()
        print(f"   {label}: {cnt}")


if __name__ == "__main__":
    session = Session(engine)

    try:
        # Phase 1: Score all companies
        enrich_lead_scores(session)

        # Phase 2: Crawl websites
        enrich_web_crawl(session, limit=50)  # Start with top 50 by score

        # Summary
        print_summary(session)

    finally:
        session.close()
