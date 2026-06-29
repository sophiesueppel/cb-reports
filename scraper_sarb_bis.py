"""
Scraper for SARB speeches from the BIS archive.

BIS maintains a comprehensive catalogue of SARB speeches going back to ~2009.
Uses the BIS document_lists JSON API to discover all SARB speeches, then
downloads PDFs for full body text.

Run:
    python scraper_sarb_bis.py
"""

import io
import re
import sqlite3
import sys
import time
import datetime as dt_module
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path("data/speeches.db")
BIS_BASE = "https://www.bis.org"
BIS_DOC_LIST_URL = f"{BIS_BASE}/api/document_lists/cbspeeches.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": UA, "Referer": f"{BIS_BASE}/cbspeeches/index.htm?r"})

# ---------------------------------------------------------------------------
# MPC members
# ---------------------------------------------------------------------------

_SARB_CURRENT = {
    "Lesetja Kganyago",
    "Rashad Cassim",
    "Fundi Tshazibana",
    "Mampho Modise",
}

_SARB_HISTORICAL = _SARB_CURRENT | {
    "Gill Marcus",
    "Tito Mboweni",
    "Daniel Mminele",
    "Kuben Naidoo",
    "Francois Groepe",
    "Brian Kahn",
    "Nomvula Moleketi",
}

# Last-name-only filters for the BIS title search (distinctive enough to avoid false positives)
_SARB_LAST_NAMES = [
    "Kganyago", "Tshazibana", "Mminele", "Naidoo", "Groepe", "Moleketi", "Mboweni",
]
# Full names for ambiguous surnames
_SARB_FULL_NAMES = [
    "Rashad Cassim", "Mampho Modise", "Gill Marcus", "Brian Kahn", "Kuben Naidoo",
]

_ALIASES = {
    "Kganyago": "Lesetja Kganyago",
    "Cassim": "Rashad Cassim",
    "Tshazibana": "Fundi Tshazibana",
    "Modise": "Mampho Modise",
    "Marcus": "Gill Marcus",
    "Mboweni": "Tito Mboweni",
    "Mminele": "Daniel Mminele",
    "Naidoo": "Kuben Naidoo",
    "Groepe": "Francois Groepe",
    "Kahn": "Brian Kahn",
    "Moleketi": "Nomvula Moleketi",
}

_TITLE_PREFIX_RE = re.compile(
    r"^(?:Mr\.?\s+|Ms\.?\s+|Dr\.?\s+|Governor\s+|Deputy\s+Governor\s+|Prof\.?\s+)",
    re.IGNORECASE,
)

_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1
)}


def _normalize_speaker(raw: str) -> str:
    name = _TITLE_PREFIX_RE.sub("", raw).strip()
    if name in _SARB_HISTORICAL:
        return name
    last = name.split()[-1] if name else ""
    return _ALIASES.get(last, name)


def _parse_date(text: str) -> str:
    m = _DATE_RE.search(text)
    if not m:
        return ""
    d, mon, y = m.group(1), m.group(2).capitalize(), m.group(3)
    return f"{y}-{_MONTHS[mon]}-{int(d):02d}"


# ---------------------------------------------------------------------------
# BIS document list: discover all SARB speeches
# ---------------------------------------------------------------------------

def discover_sarb_urls_from_bis_api() -> list[tuple[str, str, str, str]]:
    """
    Download BIS document list JSON and filter for SARB speeches.
    Returns list of (url, speaker, title, pub_date) tuples.
    """
    print("  Downloading BIS document list JSON (~7MB)...")
    r = _SESSION.get(BIS_DOC_LIST_URL, timeout=90)
    r.raise_for_status()
    doc_list = r.json()["list"]
    print(f"  Total BIS documents: {len(doc_list)}")

    results = []
    for path, item in doc_list.items():
        title_raw = item.get("short_title", "")
        # Filter: must contain a known SARB speaker in the title
        # BIS titles for SARB speeches are formatted as "Speaker Name: Speech Title"
        match = any(name in title_raw for name in _SARB_LAST_NAMES) or \
                any(name in title_raw for name in _SARB_FULL_NAMES)
        if not match:
            continue

        # Parse speaker and title from "Speaker: Title" format
        if ":" in title_raw:
            speaker_raw, _, speech_title = title_raw.partition(":")
            speaker = _normalize_speaker(speaker_raw.strip())
            title = speech_title.strip()
        else:
            speaker = ""
            title = title_raw

        # Skip if speaker not recognised
        if speaker not in _SARB_HISTORICAL:
            continue

        pub_date = item.get("publication_start_date", "")
        url = f"{BIS_BASE}{path}.htm"
        results.append((url, speaker, title, pub_date))

    # Sort newest first
    results.sort(key=lambda x: x[3], reverse=True)
    print(f"  Found {len(results)} SARB speeches in BIS list")
    return results


# ---------------------------------------------------------------------------
# Fetch full text from BIS: try HTML pagecontent then PDF
# ---------------------------------------------------------------------------

