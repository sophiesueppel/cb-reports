"""
Ingest Federal Reserve *testimony* (separate from speeches) into the DB, rated the
same way as speeches. EXPERIMENTAL — testimony is currently shown only on the test
report (report_fed_test.py); the live Fed report filters testimony out.

Testimony lives at /newsevents/testimony/{year}-testimony.htm and the individual
pages parse with the normal scraper.get_speech(). Rows are stored with
central_bank='Federal Reserve' and a url under /newsevents/testimony/, which is how
the reports tell testimony from speeches.

Run:  python ingest_fed_testimony.py
"""
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone, date as _date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

from scraper import HEADERS, BASE_URL, get_speech
from rater import rate_speech, extract_evidence_quotes

DB = Path("data/speeches.db")


def list_testimony_urls() -> list:
    urls = []
    yr = datetime.now().year
    for y in range(yr - 5, yr + 1):
        try:
            r = requests.get(f"{BASE_URL}/newsevents/testimony/{y}-testimony.htm",
                             headers=HEADERS, timeout=20)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        for u in dict.fromkeys(re.findall(r'href="(/newsevents/testimony/\w+\.htm)"', r.text)):
            urls.append(BASE_URL + u)
    return list(dict.fromkeys(urls))


def _ensure_cols(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    for c in ("topic_scores", "evidence_quotes"):
        if c not in cols:
            conn.execute(f"ALTER TABLE speeches ADD COLUMN {c} TEXT")
    conn.commit()


def ingest_new_testimony(quiet: bool = False) -> list:
    """Scrape Fed testimony listings, rate any not already in the DB, and store them
    (with topic scores + evidence quotes). Idempotent — only new URLs are processed.
    Returns the list of newly-added row dicts (for the daily pipeline's downstream steps)."""
    conn = sqlite3.connect(str(DB), timeout=30)
    _ensure_cols(conn)
    have = {r[0] for r in conn.execute("SELECT url FROM speeches")}
    urls = list_testimony_urls()
    todo = [u for u in urls if u not in have]
    if not quiet:
        print(f"{len(urls)} Fed testimony URLs found, {len(todo)} new to rate ...")

    added = []
    for i, u in enumerate(todo, 1):
        try:
            sp = get_speech(u)
        except Exception as e:
            if not quiet:
                print(f"  ! parse failed {u}: {e}")
            continue
        if not sp.text or len(sp.text) < 300:
            continue
        try:
            rating = rate_speech(sp.title, sp.speaker, sp.date, sp.text,
                                 bank="Federal Reserve", db_path=str(DB))
        except Exception as e:
            if not quiet:
                print(f"  ! rate failed {u}: {e}")
            continue
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO speeches (url,date,speaker,title,score,justification,rated_at,body,central_bank,country) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(url) DO UPDATE SET score=excluded.score, justification=excluded.justification, "
            "rated_at=excluded.rated_at, body=excluded.body",
            (u, sp.date, sp.speaker, sp.title, rating["score"], rating["justification"],
             now, sp.text, "Federal Reserve", "USA"),
        )
        ts = rating.get("topic_scores")
        if ts is not None:
            conn.execute("UPDATE speeches SET topic_scores=? WHERE url=?", (json.dumps(ts), u))
        try:
            eq = extract_evidence_quotes(sp.text, rating["score"], rating["justification"], sp.title)
        except Exception:
            eq = []
        conn.execute("UPDATE speeches SET evidence_quotes=? WHERE url=?", (json.dumps(eq), u))
        conn.commit()
        added.append({"url": u, "date": sp.date, "speaker": sp.speaker, "title": sp.title,
                      "score": rating["score"], "justification": rating["justification"],
                      "central_bank": "Federal Reserve", "country": "USA"})
        if not quiet:
            print(f"  [{i}/{len(todo)}] {sp.date} | {sp.speaker[:24]:24} | score {rating['score']} | {sp.title[:42]}")
        time.sleep(0.2)

    conn.close()
    return added


def main():
    added = ingest_new_testimony()
    print(f"done — {len(added)} new testimony item(s) added")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
