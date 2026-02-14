"""
Bitrix24 Full Data Sync — pulls ALL data from CRM into local database.
Creates tables if needed, syncs leads/deals/contacts/calls.
"""
import os, sys, time, json

# Fix Windows cp1251 terminal encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import psycopg2
import psycopg2.extras
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

WEBHOOK = os.getenv("BITRIX24_WEBHOOK_URL", "").rstrip("/")
DB_CONN = dict(host='localhost', port=5432, user='marketai', password='marketai', dbname='b2b_intelligence', connect_timeout=10)


def b24_call(method, params=None):
    """Call Bitrix24 API with retry."""
    url = f"{WEBHOOK}/{method}.json"
    for attempt in range(3):
        try:
            r = requests.get(url, params=params or {}, timeout=15)
            data = r.json()
            if data.get("error") == "QUERY_LIMIT_EXCEEDED":
                time.sleep(2 ** attempt)
                continue
            return data
        except Exception as e:
            if attempt == 2:
                return {"error": str(e)}
            time.sleep(1)
    return {"error": "max retries"}


def b24_get_all(method, params=None, limit=None):
    """Fetch all records with pagination."""
    params = dict(params or {})
    items = []
    start = 0
    while True:
        params["start"] = start
        result = b24_call(method, params)
        if "result" not in result:
            print(f"  Error {method}: {result.get('error', 'unknown')}")
            break
        batch = result["result"]
        items.extend(batch)
        total = result.get("total", 0)
        nxt = result.get("next")
        if limit and len(items) >= limit:
            items = items[:limit]
            break
        if nxt is None or len(batch) == 0:
            break
        start = nxt
        if len(items) % 500 == 0:
            print(f"    ...{len(items)}/{total}")
        time.sleep(0.5)
    return items


def create_crm_tables(conn):
    """Create Bitrix CRM mirror tables."""
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bitrix_leads (
        id INTEGER PRIMARY KEY,
        title TEXT,
        name TEXT,
        last_name TEXT,
        status_id TEXT,
        status_description TEXT,
        source_id TEXT,
        source_description TEXT,
        company_title TEXT,
        phone TEXT,
        email TEXT,
        comments TEXT,
        assigned_by_id INTEGER,
        date_create TIMESTAMP,
        date_modify TIMESTAMP,
        date_closed TIMESTAMP,
        raw_data JSONB
    );
    
    CREATE TABLE IF NOT EXISTS bitrix_deals (
        id INTEGER PRIMARY KEY,
        title TEXT,
        stage_id TEXT,
        category_id INTEGER,
        opportunity FLOAT,
        currency_id TEXT,
        contact_id INTEGER,
        company_id INTEGER,
        assigned_by_id INTEGER,
        comments TEXT,
        date_create TIMESTAMP,
        date_modify TIMESTAMP,
        closedate TIMESTAMP,
        raw_data JSONB
    );
    
    CREATE TABLE IF NOT EXISTS bitrix_contacts (
        id INTEGER PRIMARY KEY,
        name TEXT,
        last_name TEXT,
        phone TEXT,
        email TEXT,
        company_id INTEGER,
        post TEXT,
        source_id TEXT,
        assigned_by_id INTEGER,
        date_create TIMESTAMP,
        raw_data JSONB
    );
    
    CREATE TABLE IF NOT EXISTS bitrix_calls (
        id TEXT PRIMARY KEY,
        call_type INTEGER,
        phone_number TEXT,
        duration INTEGER,
        call_start_date TIMESTAMP,
        call_failed_code TEXT,
        crm_entity_type TEXT,
        crm_entity_id INTEGER,
        portal_user_id INTEGER,
        cost FLOAT,
        raw_data JSONB
    );
    
    CREATE TABLE IF NOT EXISTS crm_analytics (
        id SERIAL PRIMARY KEY,
        analysis_type TEXT,
        analysis_date TIMESTAMP DEFAULT NOW(),
        data JSONB
    );
    """)
    conn.commit()
    print("✅ CRM tables created")


def extract_phone(phones):
    """Extract first phone from Bitrix phone array."""
    if not phones:
        return None
    if isinstance(phones, list) and len(phones) > 0:
        return phones[0].get("VALUE", "")
    return str(phones)


def extract_email(emails):
    """Extract first email from Bitrix email array."""
    if not emails:
        return None
    if isinstance(emails, list) and len(emails) > 0:
        return emails[0].get("VALUE", "")
    return str(emails)


def parse_date(date_str):
    """Parse Bitrix date string."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("T", " ").split("+")[0])
    except:
        return None


