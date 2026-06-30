"""
Backfill Riksbank speech bodies by downloading PDFs for speeches with short/missing text.
After updating bodies, re-rates any speech whose body meaningfully changed.
"""
import sys, sqlite3, time
from pathlib import Path
from datetime import datetime, timezone, date as _date
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scraper_riksbank import _fetch_speech_body, _download_pdf_text, _conn, ALL_RIKSBANK, save_rating, BASE
from rater import rate_speech
from classify_relevance_llm import run_classification
from report_riksbank_filtered import generate_riksbank_filtered_report

DB = Path("data/speeches.db")
MIN_BODY_LEN = 1500  # speeches shorter than this are likely stub intros missing PDF text

today = _date.today()
cutoff = _date(today.year - 5, today.month, today.day).isoformat()

conn = sqlite3.connect(str(DB))
# Fetch all Riksbank speeches with short bodies (these are the ones with just intro text)
short = conn.execute(
    "SELECT url, date, speaker, title, length(body) FROM speeches "
    "WHERE central_bank='Riksbank' AND (body IS NULL OR body='' OR length(body) < ?) "
    "ORDER BY date DESC",
    (MIN_BODY_LEN,),
).fetchall()
conn.close()

print(f"\n--- Riksbank PDF backfill ---")
print(f"  {len(short)} speeches with body < {MIN_BODY_LEN} chars")

updated = 0
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ))
    page = context.new_page()

    for i, (url, date, speaker, title, old_len) in enumerate(short, 1):
        print(f"[{i}/{len(short)}] {speaker} | {date} | {title[:50]} (was {old_len} chars)")
        try:
            body, date_iso, _ = _fetch_speech_body(page, url)
            if len(body) > (old_len or 0) + 200:
                conn = sqlite3.connect(str(DB))
                conn.execute(
                    "UPDATE speeches SET body=? WHERE url=?",
                    (body, url),
                )
                # Clear old rating so it gets re-rated with real content
                if date >= cutoff:
                    conn.execute(
                        "UPDATE speeches SET score=NULL, justification=NULL, rated_at=NULL, "
                        "relevant_to_mp=NULL, relevant_to_mp_source=NULL, relevant_to_mp_reason=NULL, "
                        "original_score=NULL "
                        "WHERE url=?",
                        (url,),
                    )
                conn.commit()
                conn.close()
                print(f"  Updated body: {old_len} -> {len(body)} chars")
                updated += 1
            else:
                print(f"  No PDF found or no improvement ({len(body)} chars) — kept as-is")
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(0.5)

    browser.close()

print(f"\n  {updated} speeches updated with PDF text")

# Re-rate speeches that now have bodies and are in the 5-year window
conn = sqlite3.connect(str(DB))
to_rate = conn.execute(
    "SELECT url, date, speaker, title, body FROM speeches "
    "WHERE central_bank='Riksbank' AND score IS NULL AND date >= ? "
    "AND body IS NOT NULL AND length(body) > 500",
    (cutoff,),
).fetchall()
conn.close()

print(f"\n  {len(to_rate)} speeches to re-rate")
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

print(f"\nDone. {len(to_rate)-errors} re-rated, {errors} errors.")

print("\nRunning relevance classifier...")
run_classification(bank="Riksbank")

print("\nGenerating report...")
generate_riksbank_filtered_report()
print("Done.")
