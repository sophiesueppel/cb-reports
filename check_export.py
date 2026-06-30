import json

with open("data/viewer_export_full.json", encoding="utf-8") as f:
    content = f.read()
print(f"File size: {len(content)/1024:.0f} KB")

# Parse first 3 records
first_bracket = content.index("[")
# Find end of 3rd record
data = json.loads(content)
print(f"Total records: {len(data)}")

# Check size distribution
sizes = [len(json.dumps(r, separators=(",",":"))) for r in data[:100]]
sizes.sort(reverse=True)
print(f"Top 10 record sizes: {sizes[:10]}")
print(f"Avg of first 100: {sum(sizes)/len(sizes):.0f}")

# Show largest record
idx = max(range(len(data[:100])), key=lambda i: len(json.dumps(data[i])))
r = data[idx]
print(f"\nLargest record:")
for k,v in r.items():
    v_str = str(v)
    print(f"  {k}: {len(v_str)} chars = {v_str[:80]}")