def sync_leads(conn, limit=None):
    """Sync all leads from Bitrix24."""
    print("\n📥 Syncing LEADS...")
    leads = b24_get_all("crm.lead.list", {
        "select[]": ["ID","TITLE","NAME","LAST_NAME","STATUS_ID","STATUS_DESCRIPTION",
                      "SOURCE_ID","SOURCE_DESCRIPTION","COMPANY_TITLE","PHONE","EMAIL",
                      "COMMENTS","ASSIGNED_BY_ID","DATE_CREATE","DATE_MODIFY","DATE_CLOSED"]
    }, limit)
    print(f"  Fetched {len(leads)} leads")
    
    cur = conn.cursor()
    cur.execute("DELETE FROM bitrix_leads")
    
    for lead in leads:
        cur.execute("""
            INSERT INTO bitrix_leads (id,title,name,last_name,status_id,status_description,
                source_id,source_description,company_title,phone,email,comments,
                assigned_by_id,date_create,date_modify,date_closed,raw_data)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                status_id=EXCLUDED.status_id, date_modify=EXCLUDED.date_modify,
                raw_data=EXCLUDED.raw_data
        """, (
            int(lead["ID"]), lead.get("TITLE"), lead.get("NAME"), lead.get("LAST_NAME"),
            lead.get("STATUS_ID"), lead.get("STATUS_DESCRIPTION"),
            lead.get("SOURCE_ID"), lead.get("SOURCE_DESCRIPTION"),
            lead.get("COMPANY_TITLE"),
            extract_phone(lead.get("PHONE")), extract_email(lead.get("EMAIL")),
            lead.get("COMMENTS"), lead.get("ASSIGNED_BY_ID"),
            parse_date(lead.get("DATE_CREATE")), parse_date(lead.get("DATE_MODIFY")),
            parse_date(lead.get("DATE_CLOSED")),
            json.dumps(lead, ensure_ascii=False, default=str)
        ))
    
    conn.commit()
    print(f"  ✅ {len(leads)} leads saved")
    return len(leads)


def sync_deals(conn, limit=None):
    """Sync all deals from Bitrix24."""
    print("\n📥 Syncing DEALS...")
    deals = b24_get_all("crm.deal.list", {
        "select[]": ["ID","TITLE","STAGE_ID","CATEGORY_ID","OPPORTUNITY","CURRENCY_ID",
                      "CONTACT_ID","COMPANY_ID","ASSIGNED_BY_ID","COMMENTS",
                      "DATE_CREATE","DATE_MODIFY","CLOSEDATE"]
    }, limit)
    print(f"  Fetched {len(deals)} deals")
    
    cur = conn.cursor()
    cur.execute("DELETE FROM bitrix_deals")
    
    for deal in deals:
        cur.execute("""
            INSERT INTO bitrix_deals (id,title,stage_id,category_id,opportunity,currency_id,
                contact_id,company_id,assigned_by_id,comments,date_create,date_modify,closedate,raw_data)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                stage_id=EXCLUDED.stage_id, opportunity=EXCLUDED.opportunity,
                date_modify=EXCLUDED.date_modify, raw_data=EXCLUDED.raw_data
        """, (
            int(deal["ID"]), deal.get("TITLE"), deal.get("STAGE_ID"),
            deal.get("CATEGORY_ID"), float(deal.get("OPPORTUNITY") or 0),
            deal.get("CURRENCY_ID"),
            deal.get("CONTACT_ID"), deal.get("COMPANY_ID"),
            deal.get("ASSIGNED_BY_ID"), deal.get("COMMENTS"),
            parse_date(deal.get("DATE_CREATE")), parse_date(deal.get("DATE_MODIFY")),
            parse_date(deal.get("CLOSEDATE")),
            json.dumps(deal, ensure_ascii=False, default=str)
        ))
    
    conn.commit()
    print(f"  ✅ {len(deals)} deals saved")
    return len(deals)


