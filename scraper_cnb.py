"""
Czech National Bank (CNB) speech scraper.

Listing page is JS-rendered — uses Playwright to load with year filter.
Individual speech pages are static HTML — fetched with requests + BeautifulSoup.
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
from bs4 import BeautifulSoup

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))
BASE = "https://www.cnb.cz"
LISTING_URL_CS = f"{BASE}/cs/verejnost/servis-pro-media/vystoupeni-konference-seminare/prezentace-a-vystoupeni/"
LISTING_URL_EN = f"{BASE}/en/public/media-service/speeches-conferences-seminars/presentations-and-speeches/"
LISTING_URL = LISTING_URL_CS  # backwards-compat alias
_SPEECH_PATH_FRAGMENT = "/prezentace-a-vystoupeni/"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# ── CNB Bank Board members ──────────────────────────────────────────────────

_CNB_CURRENT = {
    "Aleš Michl",
    "Eva Zamrazilová",
    "Jan Frait",
    "Karina Kubelková",
    "Jan Kubíček",
    "Jan Procházka",
    "Jakub Seidler",
}

_CNB_HISTORICAL = _CNB_CURRENT | {
    "Jiří Rusnok",       # Governor 2016–2022
    "Miroslav Singer",   # Governor 2010–2016
    "Zdeněk Tůma",       # Governor 2000–2010
    "Tomáš Holub",       # Board member
    "Marek Mora",
    "Vojtěch Benda",
    "Luboš Komárek",
    "Oldřich Dědek",
    "Tomáš Nidetzký",
    "Vladimír Tomšík",   # Board member ~2006–2016
    "Pavel Řežábek",     # Board member ~2008–2016
    "Robert Holman",     # Board member ~2000–2010
    "Mojmír Hampl",      # Deputy Governor ~2008–2018
    "Kamil Janáček",     # Board member ~2000–2010
    "Luděk Niedermayer", # Board member ~2000–2008
    "Petr Král",         # Board member ~2018–2022
    "Lubomír Lízal",     # Board member ~2012–2018 (was missing)
    "Tomáš Nidetzký",
}

ALL_CNB = _CNB_HISTORICAL


def _normalize_speaker(raw: str) -> str:
    """Convert 'Surname Firstname' to 'Firstname Surname'."""
    raw = raw.strip()
    parts = raw.split()
    if len(parts) == 2:
        return f"{parts[1]} {parts[0]}"
    if len(parts) >= 3:
        return " ".join(reversed(parts))
    return raw


import unicodedata

from translator import detect_language


def _ascii_fold(s: str) -> str:
    """Fold accented chars to ASCII for fuzzy name matching."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _match_speaker(name: str) -> str:
    """Return canonical name from ALL_CNB, tolerating encoding differences."""
    if name in ALL_CNB:
        return name
    folded = _ascii_fold(name)
    for canon in ALL_CNB:
        if _ascii_fold(canon) == folded:
            return canon
    return name


# ── DB helpers ──────────────────────────────────────────────────────────────

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
    for col in ("body", "central_bank", "country", "body_en", "language"):
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
    urls = {r[0] for r in conn.execute("SELECT url FROM speeches WHERE central_bank='CNB'")}
    conn.close()
    return urls


def _store_speech(rec: dict, conn: sqlite3.Connection) -> None:
    # Detect language from content if not explicitly supplied.
    # Speeches from LISTING_URL_EN are always English; Czech listing can be either.
    lang = rec.get("language")
    if not lang:
        lang = detect_language(rec.get("body", ""), rec.get("title", ""))
    conn.execute(
        "INSERT OR IGNORE INTO speeches "
        "(url, date, speaker, title, body, central_bank, country, language) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (rec["url"], rec["date"], rec["speaker"], rec["title"],
         rec.get("body", ""), "CNB", "CZK", lang),
    )


# ── Date parsing ─────────────────────────────────────────────────────────────

def _parse_date(raw: str) -> str:
    """Parse CNB date formats: 'D. M. YYYY' or 'D.M.YYYY' → 'YYYY-MM-DD'."""
    raw = raw.strip()
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", raw)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
    return ""


# ── Individual speech page fetching ─────────────────────────────────────────

def _fetch_pdf_body(url: str) -> str:
    """Download a PDF and extract text with pdfplumber."""
    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=45)
        if resp.status_code != 200:
            return ""
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
        return "\n".join(pages)
    except Exception as e:
        print(f"    PDF fail {url}: {e}")
        return ""


