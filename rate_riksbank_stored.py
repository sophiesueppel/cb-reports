"""Rate all stored-but-unrated Riksbank speeches, classify, generate report."""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sqlite3, time
from datetime import datetime, timezone, date as _date

from scraper_riksbank import ALL_RIKSBANK, save_rating
from rater import rate_speech
from classify_relevance_llm import run_classification
from report_riksbank_filtered import generate_riksbank_filtered_report

DB = Path("data/speeches.db")

today = _date.today()
cutoff = _date(today.year - 5, today.month, today.day).isoformat()

conn = sqlite3.connect(str(DB))
unrated = conn.execute(
    "SELECT url, date, speaker, title, body FROM speeches "
    "WHERE central_bank='Riksbank' AND score IS NULL AND date >= ? "
    "AND body IS NOT NULL AND body != ''",
    (cutoff,),
).fetchall()
conn.close()

to_rate = [r for r in unrated if r[2] in ALL_RIKSBANK]
print(f"\n--- Riksbank rate-only pass ---")
print(f"  {len(to_rate)} unrated speeches in last 5 years (cutoff {cutoff})")

errors = 0
for i, (url, date, speaker, title, body) in enumerate(to_rate, 1):
    print(f"[{i}/{len(to_rate)}] {speaker} | {date} | {title[:55]}")
    try:
        r = rate_speech(title, speaker, date, body, bank="Riksbank", db_path=str(DB))
        now = datetime.now(timezone.utc).isoformat()
        save_rating(url, r["score"], r["justification"], now)
        print(f"  {r['score']}/10 -- {r['justification'][:70]}...")
    except Exception as e:
        print(f"  Error: {e}")
        errors += 1
    time.sleep(0.3)

print(f"\nDone. {len(to_rate)-errors} rated, {errors} errors.")

print("\nRunning relevance classifier...")
run_classification(bank="Riksbank")

print("\nGenerating Riksbank report...")
generate_riksbank_filtered_report()
print("Report written to report_riksbank_filtered.html")
