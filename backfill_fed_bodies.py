"""
Re-fetches body text for rated Fed speeches that have an empty body field.
Run once: python backfill_fed_bodies.py
"""

import sqlite3
import sys
import time
from pathlib import Path

from scraper import get_speech

DB_PATH = Path("data/speeches.db")


def backfill(delay: float = 0.5) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT url FROM speeches "
        "WHERE central_bank='Federal Reserve' AND score IS NOT NULL "
        "AND (body IS NULL OR TRIM(body)='') "
        "ORDER BY date DESC"
    ).fetchall()

    total = len(rows)
    print(f"  {total} rated Fed speeches need body text")
    done, empty, errors = 0, 0, 0

    for i, (url,) in enumerate(rows, 1):
        try:
            speech = get_speech(url)
            if speech.text.strip():
                conn.execute(
                    "UPDATE speeches SET body=? WHERE url=?",
                    (speech.text, url),
                )
                if i % 50 == 0:
                    conn.commit()
                done += 1
                print(f"[{i}/{total}] {len(speech.text):>6,}c  {url[-40:]}")
            else:
                empty += 1
                print(f"[{i}/{total}] EMPTY      {url[-40:]}")
        except Exception as e:
            errors += 1
            print(f"[{i}/{total}] ERROR      {url[-40:]}  — {e}")

        time.sleep(delay)

    conn.commit()
    conn.close()
    print(f"\nDone. {done} bodies stored, {empty} still empty, {errors} errors.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    backfill()
