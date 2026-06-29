"""
South African Reserve Bank (SARB) speech scraper.

Listing: JS-rendered AEM CMS at resbank.co.za — uses Playwright to extract links.
         Falls back gracefully if search service is down.
Individual: plain requests; full text from <p> elements, PDF preferred.
"""

import io
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

DB_PATH = Path("data/speeches.db")
BASE = "https://www.resbank.co.za"
LISTING_URL = f"{BASE}/en/home/publications/speeches"
PDF_BASE = f"{BASE}/content/dam/sarb/publications/speeches/speeches-by-governors"

# ---------------------------------------------------------------------------
# MPC members (Governor + 3 Deputy Governors vote; include historical)
# ---------------------------------------------------------------------------

_SARB_CURRENT = {
    "Lesetja Kganyago",   # Governor (since 2014)
    "Rashad Cassim",      # Deputy Governor
    "Fundi Tshazibana",   # Deputy Governor
    "Mampho Modise",      # Deputy Governor
}

_SARB_HISTORICAL = _SARB_CURRENT | {
    # Former governors
    "Gill Marcus",         # Governor 2009–2014
    "Tito Mboweni",        # Governor 1999–2009
    # Former deputy governors
    "Daniel Mminele",      # Deputy Governor, resigned 2021
    "Kuben Naidoo",        # Deputy Governor 2015–2022
    "Francois Groepe",     # Deputy Governor 2012–2019
    "Brian Kahn",          # Chief Economist / MPC member
    "Nomvula Moleketi",    # Deputy Governor 2005–2009
}

ALL_SARB = _SARB_HISTORICAL

_TITLE_RE = re.compile(
    r"^(?:Governor|Deputy\s+Governor|Chief\s+Economist|Dr\.?|Mr\.?|Ms\.?|Prof\.?)\s+",
    re.IGNORECASE,
)

_ALIASES: dict[str, str] = {
    "Kganyago": "Lesetja Kganyago",
    "Cassim": "Rashad Cassim",
    "Tshazibana": "Fundi Tshazibana",
    "Modise": "Mampho Modise",
    "Marcus": "Gill Marcus",
    "Mboweni": "Tito Mboweni",
    "Mminele": "Daniel Mminele",
    "Naidoo": "Kuben Naidoo",
    "Groepe": "Francois Groepe",
}


def _normalize_speaker(raw: str) -> str:
    name = _TITLE_RE.sub("", raw).strip()
    return _ALIASES.get(name, name)


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


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(_CREATE_TABLE)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    for col in ("body", "central_bank", "country"):
        if col not in cols:
            conn.execute(f"ALTER TABLE speeches ADD COLUMN {col} TEXT")
    conn.commit()
    return conn


def save_rating(url: str, score: int, justification: str, rated_at: str) -> None:
    conn = _conn()
    conn.execute(
        "UPDATE speeches SET score=?, justification=?, rated_at=? WHERE url=?",
        (score, justification, rated_at, url),
    )
    conn.commit()
    conn.close()


def get_existing_urls() -> set[str]:
    conn = _conn()
    urls = {r[0] for r in conn.execute("SELECT url FROM speeches WHERE central_bank='SARB'")}
    conn.close()
    return urls


def _store_speech(rec: dict, conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO speeches "
        "(url, date, speaker, title, body, central_bank, country) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rec["url"], rec["date"], rec["speaker"], rec["title"],
         rec.get("body", ""), "SARB", "ZAR"),
    )


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = _UA


def _pdf_url_from_speech_url(speech_url: str) -> str:
    """Derive predictable PDF URL from speech page URL."""
    # .../speeches-by-governors/2026/cassim-yield-curve
    # → /content/dam/sarb/publications/speeches/speeches-by-governors/2026/cassim-yield-curve.pdf
    m = re.search(r"/speeches-by-governors/(\d{4})/([^/?#]+)", speech_url)
    if not m:
        return ""
    year, slug = m.group(1), m.group(2)
    return f"{PDF_BASE}/{year}/{slug}.pdf"


def _download_pdf_text(pdf_url: str) -> str:
    """Download and extract text from a SARB PDF. Returns empty string on failure."""
    try:
        r = _SESSION.get(pdf_url, timeout=45)
        if r.status_code != 200:
            return ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
        return "\n".join(pages)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Individual speech page parsing (plain requests)
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1
)}


