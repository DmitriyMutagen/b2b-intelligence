"""Test Bitrix24 webhook — check permissions and pull sample data."""
import requests
import json

WEBHOOK = "https://soulway.bitrix24.ru/rest/1/9pje2rjiwussuxlx/"

def call_b24(method, params=None):
    """Call Bitrix24 REST API method."""
    url = f"{WEBHOOK}{method}.json"
    try:
        r = requests.get(url, params=params or {}, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

print("=" * 60)
print("Bitrix24 Webhook Verification")
print("=" * 60)

# 1. Check profile (who owns this webhook)
print("\n1. PROFILE")
profile = call_b24("profile")
if "result" in profile:
    p = profile["result"]
    print(f"   User: {p.get('NAME', '?')} {p.get('LAST_NAME', '?')}")
    print(f"   Email: {p.get('EMAIL', '?')}")
    print(f"   ID: {p.get('ID', '?')}")
else:
    print(f"   Error: {profile}")

# 2. Check available scopes
print("\n2. AVAILABLE SCOPES")
scopes = call_b24("scope")
if "result" in scopes:
    scope_list = scopes["result"]
    print(f"   Total scopes: {len(scope_list)}")
    # Show CRM-related scopes
    crm_scopes = [s for s in scope_list if "crm" in s.lower()]
    print(f"   CRM scopes: {crm_scopes}")
else:
    print(f"   Error: {scopes}")

# 3. Count CRM leads
print("\n3. CRM LEADS")
leads = call_b24("crm.lead.list", {"select[]": "ID", "limit": 1})
if "result" in leads:
    total = leads.get("total", len(leads["result"]))
    print(f"   Total leads: {total}")
else:
    print(f"   Error: {leads}")

# 4. Count CRM contacts
print("\n4. CRM CONTACTS")
contacts = call_b24("crm.contact.list", {"select[]": "ID", "limit": 1})
if "result" in contacts:
    total = contacts.get("total", len(contacts["result"]))
    print(f"   Total contacts: {total}")
else:
    print(f"   Error: {contacts}")

# 5. Count CRM deals
print("\n5. CRM DEALS")
deals = call_b24("crm.deal.list", {"select[]": "ID", "limit": 1})
if "result" in deals:
    total = deals.get("total", len(deals["result"]))
    print(f"   Total deals: {total}")
else:
    print(f"   Error: {deals}")

# 6. Count CRM companies
print("\n6. CRM COMPANIES")
companies = call_b24("crm.company.list", {"select[]": "ID", "limit": 1})
if "result" in companies:
    total = companies.get("total", len(companies["result"]))
    print(f"   Total companies: {total}")
else:
    print(f"   Error: {companies}")

# 7. Telephony (call records)
print("\n7. TELEPHONY")
calls = call_b24("voximplant.statistic.get", {"LIMIT": 1})
if "result" in calls:
    total = calls.get("total", 0)
    print(f"   Call records: {total}")
else:
    print(f"   Telephony status: {calls.get('error_description', 'N/A')}")

print("\n" + "=" * 60)
print("WEBHOOK VERIFICATION COMPLETE")
print("=" * 60)
