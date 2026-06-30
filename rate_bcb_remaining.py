import sys, time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sqlite3
from rater import rate_speech
from scraper_bcb import save_rating

DB = Path(__file__).parent / "data/speeches.db"

conn = sqlite3.connect(str(DB))
rows = conn.execute(
    "SELECT url, date, speaker, title, body FROM speeches "
    "WHERE central_bank='BCB' AND score IS NULL AND body IS NOT NULL AND body != '' "
    "ORDER BY date DESC"
).fetchall()
conn.close()
print(f"{len(rows)} unrated BCB speeches to rate")

errors = 0
for i, (url, date, speaker, title, body) in enumerate(rows, 1):
    print(f"[{i}/{len(rows)}] {speaker} | {date} | {title[:55]}")
    try:
        r = rate_speech(title, speaker, date, body, bank="BCB", db_path=str(DB))
        now = datetime.now(timezone.utc).isoformat()
        save_rating(url, r["score"], r["justification"], now)
        print(f"  {r['score']}/10 -- {r['justification'][:70]}...")
    except Exception as e:
        print(f"  Error: {e}")
        errors += 1
    time.sleep(0.3)

print(f"Done. {len(rows)-errors} rated, {errors} errors.")
