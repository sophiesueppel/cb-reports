"""Rate BoJ speeches that are stored but unrated, within the 5-year window."""
import os
import sys
import time
import sqlite3
from datetime import datetime, timezone, date as _date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.environ.get("OPENAI_API_KEY"):
    sys.exit("Error: OPENAI_API_KEY not set.")

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))
current_year = datetime.now().year
cutoff = _date(current_year - 5, _date.today().month, _date.today().day).isoformat()
print(f"DB: {DB_PATH}")
print(f"5-year cutoff: {cutoff}")

conn = sqlite3.connect(str(DB_PATH), timeout=30)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")

unrated = conn.execute("""
    SELECT url, date, speaker, title, body, language, body_en
    FROM speeches
    WHERE central_bank='Bank of Japan' AND score IS NULL
      AND date >= ? AND body IS NOT NULL AND body != ''
    ORDER BY date
""", (cutoff,)).fetchall()
conn.close()

print(f"{len(unrated)} unrated BoJ speeches in window\n")

from rater import rate_speech
from scraper_boj import save_rating

errors = 0
for i, (url, date, speaker, title, body, lang, body_en) in enumerate(unrated, 1):
    lang = lang or "en"
    print(f"[{i}/{len(unrated)}] {speaker} | {date} | {title[:55]}")
    try:
        r = rate_speech(title, speaker, date, body,
                        bank="Bank of Japan", db_path=str(DB_PATH),
                        language=lang, body_en=body_en or "")
        now = datetime.now(timezone.utc).isoformat()
        # Use translation returned by rater if we didn't have one already
        stored_en = body_en or r.get("body_en") or None
        save_rating(url, r["score"], r["justification"], now, body_en=stored_en)
        print(f"  {r['score']}/10 — {r['justification'][:70]}...")
    except Exception as e:
        print(f"  Error: {e}")
        errors += 1
    time.sleep(0.3)

print(f"\nDone. {len(unrated)-errors} rated, {errors} errors.")
