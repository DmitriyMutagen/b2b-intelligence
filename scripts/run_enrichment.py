"""Quick batch enrichment via API."""
import requests

API = "http://localhost:8001/api/v1"

print("Starting batch enrichment...")
r = requests.post(f"{API}/enrich/batch?limit=672", timeout=60)
data = r.json()

enriched = data.get("enriched", 0)
results = data.get("results", [])
print(f"Enriched: {enriched} companies")

# Show top 10 by score
top = sorted(results, key=lambda x: -x["lead_score"])[:15]
print(f"\nTop 15 by Lead Score:")
for x in top:
    print(f"  {x['name']:35s} Score: {x['lead_score']}")

# Stats
scores = [x["lead_score"] for x in results]
hot = len([s for s in scores if s >= 70])
warm = len([s for s in scores if 40 <= s < 70])
cold = len([s for s in scores if s < 40])
print(f"\nDistribution: Hot(70+): {hot} | Warm(40-69): {warm} | Cold(<40): {cold}")

# Verify API stats updated
stats = requests.get(f"{API}/stats").json()
print(f"\nAPI Stats: {stats}")
