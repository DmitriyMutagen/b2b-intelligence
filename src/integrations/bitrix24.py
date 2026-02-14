"""
Bitrix24 CRM Client — sync leads, contacts, deals, companies, and call records.
Uses webhook REST API.
"""
import os
import time
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("BITRIX24_WEBHOOK_URL", "").rstrip("/")


class Bitrix24Client:
    """Wrapper for Bitrix24 REST API via webhook."""

    def __init__(self, webhook_url: str = WEBHOOK_URL):
        self.webhook = webhook_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def call(self, method: str, params: dict = None, retries: int = 3) -> dict:
        """Call a Bitrix24 method with auto-retry on rate limit."""
        url = f"{self.webhook}/{method}.json"
        for attempt in range(retries):
            try:
                resp = self.session.get(url, params=params or {}, timeout=15)
                data = resp.json()
                if "error" in data and data["error"] == "QUERY_LIMIT_EXCEEDED":
                    wait = 2 ** attempt
                    print(f"  Rate limit hit, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                return data
            except Exception as e:
                if attempt == retries - 1:
                    return {"error": str(e)}
                time.sleep(1)
        return {"error": "max retries exceeded"}

    def get_all(self, method: str, params: dict = None, limit: int = None) -> list:
        """Fetch all records using Bitrix24 pagination (50 per page)."""
        params = dict(params or {})
        all_items = []
        start = 0

        while True:
            params["start"] = start
            result = self.call(method, params)

            if "result" not in result:
                print(f"  Error fetching {method}: {result}")
                break

            items = result["result"]
            all_items.extend(items)

            if limit and len(all_items) >= limit:
                all_items = all_items[:limit]
                break

            total = result.get("total", 0)
            nxt = result.get("next")

            if nxt is None or len(items) == 0:
                break

            start = nxt
            print(f"  ...fetched {len(all_items)}/{total}")
            time.sleep(0.5)  # Be gentle

        return all_items

    # ─── CRM Methods ───
    def get_leads(self, limit=None, filters=None):
        params = {
            "select[]": ["ID", "TITLE", "NAME", "LAST_NAME", "STATUS_ID",
                         "PHONE", "EMAIL", "COMPANY_TITLE", "SOURCE_ID",
                         "DATE_CREATE", "DATE_MODIFY", "COMMENTS"]
        }
        if filters:
            for k, v in filters.items():
                params[f"filter[{k}]"] = v
        return self.get_all("crm.lead.list", params, limit)

    def get_contacts(self, limit=None):
        params = {
            "select[]": ["ID", "NAME", "LAST_NAME", "PHONE", "EMAIL",
                         "COMPANY_ID", "POST", "SOURCE_ID", "DATE_CREATE"]
        }
        return self.get_all("crm.contact.list", params, limit)

    def get_deals(self, limit=None):
        params = {
            "select[]": ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY",
                         "CURRENCY_ID", "CONTACT_ID", "COMPANY_ID",
                         "DATE_CREATE", "DATE_MODIFY", "CLOSEDATE", "COMMENTS"]
        }
        return self.get_all("crm.deal.list", params, limit)

    def get_companies(self, limit=None):
        params = {
            "select[]": ["ID", "TITLE", "PHONE", "EMAIL", "WEB",
                         "INDUSTRY", "REVENUE", "ADDRESS", "DATE_CREATE"]
        }
        return self.get_all("crm.company.list", params, limit)

    def get_call_records(self, limit=None):
        params = {"LIMIT": 50}
        return self.get_all("voximplant.statistic.get", params, limit)

    def get_lead_detail(self, lead_id: int):
        return self.call("crm.lead.get", {"id": lead_id})

    def create_lead(self, fields: dict):
        return self.call("crm.lead.add", {"fields": fields})

    def update_lead(self, lead_id: int, fields: dict):
        return self.call("crm.lead.update", {"id": lead_id, "fields": fields})

    def create_contact(self, fields: dict):
        return self.call("crm.contact.add", {"fields": fields})


# ─── Quick test ───
if __name__ == "__main__":
    client = Bitrix24Client()
    print(f"Webhook: {WEBHOOK_URL[:40]}...")

    # Get 5 leads as sample
    leads = client.get_leads(limit=5)
    print(f"\nSample leads ({len(leads)}):")
    for lead in leads:
        name = f"{lead.get('NAME', '')} {lead.get('LAST_NAME', '')}".strip()
        title = lead.get("TITLE", "")
        status = lead.get("STATUS_ID", "")
        print(f"  [{lead['ID']}] {title} | {name} | Status: {status}")
