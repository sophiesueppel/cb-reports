import json

with open("data/viewer_export_full.json", encoding="utf-8") as f:
    data = json.load(f)

print(f"Records: {len(data)}")
sizes = [len(json.dumps(r, separators=(",",":"))) for r in data]
total = sum(sizes)
print(f"Total JSON size: {total/1024:.0f} KB")
print(f"Avg size: {total/len(sizes):.0f} bytes")
print(f"Max size: {max(sizes)} bytes")

# Find records with large justification
large_j = [(i, len(r.get("j","") or ""), r["c"]) for i, r in enumerate(data) if len(r.get("j","") or "") > 1000]
print(f"\nRecords with j > 1000 chars: {len(large_j)}")
if large_j:
    print("Sample:", large_j[:5])

# Field size totals
url_total = sum(len(r.get("u","") or "") for r in data)
t_total = sum(len(r.get("t","") or "") for r in data)
j_total = sum(len(r.get("j","") or "") for r in data)
print(f"\nURL total: {url_total/1024:.0f} KB")
print(f"Title total: {t_total/1024:.0f} KB")
print(f"Justification total: {j_total/1024:.0f} KB")
