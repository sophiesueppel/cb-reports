"""
Backfill topic_scores for speeches in the last 12 months (default).

Only the last 12 months matter — that's all the theme charts show.
Use --all to score the full history (much larger, rarely needed).

Usage:
    python backfill_topic_scores.py                 # last 12 months (~200 speeches)
    python backfill_topic_scores.py --all           # full history (~1900 speeches)
    python backfill_topic_scores.py --bank ECB      # single bank, last 12 months
"""
import json
import os
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv(Path(__file__).parent / ".env")

DB_PATH = Path("data/speeches.db")


def _ensure_column(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    if "topic_scores" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN topic_scores TEXT")
        conn.commit()


def run_backfill(all_history: bool = False, bank: str = None) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")

    from rater import score_topics

    today  = date.today()
    cutoff = date(today.year - 1, today.month, today.day).isoformat()

    conn = sqlite3.connect(str(DB_PATH))
    _ensure_column(conn)

    query = """
        SELECT url, title, speaker, central_bank, body, body_en
        FROM speeches
        WHERE score > 0
          AND topic_scores IS NULL
          AND body IS NOT NULL AND body != '' AND body != 'nan'
    """
    params = []
    if not all_history:
        query += " AND date >= ?"
        params.append(cutoff)
    if bank:
        query += " AND central_bank = ?"
        params.append(bank)
    query += " ORDER BY date DESC"

    rows = conn.execute(query, params).fetchall()
    scope = "full history" if all_history else f"last 12 months (since {cutoff})"
    print(f"Found {len(rows)} speeches to score — {scope}{f', bank={bank}' if bank else ''}.")

    errors = 0
    for i, (url, title, speaker, central_bank, body, body_en) in enumerate(rows, 1):
        text = (body_en or body or "").strip()
        if not text:
            continue
        print(f"[{i}/{len(rows)}] {central_bank} | {speaker[:30]} | {title[:50]}", end=" ")
        try:
            scores = score_topics(text, title=title or "", bank=central_bank or "")
            conn.execute("UPDATE speeches SET topic_scores=? WHERE url=?",
                         (json.dumps(scores), url))
            conn.commit()
            flagged = [k for k, v in scores.items() if v == 1]
            print(f"-> {flagged or 'none'}")
        except Exception as e:
            print(f"-> ERROR: {e}")
            errors += 1
        time.sleep(0.3)

    conn.close()
    print(f"\nDone. {len(rows) - errors} scored, {errors} errors.")


if __name__ == "__main__":
    all_history = "--all" in sys.argv
    bank = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg.startswith("--bank="):
            bank = arg.split("=")[1]
        elif arg == "--bank" and i < len(sys.argv) - 1:
            bank = sys.argv[i + 1]

    run_backfill(all_history=all_history, bank=bank)