def sync_contacts(conn, limit=None):
    """Sync all contacts from Bitrix24."""
    print("\n📥 Syncing CONTACTS...")
    contacts = b24_get_all("crm.contact.list", {
        "select[]": ["ID","NAME","LAST_NAME","PHONE","EMAIL",
                      "COMPANY_ID","POST","SOURCE_ID","ASSIGNED_BY_ID","DATE_CREATE"]
    }, limit)
    print(f"  Fetched {len(contacts)} contacts")
    
    cur = conn.cursor()
    cur.execute("DELETE FROM bitrix_contacts")
    
    for c in contacts:
        cur.execute("""
            INSERT INTO bitrix_contacts (id,name,last_name,phone,email,company_id,post,
                source_id,assigned_by_id,date_create,raw_data)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                phone=EXCLUDED.phone, email=EXCLUDED.email, raw_data=EXCLUDED.raw_data
        """, (
            int(c["ID"]), c.get("NAME"), c.get("LAST_NAME"),
            extract_phone(c.get("PHONE")), extract_email(c.get("EMAIL")),
            c.get("COMPANY_ID"), c.get("POST"),
            c.get("SOURCE_ID"), c.get("ASSIGNED_BY_ID"),
            parse_date(c.get("DATE_CREATE")),
            json.dumps(c, ensure_ascii=False, default=str)
        ))
    
    conn.commit()
    print(f"  ✅ {len(contacts)} contacts saved")
    return len(contacts)


