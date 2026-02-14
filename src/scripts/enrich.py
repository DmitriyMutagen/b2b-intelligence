"""
Enrichment Pipeline — orchestrates the full enrichment flow:
1. Calculate rule-based lead score
2. Crawl website (if found)
3. AI analysis (if OpenAI key available)
4. Update company record in database
"""
import time
import traceback
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.database.models import Company, Person, Contact, Intelligence
from src.ai.brain import calculate_lead_score, analyze_lead
from src.recon.web_crawler import crawl_website, CrawlResult


def enrich_company(company_id: int, use_ai: bool = True) -> dict:
    """
    Enrich a single company.

    Steps:
    1. Load company from DB
    2. Calculate rule-based lead score
    3. Crawl website (if URL available)
    4. Save contacts found from crawling
    5. Run AI analysis (if enabled)
    6. Save intelligence to DB
    7. Update company status and score

    Returns: summary dict
    """
    session = SessionLocal()
    report = {"company_id": company_id, "status": "started", "steps": []}

    try:
        company = session.query(Company).get(company_id)
        if not company:
            return {"error": f"Company {company_id} not found"}

        report["company_name"] = company.name
        print(f"\n{'='*50}")
        print(f"Enriching: {company.name} (id={company_id})")

        # Step 1: Rule-based lead score
        company_dict = {
            "name": company.name,
            "revenue_total": company.revenue_total,
            "sales_total": company.sales_total,
            "wb_present": company.wb_present,
            "ozon_present": company.ozon_present,
            "avg_price": company.avg_price,
            "website": company.website,
            "contacts_count": len(company.contacts) if hasattr(company, 'contacts') else 0,
        }

        rule_score = calculate_lead_score(company_dict)
        company.lead_score = rule_score
        company.enrichment_status = "in_progress"
        session.commit()
        report["steps"].append({"step": "lead_score", "score": rule_score})
        print(f"  Lead Score (rule-based): {rule_score}/100")

        # Step 2: Web crawl (if website available)
        crawl_data = None
        website_url = company.website

        # Try to find website from WB/Ozon brand links
        if not website_url and company.wb_brand_link:
            website_url = company.wb_brand_link
        if not website_url and company.ozon_brand_link:
            website_url = company.ozon_brand_link

        if website_url and website_url.startswith("http"):
            try:
                print(f"  Crawling: {website_url}")
                result = crawl_website(website_url, max_depth=2, max_pages=8)
                crawl_data = result.to_dict()

                # Save found contacts
                for email in result.emails[:5]:
                    existing = session.query(Contact).filter_by(
                        company_id=company.id, value=email
                    ).first()
                    if not existing:
                        session.add(Contact(
                            company_id=company.id,
                            type="email",
                            value=email,
                            source="web_crawler"
                        ))

                for phone in result.phones[:5]:
                    existing = session.query(Contact).filter_by(
                        company_id=company.id, value=phone
                    ).first()
                    if not existing:
                        session.add(Contact(
                            company_id=company.id,
                            type="phone",
                            value=phone,
                            source="web_crawler"
                        ))

                # Update website and INN
                if result.inn and not company.inn:
                    company.inn = result.inn

                if not company.website and result.url:
                    company.website = result.url

                session.commit()
                report["steps"].append({
                    "step": "web_crawl",
                    "emails_found": len(result.emails),
                    "phones_found": len(result.phones),
                    "socials": list(result.social_links.keys()),
                })
                print(f"  Crawl results: {len(result.emails)} emails, {len(result.phones)} phones")
            except Exception as e:
                report["steps"].append({"step": "web_crawl", "error": str(e)})
                print(f"  Crawl error: {e}")

        # Step 3: AI Analysis
        if use_ai:
            try:
                print(f"  Running AI analysis...")
                ai_result = analyze_lead(company_dict, crawl_data)

                if "error" not in ai_result:
                    # Update lead score with AI score
                    ai_score = ai_result.get("lead_score", rule_score)
                    company.lead_score = ai_score

                    # Save intelligence
                    existing_intel = session.query(Intelligence).filter_by(
                        company_id=company.id
                    ).first()

                    intel_data = {
                        "company_id": company.id,
                        "pain_points": ai_result.get("pain_points"),
                        "brand_dna": ai_result.get("brand_dna"),
                        "approach_strategy": ai_result.get("approach_strategy"),
                        "recommended_products": ai_result.get("recommended_products"),
                        "deal_potential": ai_result.get("deal_potential_rub"),
                    }

                    if existing_intel:
                        for k, v in intel_data.items():
                            if k != "company_id":
                                setattr(existing_intel, k, v)
                    else:
                        session.add(Intelligence(**intel_data))

                    session.commit()
                    report["steps"].append({
                        "step": "ai_analysis",
                        "ai_score": ai_score,
                        "pain_points": ai_result.get("pain_points", []),
                    })
                    print(f"  AI Score: {ai_score}/100")
                    print(f"  Pain points: {ai_result.get('pain_points', [])}")
                else:
                    report["steps"].append({"step": "ai_analysis", "error": ai_result["error"]})
                    print(f"  AI error: {ai_result['error']}")

            except Exception as e:
                report["steps"].append({"step": "ai_analysis", "error": str(e)})
                print(f"  AI analysis error: {e}")

        # Final status update
        company.enrichment_status = "enriched"
        session.commit()
        report["status"] = "completed"
        report["final_score"] = company.lead_score
        print(f"  ✅ Enriched! Final Score: {company.lead_score}/100")

    except Exception as e:
        report["status"] = "error"
        report["error"] = str(e)
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

    return report


def enrich_batch(
    limit: int = 50,
    status_filter: str = "new",
    use_ai: bool = True,
    delay: float = 1.0
) -> list:
    """
    Enrich a batch of companies.

    Args:
        limit: Max companies to process
        status_filter: Only process companies with this status
        use_ai: Whether to use AI analysis
        delay: Delay between companies (seconds)

    Returns: list of report dicts
    """
    session = SessionLocal()
    companies = session.query(Company).filter_by(
        enrichment_status=status_filter
    ).order_by(Company.revenue_total.desc().nulls_last()).limit(limit).all()

    company_ids = [c.id for c in companies]
    session.close()

    print(f"\n{'='*60}")
    print(f"BATCH ENRICHMENT: {len(company_ids)} companies")
    print(f"{'='*60}")

    reports = []
    for i, cid in enumerate(company_ids, 1):
        print(f"\n[{i}/{len(company_ids)}]")
        report = enrich_company(cid, use_ai=use_ai)
        reports.append(report)

        if i < len(company_ids):
            time.sleep(delay)

    # Summary
    success = sum(1 for r in reports if r["status"] == "completed")
    errors = sum(1 for r in reports if r["status"] == "error")
    print(f"\n{'='*60}")
    print(f"BATCH COMPLETE: {success} enriched, {errors} errors")
    print(f"{'='*60}")

    return reports


# ─── CLI ───
if __name__ == "__main__":
    import sys

    # Default: enrich top 10 companies by revenue (rule-based only, no AI)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    use_ai = "--ai" in sys.argv

    print(f"Mode: {'AI + Rules' if use_ai else 'Rules only'}")
    reports = enrich_batch(limit=limit, use_ai=use_ai, delay=0.5)
