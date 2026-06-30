"""
Batch-rate BoE MPC speeches from the last 5 years that have full text but no score.
Run this after fix_boe_bodies.py has finished.

Only rates speeches where:
  - central_bank = 'Bank of England'
  - date >= 5 years ago
  - speaker was an MPC member on that date (uses was_mpc_member)
  - body >= 500 chars (has real content)
  - score IS NULL
"""
import os
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from rater import rate_speech
from scraper_boe import was_mpc_member, save_rating, DB_PATH

load_dotenv(Path(__file__).parent / ".env")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")

    today = date.today()
    cutoff = date(today.year - 5, today.month, today.day).isoformat()

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT url, speaker, date, title, body FROM speeches "
        "WHERE central_bank='Bank of England' "
        "  AND score IS NULL "
        "  AND date >= ? "
        "  AND length(body) >= 500 "
        "ORDER BY date DESC",
        (cutoff,),
    ).fetchall()
    conn.close()

    # Filter to actual MPC members on the date of the speech
    to_rate = [r for r in rows if was_mpc_member(r[1], r[2])]
    skipped = len(rows) - len(to_rate)

    print(f"Speeches to rate: {len(to_rate)}  (skipped {skipped} non-MPC speakers)")
    print(f"Date range: {cutoff} to today")
    print()

    rated = 0
    errors = 0

    for i, (url, speaker, speech_date, title, body) in enumerate(to_rate, 1):
        print(f"[{i}/{len(to_rate)}] {speech_date} | {speaker} | {title[:55]}", flush=True)
        try:
            result = rate_speech(title, speaker, speech_date, body,
                                bank="Bank of England", db_path=str(DB_PATH))
            score = result["score"]
            justification = result["justification"]
            rated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            save_rating(url, score, justification, rated_at)
            print(f"  Score: {score}/10 — {justification[:80]}", flush=True)
            rated += 1
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            errors += 1
        time.sleep(0.3)

    print(f"\nDone. {rated} rated, {errors} errors.")


if __name__ == "__main__":
    main()
