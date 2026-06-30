"""
One-time backfill: scrape and rate all CBRT speeches from BIS (2021–present).

Run: python backfill_cbrt.py
"""
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.environ.get("OPENAI_API_KEY"):
    sys.exit("Error: OPENAI_API_KEY not set.")

from scraper_cbrt import get_all_cbrt_speeches, save_rating, DB_PATH
from rater import rate_speech
from classify_relevance_llm import run_classification
from report_cbrt_filtered import generate_cbrt_filtered_report


def main():
    today = datetime.now()
    start_year = 2016  # full history from TCMB site

    print(f"=== CBRT Backfill: {start_year}–{today.year} ===")
    speeches = get_all_cbrt_speeches(start_year=start_year)
    print(f"\n{len(speeches)} speeches to rate\n")

    errors = 0
    for i, sp in enumerate(speeches, 1):
        print(f"[{i}/{len(speeches)}] {sp['speaker']} | {sp['date']} | {sp['title'][:55]}")
        try:
            lang = sp.get("language", "en")
            body_en = sp.get("body_en") or ""
            if lang != "en" and not body_en:
                from translator import translate_speech
                body_en = translate_speech(sp["body"], lang, title=sp["title"], speaker=sp["speaker"])
                time.sleep(0.2)
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="CBRT", db_path=str(DB_PATH),
                                 language=lang, body_en=body_en)
            now = datetime.now(timezone.utc).isoformat()
            save_rating(sp["url"], rating["score"], rating["justification"], now,
                        body_en=body_en if body_en else None)
            print(f"  Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"  Error: {e}")
            errors += 1
        time.sleep(0.3)

    print(f"\nDone. {len(speeches) - errors} rated, {errors} errors.")
    run_classification(bank="CBRT")
    generate_cbrt_filtered_report()


if __name__ == "__main__":
    main()
