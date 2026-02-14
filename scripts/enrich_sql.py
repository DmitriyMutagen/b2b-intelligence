"""Quick SQL-based enrichment + audit of all data."""
import psycopg2

conn = psycopg2.connect(
    host='localhost', port=5432,
    user='marketai', password='marketai',
    dbname='b2b_intelligence', connect_timeout=5
)
cur = conn.cursor()

# 1. Current state
cur.execute("SELECT enrichment_status, count(*) FROM companies GROUP BY enrichment_status")
print("BEFORE:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

# 2. Run lead scoring via SQL (instant, no Python overhead)
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
""")
conn.commit()
print(f"\nUpdated: {cur.rowcount} companies")

# 3. Stats after
cur.execute("SELECT count(*) FROM companies WHERE lead_score >= 70")
hot = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM companies WHERE lead_score BETWEEN 40 AND 69")
warm = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM companies WHERE lead_score < 40")
cold = cur.fetchone()[0]
print(f"\nHot(70+): {hot} | Warm(40-69): {warm} | Cold(<40): {cold}")

# 4. Top 15
cur.execute("""
    SELECT name, revenue_total, sales_total, avg_price, 
           wb_present, ozon_present, lead_score 
    FROM companies ORDER BY lead_score DESC, revenue_total DESC NULLS LAST LIMIT 15
""")
print("\nTop 15:")
for r in cur.fetchall():
    rev = f"{r[1]/1e6:.1f}M" if r[1] else "N/A"
    sales = f"{r[2]/1e3:.0f}K" if r[2] else "N/A"
    mp = ("WB+Ozon" if r[4] and r[5] else "WB" if r[4] else "Ozon" if r[5] else "—")
    print(f"  {r[0]:35s} Score={r[6]:3d} Rev={rev:>8s} Sales={sales:>6s} {mp}")

# 5. Table checks
for tbl in ['persons', 'contacts', 'intelligence', 'interactions', 'documents']:
    cur.execute(f"SELECT count(*) FROM {tbl}")
    print(f"\n{tbl}: {cur.fetchone()[0]} records")

conn.close()
print("\nDONE!")
