"""
Backfill `evidence_quotes` — verbatim hawkish/dovish supporting quotes per speech.

For each DIRECTIONAL speech (score 1–3 dovish, or 7–10 hawkish) an LLM pulls 2–4
quotes copied word-for-word from the speech; each is validated as a real substring
before being stored (see rater.extract_evidence_quotes). Neutral (4–6) and off-topic
(0) speeches get an empty list so they aren't retried.

Idempotent: only rows where evidence_quotes IS NULL are processed, so it can resume.

Run:
  python backfill_evidence_quotes.py                 # all banks
  python backfill_evidence_quotes.py "Federal Reserve"   # one bank
  python backfill_evidence_quotes.py "Federal Reserve" 20 # + row cap (testing)
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from rater import extract_evidence_quotes

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))


def _ensure_column(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    if "evidence_quotes" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN evidence_quotes TEXT")
        conn.commit()


def backfill_quotes(bank: str = None, limit: int = None,
                    db_path=None, quiet: bool = False) -> tuple:
    """Extract & store evidence quotes for directional speeches lacking them.
    Idempotent (only rows where evidence_quotes IS NULL). Returns (processed, kept).

    Safe to call from the daily pipeline: with no NULL rows it's a no-op. Off-topic
    and neutral directional-scored rows still get an empty list so they aren't retried."""
    path = Path(db_path) if db_path else DB_PATH
    if not os.environ.get("OPENAI_API_KEY") or not path.exists():
        return (0, 0)

    conn = sqlite3.connect(str(path))
    _ensure_column(conn)

    where = ("WHERE ((score BETWEEN 1 AND 3) OR score >= 7) "
             "AND body IS NOT NULL AND length(body) > 500 "
             "AND evidence_quotes IS NULL")
    params = []
    if bank:
        where += " AND central_bank = ?"
        params.append(bank)
    sql = (f"SELECT url, title, score, justification, body, body_en, language "
           f"FROM speeches {where} ORDER BY date DESC")
    if limit:
        sql += f" LIMIT {limit}"

    rows = conn.execute(sql, params).fetchall()
    total = len(rows)
    if not quiet:
        print(f"Backfilling evidence quotes for {total} speech(es)"
              + (f" [{bank}]" if bank else "") + " ...")

    done = kept = 0
    for url, title, score, just, body, body_en, language in rows:
        # For non-English speeches, extract from the English translation so the
        # quotes read in English (matching the rest of the report) and validate
        # against the same text the reader sees. Falls back to the original body.
        text = body_en if (language and language != "en" and body_en and body_en.strip()) else body
        try:
            quotes = extract_evidence_quotes(text, score, just or "", title or "")
        except Exception as e:
            if not quiet:
                print(f"  ! {title[:60]!r}: {e}")
            continue
        conn.execute("UPDATE speeches SET evidence_quotes=? WHERE url=?",
                     (json.dumps(quotes), url))
        done += 1
        kept += len(quotes)
        if done % 10 == 0:
            conn.commit()
            if not quiet:
                print(f"  {done}/{total} done ({kept} quotes so far)")

    conn.commit()
    conn.close()
    if not quiet:
        print(f"Done. {done}/{total} speeches processed, {kept} quotes stored.")
    return (done, kept)


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set (check .env).")
    if not DB_PATH.exists():
        sys.exit(f"No database at {DB_PATH}")
    bank = sys.argv[1] if len(sys.argv) > 1 else None
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    backfill_quotes(bank, limit)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
