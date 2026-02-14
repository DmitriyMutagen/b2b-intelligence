#!/usr/bin/env python3
"""
Обновление website и контактных данных из Excel в PostgreSQL.
Скрипт ingest_stm.py не маппил колонки Website, Phone, Email, Telegram и т.д.
Этот скрипт дозагружает недостающие поля.

Запуск: python scripts/update_contacts_from_excel.py
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pandas as pd
from sqlalchemy.orm import Session
from src.database import engine
from src.database.models import Base, Company, Contact

Base.metadata.create_all(engine)

EXCEL_PATH = os.path.join(ROOT, "docs", "File",
    "STM_Sellers_Full_Master_v3_contacts_partial (1).xlsx")

def main():
    df = pd.read_excel(EXCEL_PATH, sheet_name='MASTER_672_companies', engine='openpyxl')
    df.columns = [str(c).strip() for c in df.columns]
    print(f"Строк в Excel: {len(df)}")

    session = Session(engine)
    updated_websites = 0
    added_contacts = 0

    for _, row in df.iterrows():
        key = str(row.get("key", "")).strip()
        if not key:
            continue

        company = session.query(Company).filter_by(key=key).first()
        if not company:
            continue

        # Update website
        website = row.get("Website")
        if pd.notna(website) and str(website).strip():
            website = str(website).strip()
            if not company.website:
                company.website = website
                updated_websites += 1

        # Update contact page
        contact_page = row.get("ContactPage")
        if pd.notna(contact_page) and str(contact_page).strip():
            val = str(contact_page).strip()
            existing = session.query(Contact).filter_by(
                company_id=company.id, type="contact_page", value=val).first()
            if not existing:
                session.add(Contact(company_id=company.id, type="contact_page",
                    value=val, source="stm_file", label="Страница контактов"))
                added_contacts += 1

        # Import phone
        phone = row.get("Phone_public")
        if pd.notna(phone) and str(phone).strip():
            val = str(phone).strip()
            existing = session.query(Contact).filter_by(
                company_id=company.id, type="phone", value=val).first()
            if not existing:
                session.add(Contact(company_id=company.id, type="phone",
                    value=val, source="stm_file", label="Публичный"))
                added_contacts += 1

        # Import email
        email = row.get("Email_public")
        if pd.notna(email) and str(email).strip():
            val = str(email).strip()
            existing = session.query(Contact).filter_by(
                company_id=company.id, type="email", value=val).first()
            if not existing:
                session.add(Contact(company_id=company.id, type="email",
                    value=val, source="stm_file", label="Публичный"))
                added_contacts += 1

        # Import Telegram
        tg = row.get("Telegram_public")
        if pd.notna(tg) and str(tg).strip():
            val = str(tg).strip()
            existing = session.query(Contact).filter_by(
                company_id=company.id, type="telegram", value=val).first()
            if not existing:
                session.add(Contact(company_id=company.id, type="telegram",
                    value=val, source="stm_file"))
                added_contacts += 1

        # Import WhatsApp
        wa = row.get("WhatsApp_public")
        if pd.notna(wa) and str(wa).strip():
            val = str(wa).strip()
            existing = session.query(Contact).filter_by(
                company_id=company.id, type="whatsapp", value=val).first()
            if not existing:
                session.add(Contact(company_id=company.id, type="whatsapp",
                    value=val, source="stm_file"))
                added_contacts += 1

        # Import VK
        vk = row.get("VK_public")
        if pd.notna(vk) and str(vk).strip():
            val = str(vk).strip()
            existing = session.query(Contact).filter_by(
                company_id=company.id, type="vk", value=val).first()
            if not existing:
                session.add(Contact(company_id=company.id, type="vk",
                    value=val, source="stm_file"))
                added_contacts += 1

        # Import Other socials
        other = row.get("Other_socials")
        if pd.notna(other) and str(other).strip():
            val = str(other).strip()
            existing = session.query(Contact).filter_by(
                company_id=company.id, type="other", value=val).first()
            if not existing:
                session.add(Contact(company_id=company.id, type="other",
                    value=val, source="stm_file"))
                added_contacts += 1

        # Import WB brand link
        wb_link = row.get("WB_brand_link") or row.get("WB_search")
        if pd.notna(wb_link) and str(wb_link).strip():
            company.wb_brand_link = str(wb_link).strip()

        # Import Ozon brand link
        ozon_link = row.get("Ozon_brand_link") or row.get("OZON_search")
        if pd.notna(ozon_link) and str(ozon_link).strip():
            company.ozon_brand_link = str(ozon_link).strip()

    session.commit()
    session.close()

    print(f"\n✅ Готово:")
    print(f"   Сайтов обновлено: {updated_websites}")
    print(f"   Контактов добавлено: {added_contacts}")


if __name__ == "__main__":
    main()