def _parse_date_str(s: str) -> str:
    m = _DATE_RE.search(s)
    if not m:
        return ""
    d, mon, y = m.group(1), m.group(2).capitalize(), m.group(3)
    return f"{y}-{_MONTHS[mon]}-{int(d):02d}"


def _fetch_speech_page(url: str) -> dict:
    """Fetch an individual SARB speech page. Returns dict with date, speaker, title, body."""
    try:
        r = _SESSION.get(url, timeout=30)
        r.raise_for_status()
    except Exception:
        return {}

    soup = BeautifulSoup(r.text, "html.parser")

    # Title and speaker
    # New format: <title> = "Speaker | Speech Title | SARB"
    # Old format: <title> = full speech title (long descriptive string)
    title = ""
    speaker = ""
    page_title_tag = soup.find("title")
    if page_title_tag:
        raw_title = page_title_tag.get_text().strip()
        parts = [p.strip() for p in raw_title.split("|")]
        if len(parts) >= 2 and len(parts[0]) < 60:
            # New format: first part is speaker name
            speaker_raw = parts[0]
            title = parts[1]
            speaker = _normalize_speaker(speaker_raw)
            if not speaker or speaker not in ALL_SARB:
                speaker = _normalize_speaker(speaker_raw.split()[-1]) if speaker_raw else ""
        else:
            # Old format: entire title tag is the speech title
            title = raw_title

    # Date: search page text for written date (e.g. "24 June 2026")
    page_text = soup.get_text(" ")
    date_iso = _parse_date_str(page_text)

    # PDF: find the actual <a href="*.pdf"> link on the page (slug may differ from URL slug)
    body = ""
    pdf_link = soup.find("a", href=re.compile(r"\.pdf$", re.I))
    if pdf_link:
        pdf_href = pdf_link["href"]
        pdf_url = BASE + pdf_href if pdf_href.startswith("/") else pdf_href
        body = _download_pdf_text(pdf_url)

    if not body:
        # Fallback: collect <p> tags (full speech text is in plain <p> elements)
        paras = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
        body = "\n\n".join(paras)

    # Last-resort speaker inference from URL slug
    if not speaker or speaker not in ALL_SARB:
        m = re.search(r"/speeches-by-governors/\d{4}/([^/?#]+)", url)
        if m:
            slug = m.group(1)
            for name in ALL_SARB:
                last = name.split()[-1].lower()
                if last in slug.lower():
                    speaker = name
                    break

    return {
        "url": url,
        "date": date_iso,
        "speaker": speaker,
        "title": title,
        "body": body,
    }


# ---------------------------------------------------------------------------
# Listing: Playwright-based URL discovery
# ---------------------------------------------------------------------------

