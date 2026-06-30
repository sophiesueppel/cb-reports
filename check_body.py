import sqlite3
conn = sqlite3.connect("data/speeches.db")
r = conn.execute("SELECT SUM(length(body)), COUNT(*) FROM speeches WHERE body IS NOT NULL AND body != ''").fetchone()
print(f"Total body text: {r[0]/1024/1024:.1f} MB across {r[1]} speeches")
r2 = conn.execute("SELECT AVG(length(body)) FROM speeches WHERE body IS NOT NULL AND body != ''").fetchone()
print(f"Avg body length: {r2[0]:.0f} chars")
# The export script outputs body too? Check our export
import json
sample = json.loads(open("data/viewer_export_full.json", encoding="utf-8").read()[:5000])
print("First record keys:", list(sample[0].keys()))
print("First record:", {k: str(v)[:80] for k,v in sample[0].items()})
conn.close()
