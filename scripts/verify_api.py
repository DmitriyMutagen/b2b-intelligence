"""Quick API verification script."""
import requests
import json

API = "http://localhost:8001/api/v1"

print("=" * 60)
print("B2B Intelligence Platform — API Verification")
print("=" * 60)

# 1. Stats
print("\n1. DASHBOARD STATS")
stats = requests.get(f"{API}/stats").json()
for k, v in stats.items():
    print(f"   {k}: {v}")

# 2. Companies
print("\n2. TOP 5 COMPANIES BY REVENUE")
data = requests.get(f"{API}/companies", params={"limit": 5}).json()
print(f"   Total in DB: {data['total']}")
for c in data["items"]:
    rev = f"{c['revenue_total']:,.0f}" if c["revenue_total"] else "N/A"
    mp = []
    if c["wb_present"]: mp.append("WB")
    if c["ozon_present"]: mp.append("Ozon")
    print(f"   [{c['id']}] {c['name']:30s} | {rev:>15s} RUB | {', '.join(mp) or '-'}")

# 3. Single Dossier
print("\n3. DOSSIER (Company #1)")
dossier = requests.get(f"{API}/companies/1").json()
company = dossier["company"]
print(f"   Name: {company['name']}")
print(f"   Revenue: {company['revenue_total']}")
print(f"   Persons: {len(dossier['persons'])}")
print(f"   Contacts: {len(dossier['contacts'])}")
print(f"   Intelligence: {'Yes' if dossier.get('intelligence') else 'Pending'}")

# 4. Profile
print("\n4. COMPANY PROFILE (Our Company)")
profile = requests.get(f"{API}/profile").json()
print(f"   Company: {profile['company_name']}")
print(f"   Industry: {profile['industry']}")
print(f"   Key facts: {profile['key_facts']['formulas']}")

# 5. Documents endpoint
print("\n5. DOCUMENTS ENDPOINT")
docs = requests.get(f"{API}/documents").json()
print(f"   Uploaded docs: {len(docs)}")

print("\n" + "=" * 60)
print("ALL ENDPOINTS VERIFIED OK")
print("=" * 60)