def _fetch_speech_body(url: str) -> tuple[str, str, str]:
    """
    Fetch an individual CNB speech page or PDF.
    Returns (body_text, date_iso, speaker_canonical).
    """
    # Direct PDF link
    if url.lower().endswith(".pdf"):
        body = _fetch_pdf_body(url)
        return body, "", ""

    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"    ERROR fetching {url}: {e}")
        return "", "", ""

    # If response is actually a PDF despite URL
    if "application/pdf" in resp.headers.get("content-type", ""):
        try:
            with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
            return "\n".join(pages), "", ""
        except Exception:
            return "", "", ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── Speaker: appears as a link with surname-first format ──────────────
    speaker = ""
    # Try the speaker link (has anchor like #michl-ales or similar)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "speaker" in href.lower() or "?speaker=" in href.lower():
            raw = a.get_text(strip=True)
            speaker = _normalize_speaker(raw)
            break

    # Fallback: look for "Name Surname, CNB [role]" pattern in metadata
    if not speaker:
        meta_text = soup.get_text(" ", strip=True)
        role_match = re.search(
            r"([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+)"
            r",?\s+CNB\s+(?:Governor|Deputy Governor|Board Member|Vice.Governor)",
            meta_text
        )
        if role_match:
            speaker = role_match.group(1)

    # ── Date ──────────────────────────────────────────────────────────────
    date_iso = ""
    # CNB date appears before speaker link, format "D. M. YYYY"
    date_candidates = re.findall(r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}", soup.get_text())
    if date_candidates:
        date_iso = _parse_date(date_candidates[0])

    # ── Body text ─────────────────────────────────────────────────────────
    # Remove nav, header, footer, sidebar before extracting
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "noscript"]):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(r"nav|menu|sidebar|filter|footer|breadcrumb|share|related", re.I)):
        tag.decompose()

    # Try main content area selectors
    content = (
        soup.select_one("main .content")
        or soup.select_one("main article")
        or soup.select_one("main")
        or soup.select_one("article")
        or soup.select_one(".article-content")
        or soup.select_one(".content")
        or soup.body
    )

    body = ""
    if content:
        # Extract paragraphs and headings only (skip boilerplate)
        parts = []
        for el in content.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
            txt = el.get_text(" ", strip=True)
            if len(txt) > 30:  # skip short nav fragments
                parts.append(txt)
        body = "\n\n".join(parts)

    return body, date_iso, speaker


# ── Playwright listing ───────────────────────────────────────────────────────

def _fetch_listing_year(page, year: int, base_url: str = None) -> list[dict]:
    """
    Navigate to CNB listing filtered by year.
    Returns list of {url, date_raw, speaker_raw, title}.
    base_url defaults to LISTING_URL_CS (Czech listing).

    HTML structure (per .list-entry):
      .date                         → "25. 9. 2025"
      .author a[data-category]      → "Frait Jan"  (surname first)
      h2 a[href*=presentations...]  → title + URL
    """
    if base_url is None:
        base_url = LISTING_URL_CS
    url = f"{base_url}?year={year}"
    page.goto(url, timeout=30000, wait_until="networkidle")
    time.sleep(1.5)

    items = []
    seen = set()

    entries = page.query_selector_all(".list-entry")
    for entry in entries:
        # Title + URL — older speeches link directly to PDFs, newer ones to HTML pages
        title_link = entry.query_selector("h2 a")
        if not title_link:
            continue
        href = title_link.get_attribute("href") or ""
        title = title_link.inner_text().strip()
        # Strip "(pdf, NNN kB)" from title
        title = re.sub(r"\s*\(pdf[^)]*\)", "", title, flags=re.I).strip()
        if not href or not title or len(title) < 5:
            continue
        full_url = BASE + href if href.startswith("/") else href
        if full_url in seen:
            continue
        seen.add(full_url)

        # Date
        date_el = entry.query_selector(".date")
        date_raw = date_el.inner_text().strip() if date_el else ""

        # Speaker — text is "Surname Firstname" (needs normalizing)
        speaker_raw = ""
        author_link = entry.query_selector(".author a")
        if author_link:
            speaker_raw = author_link.inner_text().strip()

        items.append({
            "url": full_url,
            "date_raw": date_raw,
            "speaker_raw": speaker_raw,
            "title": title,
        })

    return items


# ── Public entry points ──────────────────────────────────────────────────────

