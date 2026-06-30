import json, sqlite3
from pathlib import Path

conn = sqlite3.connect("data/speeches.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT url, date, speaker, title, score, justification, central_bank "
    "FROM speeches ORDER BY date DESC, central_bank, speaker"
).fetchall()
conn.close()

MAX_TITLE = 250   # truncate anything longer than this (body-in-title artifacts)
MAX_JUST = 800    # truncate long justifications

data = []
bad_titles = 0
for r in rows:
    title = (r["title"] or "").strip()
    if len(title) > MAX_TITLE:
        title = title[:MAX_TITLE].rstrip() + "…"
        bad_titles += 1
    d = {
        "u": r["url"] or "",
        "d": r["date"] or "",
        "s": r["speaker"] or "",
        "t": title,
        "c": r["central_bank"] or "",
    }
    if r["score"] is not None:
        d["sc"] = r["score"]
    if r["justification"]:
        j = r["justification"][:MAX_JUST]
        d["j"] = j
    data.append(d)

out = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
Path("data/viewer_export_full.json").write_text(out, encoding="utf-8")
rated = sum(1 for r in data if "sc" in r)
print(f"Exported {len(data)} speeches, {len(out)/1024:.0f} KB")
print(f"Rated: {rated}, Unrated: {len(data)-rated}")
print(f"Fixed {bad_titles} oversized titles")