def _discover_urls_playwright(start_year: int, end_year: int) -> list[str]:
    """Use Playwright to extract speech URLs from the SARB listing page.

    The listing is paginated (JS-rendered). Clicks through all page buttons
    to collect speeches across all years. Returns empty list if the page fails.
    """
    from playwright.sync_api import sync_playwright

    found_urls: list[str] = []
    seen: set[str] = set()

    def _collect(pg) -> None:
        for link in pg.query_selector_all("a[href*='speeches-by-governors']"):
            href = link.get_attribute("href") or ""
            m = re.search(r"/speeches-by-governors/(\d{4})/", href)
            if m and start_year <= int(m.group(1)) <= end_year:
                full = BASE + href if href.startswith("/") else href
                if full not in seen:
                    seen.add(full)
                    found_urls.append(full)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_UA)
        page = context.new_page()

        try:
            page.goto(LISTING_URL, timeout=35000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
        except Exception:
            pass

        _collect(page)

        # Find all page buttons (numbered) and click each in turn
        page_btns = page.query_selector_all("button.pagePublication")
        total_pages = len(page_btns)
        for pg_idx in range(1, total_pages):  # skip page 1 (already loaded)
            try:
                # Re-query to get fresh references after DOM updates
                btns = page.query_selector_all("button.pagePublication")
                if pg_idx >= len(btns):
                    break
                btns[pg_idx].click()
                page.wait_for_timeout(2000)
                _collect(page)
            except Exception:
                break

        browser.close()

    return found_urls


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def get_all_sarb_speeches(start_year: int = 2021, end_year: int = None) -> list[dict]:
    """Discover and scrape SARB MPC speeches from start_year to end_year, store to DB."""
    if end_year is None:
        end_year = datetime.now().year

    print(f"  Discovering SARB speech URLs {start_year}–{end_year} via Playwright ...")
    urls = _discover_urls_playwright(start_year, end_year)
    print(f"  Found {len(urls)} speech URLs on listing page")

    if not urls:
        raise RuntimeError(
            "SARB listing page returned 0 speech links — the JS search service may be down. "
            "Seed URLs manually via get_all_sarb_speeches_from_urls() or retry later."
        )

    existing = get_existing_urls()
    conn = _conn()
    stored = 0
    to_rate = []

    for i, url in enumerate(urls, 1):
        if url in existing:
            continue

        rec = _fetch_speech_page(url)
        if not rec.get("date") or not rec.get("speaker"):
            continue
        if rec["speaker"] not in ALL_SARB:
            continue

        _store_speech(rec, conn)
        existing.add(url)
        stored += 1
        print(f"  [{i}/{len(urls)}] Stored: {rec['speaker']} | {rec['date']} | {rec['title'][:55]}")

        if rec["speaker"] in _SARB_CURRENT and rec.get("body"):
            to_rate.append(rec)

        if i % 10 == 0:
            conn.commit()
        time.sleep(0.5)

    conn.commit()
    conn.close()
    print(f"  SARB total new speeches stored: {stored}")
    return to_rate


def get_all_sarb_speeches_from_urls(urls: list[str]) -> list[dict]:
    """Scrape SARB speeches from a manually-supplied list of URLs.

    Use this when the JS listing page is down. Pass known speech URLs directly.
    """
    existing = get_existing_urls()
    conn = _conn()
    stored = 0
    to_rate = []

    for i, url in enumerate(urls, 1):
        if url in existing:
            continue

        rec = _fetch_speech_page(url)
        if not rec.get("date") or not rec.get("speaker"):
            print(f"  [{i}] SKIP (no date/speaker): {url}")
            continue
        if rec["speaker"] not in ALL_SARB:
            print(f"  [{i}] SKIP (not MPC): {rec.get('speaker')} — {url}")
            continue

        _store_speech(rec, conn)
        existing.add(url)
        stored += 1
        print(f"  [{i}] Stored: {rec['speaker']} | {rec['date']} | {rec['title'][:55]}")

        if rec["speaker"] in _SARB_CURRENT and rec.get("body"):
            to_rate.append(rec)

        if i % 10 == 0:
            conn.commit()
        time.sleep(0.5)

    conn.commit()
    conn.close()
    print(f"  SARB total new speeches stored: {stored}")
    return to_rate


def get_new_sarb_speeches() -> list[dict]:
    """Check current year (and previous if Jan–Mar) for new SARB speeches."""
    year = datetime.now().year
    end_year = year
    start_year = year - 1 if datetime.now().month <= 3 else year

    existing = get_existing_urls()
    conn = _conn()
    to_rate = []

    try:
        urls = _discover_urls_playwright(start_year, end_year)
    except Exception as e:
        print(f"  SARB listing discovery failed: {e}")
        urls = []

    print(f"  SARB {start_year}–{end_year}: {len(urls)} URLs found")

    for url in urls:
        if url in existing:
            continue

        rec = _fetch_speech_page(url)
        if not rec.get("date") or not rec.get("speaker"):
            continue
        if rec["speaker"] not in ALL_SARB:
            continue

        _store_speech(rec, conn)
        existing.add(url)

        if rec["speaker"] in _SARB_CURRENT and rec.get("body") and rec["date"] >= f"{year}-01-01":
            to_rate.append(rec)

        time.sleep(0.5)

    conn.commit()

    # Also pick up stored-but-unrated current-year speeches
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body FROM speeches "
        "WHERE central_bank='SARB' AND score IS NULL AND date >= ?",
        (f"{year}-01-01",),
    ).fetchall()
    conn.close()

    already = {s["url"] for s in to_rate}
    for url, date, speaker, title, body in unrated:
        if url not in already and speaker in _SARB_CURRENT and body:
            to_rate.append({"url": url, "date": date, "speaker": speaker,
                            "title": title, "body": body})

    print(f"  {len(to_rate)} new SARB speeches to rate")
    return to_rate
