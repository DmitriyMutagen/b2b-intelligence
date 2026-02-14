"""
Ingestion script: Load STM Master Excel (800 records) into PostgreSQL.

Usage:
    python src/scripts/ingest_stm.py
"""
import os
import sys
import re

import pandas as pd
from sqlalchemy import text

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.database import engine
from src.database.models import Base, Company, Person, Contact

from dotenv import load_dotenv
load_dotenv()

# --- Config ---
EXCEL_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'docs', 'File',
    'STM_Sellers_Full_Master_v3_contacts_partial (1).xlsx'
)
SOURCE = "STM_Master_v3"


def create_tables():
    """Create all tables if they don't exist."""
    print("Creating tables...")
    Base.metadata.create_all(engine)
    print("Tables ready.")


def parse_names(names_field: str) -> list[dict]:
    """Parse the Names column into structured person records."""
    if not names_field or pd.isna(names_field):
        return []
    
    persons = []
    # Names might be comma-separated or contain role info
    raw = str(names_field).strip()
    if raw:
        persons.append({
            "full_name": raw,
            "role": "LPR (из STM)",
            "source": "stm_file"
        })
    return persons


def ingest():
    """Main ingestion logic."""
    print(f"Reading: {EXCEL_PATH}")
    
    # Read the MASTER sheet
    df = pd.read_excel(EXCEL_PATH, sheet_name='MASTER_672_companies', engine='openpyxl')
    df.columns = [str(c).strip() for c in df.columns]
    
    print(f"Columns: {df.columns.tolist()}")
    print(f"Rows: {len(df)}")
    
    from sqlalchemy.orm import Session
    session = Session(engine)
    
    imported = 0
    skipped = 0
    errors = 0
    
    for _, row in df.iterrows():
        try:
            key = str(row.get('key', '')).strip()
            name = str(row.get('Company', '')).strip()
            
            if not name or not key:
                skipped += 1
                continue
            
            # Check duplicate
            existing = session.execute(
                text("SELECT id FROM companies WHERE key = :key"),
                {"key": key}
            ).scalar()
            
            if existing:
                skipped += 1
                continue
            
            # Create Company
            company = Company(
                key=key,
                name=name,
                legal_form=str(row.get('LegalForm', '')) if pd.notna(row.get('LegalForm')) else None,
                wb_present=bool(row.get('WB_present', 0)),
                ozon_present=bool(row.get('OZON_present', 0)),
                revenue_total=float(row['Revenue_total']) if pd.notna(row.get('Revenue_total')) else None,
                sales_total=float(row['Sales_total']) if pd.notna(row.get('Sales_total')) else None,
                avg_price=float(row['AvgPrice_calc']) if pd.notna(row.get('AvgPrice_calc')) else None,
                wb_brand_link=str(row.get('WB_brand_link', '')) if pd.notna(row.get('WB_brand_link')) else None,
                ozon_brand_link=str(row.get('Ozon_brand_link', '')) if pd.notna(row.get('Ozon_brand_link')) else None,
                source_file=SOURCE,
                enrichment_status='new'
            )
            session.add(company)
            session.flush()  # Get ID
            
            # Parse persons from Names column
            names_raw = row.get('Names', '')
            for person_data in parse_names(names_raw):
                person = Person(
                    company_id=company.id,
                    full_name=person_data['full_name'],
                    role=person_data['role'],
                    source=person_data['source']
                )
                session.add(person)
            
            # Parse WB/Ozon links as contacts
            if company.wb_brand_link:
                session.add(Contact(
                    company_id=company.id,
                    type='marketplace_link',
                    value=company.wb_brand_link,
                    label='Wildberries',
                    source='stm_file'
                ))
            if company.ozon_brand_link:
                session.add(Contact(
                    company_id=company.id,
                    type='marketplace_link',
                    value=company.ozon_brand_link,
                    label='Ozon',
                    source='stm_file'
                ))
            
            imported += 1
            if imported % 100 == 0:
                print(f"  ...imported {imported}")
                session.commit()  # Intermediate commit
                
        except Exception as e:
            errors += 1
            print(f"  ERROR row {row.get('key', '?')}: {e}")
    
    session.commit()
    session.close()
    
    print(f"\n{'='*50}")
    print(f"DONE: Imported={imported}, Skipped={skipped}, Errors={errors}")


if __name__ == "__main__":
    create_tables()
    ingest()
