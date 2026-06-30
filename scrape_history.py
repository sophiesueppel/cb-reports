"""Scrape all Fed speeches from 2011 to present — metadata + body, no rating."""
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from scraper import get_all_speech_urls, get_speech

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = Path("data/speeches.db")

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS speeches (
        url           TEXT PRIMARY KEY,
        date          TEXT,
        speaker       TEXT,
        title         TEXT,
        score         INTEGER,
        justification TEXT,
        rated_at      TEXT,
        body          TEXT,
        central_bank  TEXT,
        country       TEXT
    )
"""

START_YEAR = 2006
END_YEAR   = datetime.now().year


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(_CREATE_TABLE)
    # Migrate: add columns if missing
    existing = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    for col, defn in [("body", "TEXT"), ("central_bank", "TEXT"), ("country", "TEXT")]:
        if col not in existing:
            conn.execute(f"ALTER TABLE speeches ADD COLUMN {col} {defn}")
    conn.commit()
    return conn


def already_scraped() -> set[str]:
    conn = _conn()
    urls = {row[0] for row in conn.execute("SELECT url FROM speeches")}
    conn.close()
    return urls


def save_metadata(conn: sqlite3.Connection, url: str, date: str, speaker: str,
                  title: str, body: str) -> None:
    # INSERT OR IGNORE — don't overwrite existing rated speeches
    conn.execute(
        "INSERT OR IGNORE INTO speeches "
        "(url, date, speaker, title, body, central_bank, country) "
        "VALUES (?, ?, ?, ?, ?, 'Federal Reserve', 'USA')",
        (url, date, speaker, title, body),
    )
    conn.commit()


def run() -> None:
    print(f"Collecting speech URLs {START_YEAR}–{END_YEAR} ...")
    all_urls: list[str] = []
    for year in range(START_YEAR, END_YEAR + 1):
        batch = get_all_speech_urls(year)
        print(f"  {year}: {len(batch)} speeches")
        all_urls.extend(batch)

    scraped = already_scraped()
    to_fetch = [u for u in all_urls if u not in scraped]
    print(f"\n{len(scraped)} already in DB. {len(to_fetch)} new to scrape.\n")

    if not to_fetch:
        print("Nothing to do.")
        return

    conn = _conn()
    errors = saved = 0

    for i, url in enumerate(to_fetch, 1):
        try:
            speech = get_speech(url)
            save_metadata(conn, speech.url, speech.date, speech.speaker, speech.title, speech.text)
            saved += 1
            print(f"[{i}/{len(to_fetch)}] {speech.date} | {speech.speaker[:40]:40s} | {speech.title[:50]}")
        except Exception as e:
            print(f"[{i}/{len(to_fetch)}] ERROR {url.split('/')[-1]}: {e}")
            errors += 1
        time.sleep(0.4)

    conn.close()
    total = conn = sqlite3.connect(str(DB_PATH)).execute("SELECT COUNT(*) FROM speeches").fetchone()[0]
    print(f"\nDone. {saved} saved, {errors} errors. Database now has {total} speeches.")


if __name__ == "__main__":
    run()
