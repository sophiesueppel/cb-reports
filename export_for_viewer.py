import json, sqlite3
from pathlib import Path

conn = sqlite3.connect("data/speeches.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT url, date, speaker, title, score, justification, central_bank "
    "FROM speeches WHERE score IS NOT NULL ORDER BY date DESC"
).fetchall()
conn.close()

data = [dict(r) for r in rows]
Path("data/viewer_export.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
print(f"Exported {len(data)} rated speeches")
