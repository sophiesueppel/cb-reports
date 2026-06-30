"""Run Riksbank historical batch scrape+rate."""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scraper_riksbank import get_all_riksbank_speeches, _RIKSBANK_CURRENT, ALL_RIKSBANK, save_rating
from rater import rate_speech
from classify_relevance_llm import run_classification
from report_riksbank_filtered import generate_riksbank_filtered_report
from datetime import datetime, timezone, date as _date
import sqlite3, time, os
from pathlib import Path as P

DB = P(os.environ.get("CB_DB_PATH", "data/speeches.db"))
start_year = int(sys.argv[1]) if len(sys.argv) > 1 else 2021
current_year = datetime.now().year
cutoff = _date(current_year - 5, _date.today().month, _date.today().day).isoformat()

print(f"\n--- Riksbank batch ({start_year}-{current_year}) ---")
new_speeches = get_all_riksbank_speeches(start_year=start_year, end_year=current_year)

# Also pick up stored-but-unrated speeches for all historical members
conn = sqlite3.connect(str(DB), timeout=30)
conn.execute("PRAGMA busy_timeout=30000")
unrated = conn.execute(
    "SELECT url, date, speaker, title, body FROM speeches "
    "WHERE central_bank='Riksbank' AND score IS NULL AND date >= ? AND body IS NOT NULL AND body != ''",
    (cutoff,),
).fetchall()
conn.close()

already = {s["url"] for s in new_speeches}
for url, date, speaker, title, body in unrated:
    if url not in already and speaker in ALL_RIKSBANK:
        new_speeches.append({"url": url, "date": date, "speaker": speaker, "title": title, "body": body})

to_rate = [s for s in new_speeches if s.get("date", "") >= cutoff]
print(f"  {len(to_rate)} speeches to rate (last 5 years)")

from translator import translate_speech

errors = 0
for i, sp in enumerate(to_rate, 1):
    print(f"[{i}/{len(to_rate)}] {sp['speaker']} | {sp['date']} | {sp['title'][:55]}")
    if not sp.get("body"):
        print("  Skipped - no text")
        continue
    try:
        lang = sp.get("language", "en")
        body_en = sp.get("body_en") or ""

        if lang != "en" and not body_en:
            print(f"  Translating ({lang}) ...")
            body_en = translate_speech(sp["body"], lang, title=sp["title"], speaker=sp["speaker"])
            time.sleep(0.2)

        r = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                        bank="Riksbank", db_path=str(DB),
                        language=lang, body_en=body_en)
        now = datetime.now(timezone.utc).isoformat()
        save_rating(sp["url"], r["score"], r["justification"], now,
                    body_en=body_en if body_en else None)
        print(f"  {r['score']}/10 -- {r['justification'][:70]}...")
    except Exception as e:
        print(f"  Error: {e}")
        errors += 1
    time.sleep(0.3)

print(f"\nDone. {len(to_rate)-errors} rated, {errors} errors.")
run_classification(bank="Riksbank")
generate_riksbank_filtered_report()
