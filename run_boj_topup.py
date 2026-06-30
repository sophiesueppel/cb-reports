"""Rate any unrated BoJ Policy Board speeches within the last 5 years, then regenerate report."""
import sys, time
from datetime import date, datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import sqlite3
from rater import rate_speech
from scraper_boj import save_rating, ALL_BOJ_BOARD
from report_boj import generate_boj_report

DB_PATH = Path("data/speeches.db")
today = date.today()
cutoff = date(today.year - 5, today.month, today.day).isoformat()

conn = sqlite3.connect(str(DB_PATH))
rows = conn.execute(
    "SELECT url, date, speaker, title, body FROM speeches "
    "WHERE central_bank='Bank of Japan' AND score IS NULL "
    "AND date >= ? AND body IS NOT NULL AND body != ''",
    (cutoff,),
).fetchall()
conn.close()

to_rate = [
    {"url": r[0], "date": r[1], "speaker": r[2], "title": r[3], "body": r[4]}
    for r in rows if r[2] in ALL_BOJ_BOARD
]

print(f"{len(to_rate)} unrated BoJ speeches to rate (since {cutoff})")

errors = 0
for i, sp in enumerate(to_rate, 1):
    print(f"[{i}/{len(to_rate)}] {sp['speaker']} | {sp['date']} | {sp['title'][:55]}")
    try:
        rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                             bank="Bank of Japan", db_path=str(DB_PATH))
        now = datetime.now(timezone.utc).isoformat()
        save_rating(sp["url"], rating["score"], rating["justification"], now)
        print(f"  Score: {rating['score']}/10 — {rating['justification'][:70]}...")
    except Exception as e:
        print(f"  Error: {e}")
        errors += 1
    time.sleep(0.3)

print(f"\nDone. {len(to_rate) - errors} rated, {errors} errors.")
generate_boj_report()
print("Report regenerated.")
