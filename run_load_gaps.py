"""Load historical speeches into the database WITHOUT rating them.

Covers:
  Fed   1996–2005  (~500 speeches, HTML)
  BoJ   1996–2001  (~50 speeches, PDF, via www2.boj.or.jp)
  BoJ   2011–2020  (~300 speeches, PDF, via www.boj.or.jp)
  BoJ   2002–2010  SKIPPED — permanently deleted, no archive
"""
import sqlite3
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path("data/speeches.db")

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

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


def _conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute(_CREATE_TABLE)
    cols = {r[1] for r in c.execute("PRAGMA table_info(speeches)")}
    for col in ("body", "central_bank", "country"):
        if col not in cols:
            c.execute(f"ALTER TABLE speeches ADD COLUMN {col} TEXT")
    c.commit()
    return c


def _existing(conn, bank):
    return {r[0] for r in conn.execute(
        "SELECT url FROM speeches WHERE central_bank=?", (bank,)
    )}


# ---------------------------------------------------------------------------
# Fed 1996-2005
# ---------------------------------------------------------------------------

def load_fed_gap(start_year=1996, end_year=2005):
    from scraper import get_all_speech_urls, get_speech

    print(f"\n=== Fed {start_year}–{end_year} ===")
    conn = _conn()
    existing = _existing(conn, "Federal Reserve")
    total_stored = 0

    for year in range(start_year, end_year + 1):
        print(f"  Fetching Fed {year} index ...")
        urls = get_all_speech_urls(year)
        print(f"    Found {len(urls)} URLs")
        year_stored = 0

        for url in urls:
            if url in existing:
                continue
            try:
                s = get_speech(url)
                conn.execute(
                    "INSERT OR IGNORE INTO speeches "
                    "(url, date, speaker, title, body, central_bank, country) "
                    "VALUES (?, ?, ?, ?, ?, 'Federal Reserve', 'USA')",
                    (s.url, s.date, s.speaker, s.title, s.text),
                )
                existing.add(url)
                year_stored += 1
                total_stored += 1
                time.sleep(0.3)
            except Exception as e:
                print(f"    ERROR {url}: {e}")

        conn.commit()
        print(f"    {year}: {year_stored} new stored (running total: {total_stored})")

    conn.close()
    print(f"\nFed gap done: {total_stored} speeches loaded")
    return total_stored


# ---------------------------------------------------------------------------
# BoJ historical (uses _scrape_year_index + _get_speech_text from scraper_boj)
# ---------------------------------------------------------------------------

def load_boj_gap(start_year, end_year, label):
    from scraper_boj import _scrape_year_index, _get_speech_text, _session, _conn as boj_conn

    print(f"\n=== BoJ {label} ({start_year}–{end_year}) ===")
    conn = boj_conn()
    session = _session()
    existing = {r[0] for r in conn.execute(
        "SELECT url FROM speeches WHERE central_bank='Bank of Japan'"
    )}
    total_stored = 0

    for year in range(start_year, end_year + 1):
        print(f"  Fetching BoJ {year} index ...")
        entries = _scrape_year_index(year, session)
        print(f"    Found {len(entries)} entries on site")
        year_stored = 0

        for sp in entries:
            if sp["url"] in existing:
                continue
            try:
                body = _get_speech_text(sp["url"], session)
                conn.execute(
                    "INSERT OR IGNORE INTO speeches "
                    "(url, date, speaker, title, body, central_bank, country) "
                    "VALUES (?, ?, ?, ?, ?, 'Bank of Japan', 'JPN')",
                    (sp["url"], sp["date"], sp["speaker"], sp["title"], body),
                )
                existing.add(sp["url"])
                year_stored += 1
                total_stored += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"    ERROR {sp['url']}: {e}")

        conn.commit()
        print(f"    {year}: {year_stored} new stored (running total: {total_stored})")

    conn.close()
    print(f"\nBoJ {label} done: {total_stored} speeches loaded")
    return total_stored


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Allow partial runs via command-line: "fed", "boj-old", "boj-mid", or nothing for all
    tasks = set(sys.argv[1:]) if len(sys.argv) > 1 else {"fed", "boj-old", "boj-mid"}

    grand_total = 0

    if "fed" in tasks:
        grand_total += load_fed_gap(1996, 2005)

    if "boj-old" in tasks:
        # 1996-2001 on www2.boj.or.jp (falls back automatically in _scrape_year_index)
        grand_total += load_boj_gap(1996, 2001, "pre-2002 archive")

    if "boj-mid" in tasks:
        # 2011-2020 on www.boj.or.jp
        grand_total += load_boj_gap(2011, 2020, "2011-2020")

    print(f"\n{'='*50}")
    print(f"All done. Grand total speeches loaded: {grand_total}")
    print("None were rated. Run the topup scripts to rate if needed.")