def sync_calls(conn, limit=None):
    """Sync call records from Bitrix24."""
    print("\n📥 Syncing CALLS...")
    calls = b24_get_all("voximplant.statistic.get", {"LIMIT": 50}, limit)
    print(f"  Fetched {len(calls)} call records")
    
    cur = conn.cursor()
    cur.execute("DELETE FROM bitrix_calls")
    
    for call in calls:
        call_id = call.get("ID") or call.get("CALL_ID") or str(hash(json.dumps(call, default=str)))
        cur.execute("""
            INSERT INTO bitrix_calls (id,call_type,phone_number,duration,call_start_date,
                call_failed_code,crm_entity_type,crm_entity_id,portal_user_id,cost,raw_data)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (
            str(call_id), call.get("CALL_TYPE"),
            call.get("PHONE_NUMBER"), call.get("DURATION"),
            parse_date(call.get("CALL_START_DATE")),
            call.get("CALL_FAILED_CODE"),
            call.get("CRM_ENTITY_TYPE"), call.get("CRM_ENTITY_ID"),
            call.get("PORTAL_USER_ID"), call.get("COST"),
            json.dumps(call, ensure_ascii=False, default=str)
        ))
    
    conn.commit()
    print(f"  ✅ {len(calls)} calls saved")
    return len(calls)


def run_analytics(conn):
    """Run CRM analytics queries after sync."""
    cur = conn.cursor()
    analytics = {}
    
    # 1. Lead funnel
    cur.execute("""
        SELECT status_id, count(*) as cnt 
        FROM bitrix_leads GROUP BY status_id ORDER BY cnt DESC
    """)
    analytics["lead_statuses"] = {r[0]: r[1] for r in cur.fetchall()}
    
    # 2. Lost leads (no activity in 30+ days, not closed)
    cur.execute("""
        SELECT count(*) FROM bitrix_leads 
        WHERE status_id NOT IN ('CONVERTED','JUNK')
        AND date_modify < NOW() - INTERVAL '30 days'
    """)
    analytics["lost_leads_30d"] = cur.fetchone()[0]
    
    cur.execute("""
        SELECT count(*) FROM bitrix_leads 
        WHERE status_id NOT IN ('CONVERTED','JUNK')
        AND date_modify < NOW() - INTERVAL '90 days'
    """)
    analytics["lost_leads_90d"] = cur.fetchone()[0]
    
    # 3. Deal stages
    cur.execute("""
        SELECT stage_id, count(*), COALESCE(SUM(opportunity),0)
        FROM bitrix_deals GROUP BY stage_id ORDER BY count(*) DESC
    """)
    analytics["deal_stages"] = [{"stage": r[0], "count": r[1], "amount": float(r[2])} for r in cur.fetchall()]
    
    # 4. Stuck deals (same stage >14 days)
    cur.execute("""
        SELECT count(*) FROM bitrix_deals
        WHERE stage_id NOT LIKE 'WON%' AND stage_id NOT LIKE 'LOSE%'
        AND date_modify < NOW() - INTERVAL '14 days'
    """)
    analytics["stuck_deals"] = cur.fetchone()[0]
    
    # 5. Call stats
    cur.execute("SELECT count(*), COALESCE(AVG(duration),0), COALESCE(SUM(duration),0) FROM bitrix_calls")
    r = cur.fetchone()
    analytics["calls_total"] = r[0]
    analytics["calls_avg_duration"] = round(float(r[1]), 1)
    analytics["calls_total_hours"] = round(float(r[2]) / 3600, 1)
    
    # 6. Top 20 lost leads (biggest potential)
    cur.execute("""
        SELECT id, title, name, last_name, company_title, phone, email, 
               status_id, date_create, date_modify, comments
        FROM bitrix_leads 
        WHERE status_id NOT IN ('CONVERTED','JUNK')
        AND date_modify < NOW() - INTERVAL '30 days'
        ORDER BY date_create DESC
        LIMIT 20
    """)
    cols = [d[0] for d in cur.description]
    analytics["top_lost_leads"] = [dict(zip(cols, row)) for row in cur.fetchall()]
    
    # 7. Top stuck deals
    cur.execute("""
        SELECT id, title, stage_id, opportunity, date_create, date_modify
        FROM bitrix_deals
        WHERE stage_id NOT LIKE 'WON%' AND stage_id NOT LIKE 'LOSE%'
        AND date_modify < NOW() - INTERVAL '14 days'
        ORDER BY opportunity DESC NULLS LAST
        LIMIT 20
    """)
    cols = [d[0] for d in cur.description]
    analytics["top_stuck_deals"] = [dict(zip(cols, row)) for row in cur.fetchall()]
    
    # Save analytics
    cur.execute("""
        INSERT INTO crm_analytics (analysis_type, data) 
        VALUES ('full_report', %s)
    """, (json.dumps(analytics, ensure_ascii=False, default=str),))
    conn.commit()
    
    return analytics


def print_report(analytics):
    """Print human-readable CRM report."""
    print("\n" + "="*60)
    print("CRM ANALYTICS REPORT")
    print("="*60)
    
    print("\n📊 LEAD STATUSES:")
    for status, cnt in sorted(analytics["lead_statuses"].items(), key=lambda x: -x[1]):
        print(f"  {status:25s}: {cnt}")
    
    print(f"\n⚠️  LOST LEADS (no activity >30 days): {analytics['lost_leads_30d']}")
    print(f"⚠️  LOST LEADS (no activity >90 days): {analytics['lost_leads_90d']}")
    
    print("\n💰 DEAL STAGES:")
    for d in analytics["deal_stages"]:
        amt = f"{d['amount']/1e6:.1f}M" if d['amount'] > 1e6 else f"{d['amount']:,.0f}"
        print(f"  {d['stage']:25s}: {d['count']} deals  ({amt} ₽)")
    
    print(f"\n⏸️  STUCK DEALS (>14 days same stage): {analytics['stuck_deals']}")
    
    print(f"\n📞 CALLS:")
    print(f"  Total: {analytics['calls_total']}")
    print(f"  Avg duration: {analytics['calls_avg_duration']}s")
    print(f"  Total hours: {analytics['calls_total_hours']}h")
    
    if analytics.get("top_lost_leads"):
        print(f"\n🔥 TOP LOST LEADS (вернуть в работу):")
        for lead in analytics["top_lost_leads"][:10]:
            name = f"{lead.get('name') or ''} {lead.get('last_name') or ''}".strip() or lead.get('title', '')
            phone = lead.get('phone') or '—'
            company = lead.get('company_title') or '—'
            print(f"  [{lead['id']}] {name:25s} | {company:20s} | {phone}")
    
    if analytics.get("top_stuck_deals"):
        print(f"\n⏳ TOP STUCK DEALS:")
        for deal in analytics["top_stuck_deals"][:10]:
            opp = f"{deal.get('opportunity',0):,.0f}₽"
            print(f"  [{deal['id']}] {deal.get('title',''):30s} | {deal.get('stage_id',''):15s} | {opp}")


# ─── MAIN ───
if __name__ == "__main__":
    print("="*60)
    print("BITRIX24 FULL CRM SYNC + ANALYTICS")
    print("="*60)
    
    # Use --quick for first 100 records only
    quick = "--quick" in sys.argv
    limit = 100 if quick else None
    
    conn = psycopg2.connect(**DB_CONN)
    
    # Step 1: Create tables
    create_crm_tables(conn)
    
    # Step 2: First enrich companies (fix dashboard)
    print("\n📊 Enriching companies (lead scoring)...")
    cur = conn.cursor()
    cur.execute("""
    UPDATE companies SET 
      lead_score = LEAST(100, (
        CASE WHEN revenue_total > 100000000 THEN 30
             WHEN revenue_total > 50000000 THEN 25
             WHEN revenue_total > 10000000 THEN 20
             WHEN revenue_total > 1000000 THEN 10
             ELSE 0 END
        + CASE WHEN wb_present AND ozon_present THEN 20
               WHEN wb_present OR ozon_present THEN 12
               ELSE 0 END
        + CASE WHEN sales_total > 100000 THEN 20
               WHEN sales_total > 50000 THEN 15
               WHEN sales_total > 10000 THEN 10
               WHEN sales_total > 1000 THEN 5
               ELSE 0 END
        + CASE WHEN avg_price > 2000 THEN 15
               WHEN avg_price > 1000 THEN 10
               WHEN avg_price > 500 THEN 5
               ELSE 0 END
      )),
      enrichment_status = 'enriched'
    WHERE enrichment_status = 'new' OR lead_score = 0
    """)
    conn.commit()
    print(f"  ✅ {cur.rowcount} companies scored")
    
    # Step 3: Sync Bitrix data
    n_leads = sync_leads(conn, limit)
    n_deals = sync_deals(conn, limit)
    n_contacts = sync_contacts(conn, limit)
    n_calls = sync_calls(conn, limit)
    
    # Step 4: Run analytics
    analytics = run_analytics(conn)
    
    # Step 5: Print report
    print_report(analytics)
    
    # Save report to file
    with open("scripts/crm_report.json", "w", encoding="utf-8") as f:
        json.dump(analytics, f, ensure_ascii=False, indent=2, default=str)
    
    conn.close()
    
    print("\n" + "="*60)
    print("SYNC COMPLETE!")
    print(f"Leads: {n_leads} | Deals: {n_deals} | Contacts: {n_contacts} | Calls: {n_calls}")
    print("Report saved to scripts/crm_report.json")
    print("="*60)
