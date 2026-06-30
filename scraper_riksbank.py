"""
Riksbank (Sveriges Riksbank) speech scraper.

Listing: https://www.riksbank.se/en-gb/press-and-published/speeches-and-presentations/?year=YYYY
Individual: metadata from article element + full text from linked PDF.
Uses Playwright to bypass bot protection for page navigation; PDFs downloaded via requests.
"""

import io
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))
BASE = "https://www.riksbank.se"
LISTING_BASE = f"{BASE}/en-gb/press-and-published/speeches-and-presentations/"

# ---------------------------------------------------------------------------
# Executive Board members (all vote on rates, 6 members)
# ---------------------------------------------------------------------------

_RIKSBANK_CURRENT = {
    "Erik Thedéen",
    "Aino Bunge",
    "Per Jansson",
    "Anna Seim",
    "Göran Hjelm",
    "Per Bolund",
}

_RIKSBANK_HISTORICAL = _RIKSBANK_CURRENT | {
    # Departed 2024
    "Martin Flodén",
    "Anna Breman",
    # Earlier
    "Cecilia Skingsley",
    "Henry Ohlsson",
    "Kerstin af Jochnick",
    "Per Jansson",
    "Stefan Ingves",     # Governor until Jan 2023
    "Mikael Jansson",
    "Karolina Ekholm",
    "Lars E.O. Svensson",
}

ALL_RIKSBANK = _RIKSBANK_HISTORICAL

# Speaker name → canonical (strips title prefixes AND suffixes)
_TITLE_PREFIX_RE = re.compile(
    r"^(?:Governor|First\s+Deputy\s+Governor|Deputy\s+Governor|Chief\s+Economist"
    r"|Adviser|Director|Professor)\s+",
    re.IGNORECASE,
)
_TITLE_SUFFIX_RE = re.compile(
    r"\s+(?:Governor|First\s+Deputy\s+Governor|Deputy\s+Governor|Chief\s+Economist"
    r"|Adviser|Director|Professor)$",
    re.IGNORECASE,
)

_ALIASES: dict[str, str] = {
    "Thedéen": "Erik Thedéen",
    "Thedeen": "Erik Thedéen",
    "Bunge": "Aino Bunge",
    "Jansson": "Per Jansson",
    "Seim": "Anna Seim",
    "Flodén": "Martin Flodén",
    "Breman": "Anna Breman",
    "Hjelm": "Göran Hjelm",
    "Bolund": "Per Bolund",
    "Ingves": "Stefan Ingves",
    "Skingsley": "Cecilia Skingsley",
}


def _normalize_speaker(raw: str) -> str:
    """Strip title prefix/suffix and resolve single-name shorthand."""
    name = _TITLE_PREFIX_RE.sub("", raw).strip()
    name = _TITLE_SUFFIX_RE.sub("", name).strip()
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
    for col in ("body", "central_bank", "country", "language", "body_en"):
        if col not in cols:
            conn.execute(f"ALTER TABLE speeches ADD COLUMN {col} TEXT")
    conn.commit()
    return conn


def save_rating(url: str, score: int, justification: str, rated_at: str, body_en: str = None) -> None:
    conn = _conn()
    if body_en:
        conn.execute(
            "UPDATE speeches SET score=?, justification=?, rated_at=?, body_en=? WHERE url=?",
            (score, justification, rated_at, body_en, url),
        )
    else:
        conn.execute(
            "UPDATE speeches SET score=?, justification=?, rated_at=? WHERE url=?",
            (score, justification, rated_at, url),
        )
    conn.commit()
    conn.close()


def get_existing_urls() -> set[str]:
    conn = _conn()
    urls = {r[0] for r in conn.execute("SELECT url FROM speeches WHERE central_bank='Riksbank'")}
    conn.close()
    return urls


def _store_speech(rec: dict, conn: sqlite3.Connection) -> None:
    from translator import detect_language
    lang = rec.get("language") or detect_language(rec.get("body", ""), rec.get("title", ""))
    conn.execute(
        "INSERT OR IGNORE INTO speeches "
        "(url, date, speaker, title, body, central_bank, country, language) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (rec["url"], rec["date"], rec["speaker"], rec["title"],
         rec.get("body", ""), "Riksbank", "SEK", lang),
    )