def get_all_cnb_speeches(start_year: int = 2021, end_year: int = None) -> list[dict]:
    """Scrape all Bank Board speeches from start_year to end_year, store to DB."""
    from playwright.sync_api import sync_playwright

    if end_year is None:
        end_year = datetime.now().year

    existing = get_existing_urls()
    conn = _conn()
    stored = 0
    to_rate = []

    years = list(range(start_year, end_year + 1))
    print(f"  Fetching CNB speeches {years[0]}–{years[-1]} ...")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_UA)
        page = context.new_page()

        for year in years:
            # Scrape both the Czech listing and the separate English listing.
            # CNB explicitly routes non-Czech presentations to the English URL.
            listings = [
                (LISTING_URL_CS, None),   # language auto-detected from body
                (LISTING_URL_EN, "en"),   # always English
            ]
            year_new = 0

            for listing_url, forced_lang in listings:
                items = _fetch_listing_year(page, year, base_url=listing_url)
                label = "EN" if forced_lang == "en" else "CS"
                print(f"    {year} [{label}]: {len(items)} speeches on site")

                for item in items:
                    url = item["url"]
                    if url in existing:
                        continue

                    # Get body + confirmed date/speaker from the individual page
                    body, date_iso, speaker = _fetch_speech_body(url)

                    # Fall back to listing metadata if individual page parse fails
                    if not date_iso and item["date_raw"]:
                        date_iso = _parse_date(item["date_raw"])
                    if not speaker and item["speaker_raw"]:
                        speaker = _normalize_speaker(item["speaker_raw"])

                    if not date_iso or not speaker:
                        print(f"      SKIP (missing date/speaker): {url}")
                        continue
                    speaker = _match_speaker(speaker)
                    if speaker not in ALL_CNB:
                        print(f"      SKIP (not board member): {speaker} — {url}")
                        continue

                    rec = {
                        "url": url,
                        "date": date_iso,
                        "speaker": speaker,
                        "title": item["title"],
                        "body": body,
                        "language": forced_lang,  # None → auto-detect in _store_speech
                    }
                    _store_speech(rec, conn)
                    existing.add(url)
                    year_new += 1
                    stored += 1

                    if body:
                        to_rate.append(rec)

                    time.sleep(0.5)

            conn.commit()
            print(f"      → {year_new} new stored")

        browser.close()

    conn.close()
    print(f"  CNB total new speeches stored: {stored}")
    return to_rate


def get_new_cnb_speeches() -> list[dict]:
    """Check current (and previous if early in year) year for new CNB speeches."""
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

        listings = [
            (LISTING_URL_CS, None),
            (LISTING_URL_EN, "en"),
        ]
        for y in years_to_check:
            for listing_url, forced_lang in listings:
                items = _fetch_listing_year(page, y, base_url=listing_url)
                label = "EN" if forced_lang == "en" else "CS"
                print(f"  CNB {y} [{label}]: {len(items)} speeches on site")

                for item in items:
                    url = item["url"]
                    if url in existing:
                        continue

                    body, date_iso, speaker = _fetch_speech_body(url)
                    if not date_iso and item["date_raw"]:
                        date_iso = _parse_date(item["date_raw"])
                    if not speaker and item["speaker_raw"]:
                        speaker = _normalize_speaker(item["speaker_raw"])

                    if not date_iso or not speaker or speaker not in ALL_CNB:
                        continue

                    rec = {
                        "url": url,
                        "date": date_iso,
                        "speaker": speaker,
                        "title": item["title"],
                        "body": body,
                        "language": forced_lang,
                    }
                    _store_speech(rec, conn)
                    existing.add(url)

                    if speaker in _CNB_CURRENT and body and date_iso >= f"{year}-01-01":
                        to_rate.append(rec)

                time.sleep(0.5)

        browser.close()

    conn.commit()

    # Pick up any stored-but-unrated current-year speeches
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body FROM speeches "
        "WHERE central_bank='CNB' AND score IS NULL AND date >= ?",
        (f"{year}-01-01",),
    ).fetchall()
    conn.close()

    already = {s["url"] for s in to_rate}
    for url, date, speaker, title, body in unrated:
        if url not in already and speaker in _CNB_CURRENT and body:
            to_rate.append({"url": url, "date": date, "speaker": speaker,
                            "title": title, "body": body})

    print(f"  {len(to_rate)} new CNB speeches to rate")
    return to_rate
