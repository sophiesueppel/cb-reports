import json

with open("data/viewer_export_full.json", encoding="utf-8") as f:
    data = json.load(f)

# Find records with huge fields
for i, r in enumerate(data):
    for k, v in r.items():
        if v and len(str(v)) > 5000:
            print(f"Record {i}: key={k}, len={len(str(v))}, central_bank={r.get('c')}, date={r.get('d')}")
            print(f"  First 200: {str(v)[:200]}")
