"""
Реконнесенс-обогащение компаний — массовый парсинг сайтов.

Берёт компании из БД, которые имеют сайт (website != NULL),
парсит их через web_crawler и сохраняет найденные контакты
(emails, телефоны, соцсети, ИНН) обратно в таблицу contacts.

Запуск:
    python scripts/recon_enrichment.py [--limit 50] [--force]
"""
import sys
import os
import time
import argparse

# Encoding fix for Windows
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

# ─── Database connection ───
# NOTE: .env имеет POSTGRES_DB=b2b_intelligence, но реальная БД в Docker = marketai
DB_CONN = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": "b2b_intelligence",
    "user": os.getenv("POSTGRES_USER", "marketai"),
    "password": os.getenv("POSTGRES_PASSWORD", "marketai"),
}

# Import our existing web crawler
from src.recon.web_crawler import crawl_website


def get_companies_to_crawl(conn, limit=50, force=False):
    """Получить компании для парсинга."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if force:
        # Парсить все с сайтом
        cur.execute("""
            SELECT id, name, website, inn 
            FROM companies 
            WHERE website IS NOT NULL AND website != ''
            ORDER BY revenue_total DESC NULLS LAST
            LIMIT %s
        """, (limit,))
    else:
        # Парсить только те, у которых нет контактов с источником web_crawl
        cur.execute("""
            SELECT c.id, c.name, c.website, c.inn 
            FROM companies c
            WHERE c.website IS NOT NULL AND c.website != ''
              AND c.id NOT IN (
                  SELECT DISTINCT company_id FROM contacts WHERE source = 'web_crawl'
              )
            ORDER BY c.revenue_total DESC NULLS LAST
            LIMIT %s
        """, (limit,))
    
    rows = cur.fetchall()
    cur.close()
    return rows


def save_crawl_results(conn, company_id, crawl_result):
    """Сохранить результаты парсинга в БД."""
    cur = conn.cursor()
    saved = 0
    
    # Удалить старые web_crawl контакты для этой компании
    cur.execute("DELETE FROM contacts WHERE company_id = %s AND source = 'web_crawl'", (company_id,))
    
    # Emails
    for email in crawl_result.emails:
        cur.execute("""
            INSERT INTO contacts (company_id, type, value, source, is_verified)
            VALUES (%s, 'email', %s, 'web_crawl', false)
        """, (company_id, email))
        saved += 1
    
    # Phones
    for phone in crawl_result.phones:
        # Нормализации
        clean = phone.strip()
        cur.execute("""
            INSERT INTO contacts (company_id, type, value, source, is_verified)
            VALUES (%s, 'phone', %s, 'web_crawl', false)
        """, (company_id, clean))
        saved += 1
    
    # Social links
    for platform, url in crawl_result.social_links.items():
        cur.execute("""
            INSERT INTO contacts (company_id, type, value, label, source, is_verified)
            VALUES (%s, %s, %s, %s, 'web_crawl', false)
        """, (company_id, platform, url, platform.capitalize()))
        saved += 1
    
    # Обновить ИНН если нашли и нет в БД
    if crawl_result.inn:
        cur.execute("""
            UPDATE companies SET inn = %s WHERE id = %s AND (inn IS NULL OR inn = '')
        """, (crawl_result.inn, company_id))
    
    conn.commit()
    cur.close()
    return saved


def run_mass_crawl(limit=50, force=False):
    """Запустить массовый парсинг сайтов компаний."""
    print("=" * 60)
    print("🔍 РЕКОННЕСЕНС — Парсинг сайтов компаний")
    print("=" * 60)
    
    conn = psycopg2.connect(**DB_CONN)
    companies = get_companies_to_crawl(conn, limit=limit, force=force)
    
    print(f"\n📋 Компаний для парсинга: {len(companies)}")
    if not companies:
        print("✅ Все компании уже обработаны!")
        conn.close()
        return {"processed": 0, "contacts_found": 0}
    
    total_contacts = 0
    processed = 0
    errors = 0
    
    for i, company in enumerate(companies, 1):
        comp_id = company['id']
        name = company['name']
        website = company['website']
        
        print(f"\n[{i}/{len(companies)}] 🏢 {name}")
        print(f"    🌐 {website}")
        
        try:
            result = crawl_website(website, max_depth=2, max_pages=10)
            
            # Сохранить результаты
            saved = save_crawl_results(conn, comp_id, result)
            total_contacts += saved
            processed += 1
            
            print(f"    📧 Emails: {len(result.emails)}")
            print(f"    📞 Телефоны: {len(result.phones)}")
            print(f"    🔗 Соцсети: {list(result.social_links.keys())}")
            if result.inn:
                print(f"    🏛️ ИНН: {result.inn}")
            print(f"    💾 Сохранено контактов: {saved}")
            
        except Exception as e:
            errors += 1
            print(f"    ❌ Ошибка: {e}")
        
        # Пауза между сайтами
        time.sleep(1)
    
    conn.close()
    
    print("\n" + "=" * 60)
    print(f"✅ РЕЗУЛЬТАТ:")
    print(f"   Обработано: {processed}/{len(companies)}")
    print(f"   Контактов найдено: {total_contacts}")
    print(f"   Ошибок: {errors}")
    print("=" * 60)
    
    return {
        "processed": processed,
        "contacts_found": total_contacts,
        "errors": errors
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Массовый парсинг сайтов компаний")
    parser.add_argument("--limit", type=int, default=50, help="Максимум компаний для парсинга")
    parser.add_argument("--force", action="store_true", help="Перепарсить даже уже обработанные")
    args = parser.parse_args()
    
    run_mass_crawl(limit=args.limit, force=args.force)
