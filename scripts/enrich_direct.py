"""Direct DB enrichment — bypasses API timeout for bulk ops."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import SessionLocal
from src.database.models import Company
from src.ai.brain import calculate_lead_score

session = SessionLocal()
companies = session.query(Company).filter_by(enrichment_status="new").all()
print(f"Enriching {len(companies)} companies...")

for i, c in enumerate(companies, 1):
    data = {
        "name": c.name,
        "revenue_total": c.revenue_total,
        "sales_total": c.sales_total,
        "wb_present": c.wb_present,
        "ozon_present": c.ozon_present,
        "avg_price": c.avg_price,
        "website": c.website,
    }
    c.lead_score = calculate_lead_score(data)
    c.enrichment_status = "enriched"
    if i % 100 == 0:
        session.commit()
        print(f"  ...{i} done")

session.commit()
session.close()

# Stats
session2 = SessionLocal()
hot = session2.query(Company).filter(Company.lead_score >= 70).count()
warm = session2.query(Company).filter(Company.lead_score.between(40, 69)).count()
cold = session2.query(Company).filter(Company.lead_score < 40).count()
total = session2.query(Company).count()
enriched = session2.query(Company).filter_by(enrichment_status="enriched").count()
print(f"\nDONE! Total: {total} | Enriched: {enriched}")
print(f"Hot(70+): {hot} | Warm(40-69): {warm} | Cold(<40): {cold}")

top = session2.query(Company).order_by(Company.lead_score.desc()).limit(10).all()
print(f"\nTop 10:")
for c in top:
    print(f"  {c.name:35s} Score={c.lead_score} Rev={c.revenue_total}")
session2.close()