# ---------------------------------------------------------------------------
# Playwright fetching
# ---------------------------------------------------------------------------

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _fetch_listing_year(page, year: int) -> list[dict]:
    """Return list of {url, date_raw, speaker_raw, title, type} for one year.

    Paginates via ?year=YYYY&page=N until a page returns no new items.
    """
    seen_urls: set[str] = set()
    items = []
    page_num = 1

    while True:
        url = f"{LISTING_BASE}?year={year}&page={page_num}"
        page.goto(url, timeout=30000, wait_until="networkidle")
        links = page.query_selector_all("a.listing-item--speach")
        new_on_page = 0

        for a in links:
            href = a.get_attribute("href") or ""
            if not href or href == LISTING_BASE:
                continue
            full_url = BASE + href if href.startswith("/") else href
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            raw = a.inner_text().strip()
            h4 = a.query_selector("h4")
            title = h4.inner_text().strip() if h4 else raw.split("\n")[0].strip()

            date_match = re.search(r"Date:\s*\n?\s*(\d{2}/\d{2}/\d{4})", raw)
            date_raw = date_match.group(1) if date_match else ""

            # Stop counting as new if the site has started returning off-year speeches
            if date_raw:
                item_year = int(date_raw.split("/")[2])
                if item_year != year:
                    continue  # URL is in seen_urls but don't add to items

            new_on_page += 1

            spk_match = re.search(r"Speaker:\s*\n?\s*(.+?)(?:\n|Place:|$)", raw)
            speaker_raw = spk_match.group(1).strip() if spk_match else ""

            cat = a.query_selector(".page-category")
            speech_type = cat.inner_text().strip() if cat else ""

            items.append({
                "url": full_url,
                "date_raw": date_raw,
                "speaker_raw": speaker_raw,
                "title": title,
                "type": speech_type,
            })

        if new_on_page == 0:
            break
        page_num += 1

    return items


_PDF_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _download_pdf_text(pdf_href: str) -> str:
    """Download a Riksbank PDF and extract text. Returns empty string on failure."""
    url = BASE + pdf_href if pdf_href.startswith("/") else pdf_href
    try:
        r = requests.get(url, headers={"User-Agent": _PDF_UA}, timeout=45)
        if r.status_code != 200:
            return ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
        return "\n".join(pages)
    except Exception:
        return ""


def _fetch_speech_body(page, url: str) -> tuple[str, str, str]:
    """Load individual speech page. Returns (body_text, date_iso, speaker_canonical).

    Metadata is extracted from the info box; full text comes from the linked PDF
    (falling back to article HTML text if no PDF is found).
    """
    page.goto(url, timeout=30000, wait_until="networkidle")

    # Date/speaker from info box
    date_iso = ""
    speaker = ""
    info_box = page.query_selector(".article-page__info-box")
    if info_box:
        box_text = info_box.inner_text()
        date_match = re.search(r"Date:\s*(\d{2}/\d{2}/\d{4})", box_text)
        if date_match:
            d, m, y = date_match.group(1).split("/")
            date_iso = f"{y}-{m}-{d}"
        spk_match = re.search(r"Speaker:\s*(.+?)(?:\n|Place:|$)", box_text)
        speaker_raw = spk_match.group(1).strip() if spk_match else ""
        speaker = _normalize_speaker(speaker_raw)

    # Prefer PDF full text; fall back to article HTML
    body = ""
    pdf_links = page.query_selector_all("a[href$='.pdf']")
    for link in pdf_links:
        href = link.get_attribute("href") or ""
        lower = href.lower()
        if "slide" in lower or "bilag" in lower or "appendix" in lower:
            continue
        body = _download_pdf_text(href)
        if body:
            break

    if not body:
        article = page.query_selector("article")
        body = article.inner_text().strip() if article else ""

    return body, date_iso, speaker


