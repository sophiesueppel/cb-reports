"""
CNB backfill:
- Scrape and store ALL speeches from both Czech and English listings (2000–present)
- Translate non-English speeches (store in body_en)
- Rate speeches from 2021 onwards using the English translation
"""
import sys, time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sqlite3
from scraper_cnb import get_all_cnb_speeches, save_rating, DB_PATH
from rater import rate_speech
from translator import translate_speech

RATE_FROM_YEAR = 2021

# Step 1: scrape full history — Czech + English listings, 2000–present
print("=== Scraping CNB (Czech + English listings) 2000–present ===")
all_new = get_all_cnb_speeches(start_year=2000)
print(f"\n{len(all_new)} new speeches scraped and stored")

# Step 2: translate + rate speeches from RATE_FROM_YEAR onwards
conn = sqlite3.connect(str(DB_PATH))
unrated = conn.execute(
    "SELECT url, date, speaker, title, body, language, body_en FROM speeches "
    "WHERE central_bank='CNB' AND score IS NULL "
    "AND body IS NOT NULL AND LENGTH(body) >= 800 "
    "AND date >= ?",
    (f"{RATE_FROM_YEAR}-01-01",),
).fetchall()
conn.close()

to_rate = [
    {"url": u, "date": d, "speaker": sp, "title": t, "body": b,
     "language": lang or "cs", "body_en": ben}
    for u, d, sp, t, b, lang, ben in unrated
]
print(f"{len(to_rate)} speeches to rate (from {RATE_FROM_YEAR} onwards)")

errors = 0
for i, rec in enumerate(to_rate, 1):
    print(f"[{i}/{len(to_rate)}] {rec['speaker']} | {rec['date']} | {rec['title'][:55]}")
    try:
        lang = rec.get("language", "cs")
        body_en = rec.get("body_en") or ""

        # Translate if not English and not yet translated
        if lang != "en" and not body_en:
            print(f"  Translating ({lang}) ...")
            body_en = translate_speech(rec["body"], lang, title=rec["title"], speaker=rec["speaker"])
            time.sleep(0.2)

        r = rate_speech(
            rec["title"], rec["speaker"], rec["date"], rec["body"],
            bank="CNB", db_path=str(DB_PATH),
            language=lang, body_en=body_en,
        )
        now = datetime.now(timezone.utc).isoformat()
        save_rating(rec["url"], r["score"], r["justification"], now,
                    body_en=body_en if body_en else r.get("body_en"))
        print(f"  {r['score']}/10 — {r['justification'][:70]}...")
    except Exception as e:
        print(f"  Error: {e}")
        errors += 1
    time.sleep(0.3)

print(f"\nDone. {len(to_rate) - errors} rated, {errors} errors.")
