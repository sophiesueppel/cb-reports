"""Run SARB historical batch scrape+rate.

Usage:
    python run_sarb_batch.py [start_year]

If the SARB listing page JS is down, the scraper will raise a RuntimeError.
In that case, seed URLs manually:

    from scraper_sarb import get_all_sarb_speeches_from_urls
    urls = [
        "https://www.resbank.co.za/.../2026/cassim-yield-curve",
        ...
    ]
    get_all_sarb_speeches_from_urls(urls)
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scraper_sarb import get_all_sarb_speeches, ALL_SARB, save_rating
from rater import rate_speech
from classify_relevance_llm import run_classification
from report_sarb_filtered import generate_sarb_filtered_report
from datetime import datetime, timezone, date as _date
import sqlite3, time
from pathlib import Path as P

DB = P("data/speeches.db")
start_year = int(sys.argv[1]) if len(sys.argv) > 1 else 2021
current_year = datetime.now().year
today = _date.today()
cutoff = _date(today.year - 5, today.month, today.day).isoformat()

print(f"\n--- SARB batch ({start_year}-{current_year}) ---")

try:
    new_speeches = get_all_sarb_speeches(start_year=start_year, end_year=current_year)
except RuntimeError as e:
    print(f"  WARNING: {e}")
    print("  Proceeding with stored-but-unrated speeches only.")
    new_speeches = []

# Pick up stored-but-unrated speeches for all historical members
conn = sqlite3.connect(str(DB))
unrated = conn.execute(
    "SELECT url, date, speaker, title, body FROM speeches "
    "WHERE central_bank='SARB' AND score IS NULL AND date >= ? "
    "AND body IS NOT NULL AND body != ''",
    (cutoff,),
).fetchall()
conn.close()

already = {s["url"] for s in new_speeches}
for url, date, speaker, title, body in unrated:
    if url not in already and speaker in ALL_SARB:
        new_speeches.append({"url": url, "date": date, "speaker": speaker,
                             "title": title, "body": body})

to_rate = [s for s in new_speeches if s.get("date", "") >= cutoff]
print(f"  {len(to_rate)} speeches to rate (last 5 years)")

errors = 0
for i, sp in enumerate(to_rate, 1):
    print(f"[{i}/{len(to_rate)}] {sp['speaker']} | {sp['date']} | {sp['title'][:55]}")
    if not sp.get("body"):
        print("  Skipped — no text")
        continue
    try:
        r = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                        bank="SARB", db_path=str(DB))
        now = datetime.now(timezone.utc).isoformat()
        save_rating(sp["url"], r["score"], r["justification"], now)
        print(f"  {r['score']}/10 -- {r['justification'][:70]}...")
    except Exception as e:
        print(f"  Error: {e}")
        errors += 1
    time.sleep(0.3)

print(f"\nDone. {len(to_rate)-errors} rated, {errors} errors.")
run_classification(bank="SARB")
generate_sarb_filtered_report()