def _fetch_body_and_date(url: str) -> tuple[str, str]:
    """
    Returns (body_text, date_iso) for a BIS speech URL.
    Tries PDF first (full text), falls back to HTML pagecontent excerpt.
    """
    pdf_url = url.replace(".htm", ".pdf")
    body = ""
    date_iso = ""

    # Try PDF (replace .htm → .pdf)
    try:
        r = _SESSION.get(pdf_url, timeout=60)
        if r.status_code == 200:
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
            body = "\n".join(pages)
            date_iso = _parse_date(body)
    except Exception:
        pass

    # If no date yet, try HTML pagecontent
    if not date_iso or not body:
        try:
            r = _SESSION.get(url, timeout=30)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                pc = soup.find(id="pagecontent")
                pc_text = pc.get_text(" ") if pc else ""
                if not date_iso:
                    date_iso = _parse_date(pc_text)
                if not body:
                    # Use HTML excerpt (likely partial, but better than nothing)
                    paras = [p.get_text(strip=True) for p in (pc or soup).find_all("p") if p.get_text(strip=True)]
                    body = "\n\n".join(paras)
        except Exception:
            pass

    return body, date_iso


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def get_existing_urls() -> set[str]:
    conn = _conn()
    urls = {r[0] for r in conn.execute("SELECT url FROM speeches WHERE central_bank='SARB'")}
    conn.close()
    return urls


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(start_year: int = 2021) -> None:
    from dotenv import load_dotenv
    load_dotenv(Path(".env") if Path(".env").exists() else Path("../.env"))

    print("=== SARB BIS scraper ===")
    speeches = discover_sarb_urls_from_bis_api()

    existing = get_existing_urls()
    new_speeches = [(u, sp, t, d) for u, sp, t, d in speeches if u not in existing]
    print(f"New speeches to fetch (not in DB): {len(new_speeches)}")

    conn = _conn()
    stored = 0
    skipped = 0

    for i, (url, speaker, title, pub_date) in enumerate(new_speeches, 1):
        body, date_iso = _fetch_body_and_date(url)

        # Use publication_start_date as fallback date if we can't parse from content
        if not date_iso and pub_date:
            date_iso = pub_date  # close enough; usually within a few days of speech

        if len(body) < 200:
            print(f"  [{i}/{len(new_speeches)}] SKIP (body {len(body)} chars): {url}")
            skipped += 1
            time.sleep(0.3)
            continue

        conn.execute(
            "INSERT OR IGNORE INTO speeches "
            "(url, date, speaker, title, body, central_bank, country) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (url, date_iso, speaker, title, body, "SARB", "ZAR"),
        )
        stored += 1
        print(f"  [{i}/{len(new_speeches)}] Stored: {speaker} | {date_iso} | {title[:60]}")

        if i % 10 == 0:
            conn.commit()
        time.sleep(0.4)

    conn.commit()
    conn.close()
    print(f"\nStored {stored} new speeches ({skipped} skipped/short)")

    if stored > 0:
        _rate_new(start_year)
        _classify_new()
        _regenerate_report()
        _git_push(stored)
    else:
        print("No new speeches stored — no rating/report update needed.")


def _rate_new(start_year: int = 2021) -> None:
    from rater import rate_speech

    print("\n--- Rating new unrated SARB speeches ---")
    conn = _conn()
    cutoff = f"{start_year}-01-01"
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body FROM speeches "
        "WHERE central_bank='SARB' AND score IS NULL "
        "AND date >= ? AND body IS NOT NULL AND length(body) > 200 "
        "ORDER BY date DESC",
        (cutoff,),
    ).fetchall()
    print(f"  {len(unrated)} speeches to rate (from {cutoff})")

    now = dt_module.datetime.now().isoformat()
    rated, errors = 0, 0
    for i, (url, date, speaker, title, body) in enumerate(unrated, 1):
        try:
            result = rate_speech(
                title=title or "",
                speaker=speaker or "",
                date=date or "",
                text=body,
                bank="SARB",
                db_path=str(DB_PATH),
            )
            score = result["score"]
            justification = result["justification"]
            conn.execute(
                "UPDATE speeches SET score=?, justification=?, rated_at=? WHERE url=?",
                (score, justification, now, url),
            )
            conn.commit()
            print(f"  [{i}/{len(unrated)}] {date} | {title[:50]} → {score}/10")
            rated += 1
        except Exception as e:
            print(f"  [{i}/{len(unrated)}] ERROR: {e}")
            errors += 1

    conn.close()
    print(f"  Done. {rated} rated, {errors} errors.")


def _classify_new() -> None:
    print("\n--- Classifying neutral SARB speeches ---")
    from classify_relevance_llm import run_classification
    run_classification(bank="SARB")


def _regenerate_report() -> None:
    print("\n--- Regenerating SARB report ---")
    from report_sarb_filtered import generate_sarb_filtered_report
    generate_sarb_filtered_report()


def _git_push(n_stored: int) -> None:
    import subprocess
    print("\n--- Git commit & push ---")
    subprocess.run(["git", "add", "report_sarb_filtered.html", "scraper_sarb_bis.py"], check=True)
    msg = f"SARB: backfill {n_stored} speeches from BIS archive"
    result = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Git commit: {result.stdout.strip()} {result.stderr.strip()}")
    else:
        print(f"  Committed: {result.stdout.strip()}")
    subprocess.run(["git", "push"], check=True)
    print("  Pushed.")


if __name__ == "__main__":
    run()