def _parse_date(date_raw: str) -> str:
    """Convert DD/MM/YYYY to YYYY-MM-DD."""
    if not date_raw:
        return ""
    try:
        d, m, y = date_raw.split("/")
        return f"{y}-{m}-{d}"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def get_all_riksbank_speeches(start_year: int = 2021, end_year: int = None) -> list[dict]:
    """Scrape all Executive Board speeches from start_year to end_year, store to DB."""
    from playwright.sync_api import sync_playwright

    if end_year is None:
        end_year = datetime.now().year

    existing = get_existing_urls()
    conn = _conn()
    stored = 0
    to_rate = []

    years = list(range(start_year, end_year + 1))
    print(f"  Fetching Riksbank speeches {years[0]}-{years[-1]} ...")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_UA)
        page = context.new_page()

        for year in years:
            items = _fetch_listing_year(page, year)
            year_new = 0
            print(f"    {year}: {len(items)} speeches on site")

            for item in items:
                speaker_listing = _normalize_speaker(item["speaker_raw"])
                if speaker_listing and speaker_listing not in ALL_RIKSBANK:
                    continue

                url = item["url"]
                if url in existing:
                    continue

                body, date_iso, speaker = _fetch_speech_body(page, url)

                if not date_iso:
                    date_iso = _parse_date(item["date_raw"])
                if not speaker:
                    speaker = speaker_listing or item["speaker_raw"]

                if not date_iso or not speaker:
                    continue
                if speaker not in ALL_RIKSBANK:
                    continue

                rec = {
                    "url": url,
                    "date": date_iso,
                    "speaker": speaker,
                    "title": item["title"],
                    "body": body,
                }
                _store_speech(rec, conn)
                existing.add(url)
                year_new += 1
                stored += 1

                if speaker in _RIKSBANK_CURRENT and body:
                    to_rate.append(rec)

                time.sleep(0.3)

            conn.commit()
            print(f"      -> {year_new} new stored")

        browser.close()

    conn.close()
    print(f"  Riksbank total new speeches stored: {stored}")
    return to_rate


def get_new_riksbank_speeches() -> list[dict]:
    """Check current (and previous if Jan-Mar) year for new speeches."""
    from playwright.sync_api import sync_playwright

    year = datetime.now().year
    years_to_check = [year]
    if datetime.now().month <= 3:
        years_to_check.append(year - 1)

    existing = get_existing_urls()
    conn = _conn()
    to_rate = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_UA)
        page = context.new_page()

        for y in years_to_check:
            items = _fetch_listing_year(page, y)
            print(f"  Riksbank {y}: {len(items)} speeches on site")

            for item in items:
                url = item["url"]
                speaker_listing = _normalize_speaker(item["speaker_raw"])
                if speaker_listing and speaker_listing not in ALL_RIKSBANK:
                    continue
                if url in existing:
                    continue

                body, date_iso, speaker = _fetch_speech_body(page, url)
                if not date_iso:
                    date_iso = _parse_date(item["date_raw"])
                if not speaker:
                    speaker = speaker_listing

                if not date_iso or not speaker or speaker not in ALL_RIKSBANK:
                    continue

                rec = {
                    "url": url,
                    "date": date_iso,
                    "speaker": speaker,
                    "title": item["title"],
                    "body": body,
                }
                _store_speech(rec, conn)
                existing.add(url)

                if speaker in _RIKSBANK_CURRENT and body and date_iso >= f"{year}-01-01":
                    to_rate.append(rec)

                time.sleep(0.3)

        browser.close()

    conn.commit()

    # Also pick up stored-but-unrated current-year speeches
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body FROM speeches "
        "WHERE central_bank='Riksbank' AND score IS NULL AND date >= ?",
        (f"{year}-01-01",),
    ).fetchall()
    conn.close()

    already = {s["url"] for s in to_rate}
    for url, date, speaker, title, body in unrated:
        if url not in already and speaker in _RIKSBANK_CURRENT and body:
            to_rate.append({"url": url, "date": date, "speaker": speaker,
                            "title": title, "body": body})

    print(f"  {len(to_rate)} new Riksbank speeches to rate")
    return to_rate


# Keep alias for backwards compat
get_new_riksbank_2026 = get_new_riksbank_speeches
