"""
Central Bank of the Republic of Turkey (CBRT / TCMB) speech scraper.

Primary source: TCMB native site (tcmb.gov.tr) — all Governor speeches in English.
Supplementary: BIS document_lists API for any speeches not on the native site.

CBRT communicates almost entirely through the Governor; Deputy Governors have
no dedicated speech archive on the TCMB website.
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
BIS_BASE = "https://www.bis.org"
BIS_DOC_LIST_URL = f"{BIS_BASE}/api/document_lists/cbspeeches.json"
TCMB_BASE = "https://www.tcmb.gov.tr"
TCMB_YEAR_URL = (
    f"{TCMB_BASE}/wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/"
    "Remarks+by+Governor/{year}/"
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": _UA, "Referer": f"{BIS_BASE}/cbspeeches/index.htm"})

# ── Member lists ─────────────────────────────────────────────────────────────

_CBRT_CURRENT = {
    "Fatih Karahan",         # Governor since Feb 2024
    "Osman Cevdet Akcay",   # Deputy Governor
    "Taha Cakmak",          # Deputy Governor
    "Cagri Kucuksahin",     # Deputy Governor
}

_CBRT_HISTORICAL = _CBRT_CURRENT | {
    "Hafize Gaye Erkan",    # Governor Jun 2023 - Feb 2024
    "Sahap Kavcioglu",      # Governor 2021-2023 (unorthodox rate cuts)
    "Naci Agbal",           # Governor Nov 2020 - Mar 2021
    "Murat Uysal",          # Governor Jul 2019 - Nov 2020
    "Murat Cetinkaya",      # Governor Apr 2016 - Jul 2019
    "Murat Cetinkaya",
    "Erkan Kilimci",
    "Emrah Senol",
}

ALL_CBRT = _CBRT_HISTORICAL

_CBRT_SURNAMES = [
    "Karahan", "Erkan", "Kavcioglu", "Agbal", "Uysal", "Cetinkaya",
    "Akcay", "Cakmak", "Kucuksahin", "Kilimci",
]

# Some surnames are common, handle carefully
_ALIASES = {
    "Karahan":     "Fatih Karahan",
    "Erkan":       "Hafize Gaye Erkan",
    "Kavcioglu":   "Sahap Kavcioglu",
    "Agbal":       "Naci Agbal",
    "Uysal":       "Murat Uysal",
    "Cetinkaya":   "Murat Cetinkaya",
    "Akcay":       "Osman Cevdet Akcay",
    "Cakmak":      "Taha Cakmak",
    "Kucuksahin":  "Cagri Kucuksahin",
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
    if name in ALL_CBRT:
        return name
    last = name.split()[-1] if name else ""
    return _ALIASES.get(last, name)


def _parse_date(text: str) -> str:
    m = _DATE_RE.search(text)
    if not m:
        return ""
    d, mon, y = m.group(1), m.group(2).capitalize(), m.group(3)
    return f"{y}-{_MONTHS[mon]}-{int(d):02d}"


def _matches_cbrt(title_raw: str) -> bool:
    return any(s in title_raw for s in _CBRT_SURNAMES)


# ── DB helpers ───────────────────────────────────────────────────────────────

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
    for col in ("body", "central_bank", "country", "body_en", "language", "relevant_to_mp",
                "original_score", "topic_scores", "body_language"):
        if col not in cols:
            conn.execute(f"ALTER TABLE speeches ADD COLUMN {col} TEXT")
    conn.commit()
    return conn


def save_rating(url: str, score: int, justification: str, rated_at: str,
                body_en: str = None) -> None:
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
    urls = {r[0] for r in conn.execute("SELECT url FROM speeches WHERE central_bank='CBRT'")}
    conn.close()
    return urls


# ── BIS fetch ────────────────────────────────────────────────────────────────

def _fetch_bis_doc_list() -> dict:
    print("  Downloading BIS document list (~7MB) ...")
    r = _SESSION.get(BIS_DOC_LIST_URL, timeout=90)
    r.raise_for_status()
    return r.json().get("list", {})


def _fetch_body_and_date(url: str) -> tuple[str, str]:
    pdf_url = url.replace(".htm", ".pdf")
    body, date_iso = "", ""

    try:
        r = _SESSION.get(pdf_url, timeout=60)
        if r.status_code == 200 and "pdf" in r.headers.get("content-type", "").lower():
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
            body = "\n".join(pages)
            date_iso = _parse_date(body)
    except Exception:
        pass

    if not body or not date_iso:
        try:
            r = _SESSION.get(url, timeout=30)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                pc = soup.find(id="pagecontent") or soup.find("main") or soup.body
                pc_text = pc.get_text(" ") if pc else ""
                if not date_iso:
                    date_iso = _parse_date(pc_text)
                if not body:
                    paras = [p.get_text(strip=True) for p in (pc or soup).find_all("p")
                             if len(p.get_text(strip=True)) > 30]
                    body = "\n\n".join(paras)
        except Exception:
            pass

    return body, date_iso


# ── TCMB native site scraping ─────────────────────────────────────────────────

# Governor date ranges for attribution
_GOVERNOR_RANGES = [
    ("Fatih Karahan",    "2024-02-02", "9999-12-31"),
    ("Hafize Gaye Erkan","2023-06-09", "2024-02-01"),
    ("Sahap Kavcioglu",  "2021-03-20", "2023-06-08"),
    ("Naci Agbal",       "2020-11-07", "2021-03-20"),
    ("Murat Uysal",      "2019-07-06", "2020-11-07"),
    ("Murat Cetinkaya",  "2016-04-19", "2019-07-06"),
]

# Date tag on TCMB pages: DD/MM/YYYY
_TCMB_DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def _governor_for_date(date_iso: str) -> str:
    for name, start, end in _GOVERNOR_RANGES:
        if start <= date_iso <= end:
            return name
    return "Fatih Karahan"


def _parse_tcmb_date(raw: str) -> str:
    m = _TCMB_DATE_RE.search(raw)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo}-{d}"
    return ""


def _scrape_tcmb_year(year: int) -> list[dict]:
    """Return list of {url, pdf_url, title, date, speaker} for a given year."""
    index_url = TCMB_YEAR_URL.format(year=year)
    try:
        r = _SESSION.get(index_url, timeout=20)
        if r.status_code != 200:
            return []
    except Exception:
        return []

    soup = BeautifulSoup(r.content, "html.parser")
    results = []
    seen_urls = set()

    for box in soup.find_all("div", class_="block-collection-box"):
        date_tag = box.find("div", class_="collection-tag")
        date_iso = _parse_tcmb_date(date_tag.get_text(strip=True)) if date_tag else ""

        # Find the main title link — prefer the HTML page link over direct PDF
        html_link = None
        pdf_link = None
        for a in box.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".pdf") or "MOD=AJPERES" in href:
                if pdf_link is None:
                    pdf_link = TCMB_BASE + href if href.startswith("/") else href
            else:
                if html_link is None and "/Main+Menu/" in href:
                    html_link = TCMB_BASE + href if href.startswith("/") else href

        title = ""
        # Try type-link class first, then any <a> with a title attribute
        title_a = box.find("a", class_="type-link") or box.find("a", title=True)
        if title_a:
            title = title_a.get("title") or title_a.get_text(strip=True)

        if not title:
            continue

        # Skip slides/presentations — they're supporting material, not speech text
        lower = title.lower()
        if "presentation" in lower or "remarks" in lower.replace("remarks by governor", ""):
            pass  # include remarks, skip presentations
        if "presentation" in lower and "speech" not in lower:
            continue

        url = html_link or pdf_link
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        if not date_iso:
            continue

        speaker = _governor_for_date(date_iso)
        results.append({
            "url": url,
            "pdf_url": pdf_link,
            "title": title,
            "date": date_iso,
            "speaker": speaker,
        })

    return results


def _fetch_tcmb_body(html_url: str, pdf_url: str) -> str:
    """Fetch speech body from HTML page, fall back to PDF."""
    body = ""

    # Try HTML first
    if html_url and not html_url.endswith(".pdf"):
        try:
            r = _SESSION.get(html_url, timeout=20)
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, "html.parser")
                # TCMB speech pages have content in .wysiwyg or main content area
                content = (soup.find(class_="wysiwyg") or
                           soup.find(class_="rich-text") or
                           soup.find("article") or
                           soup.find("main"))
                if content:
                    paras = [p.get_text(strip=True) for p in content.find_all("p")
                             if len(p.get_text(strip=True)) > 30]
                    body = "\n\n".join(paras)
                if not body:
                    # grab all text from page body, strip nav noise
                    for tag in soup(["nav", "header", "footer", "script", "style"]):
                        tag.decompose()
                    text = soup.get_text("\n", strip=True)
                    lines = [l for l in text.splitlines() if len(l.strip()) > 40]
                    body = "\n".join(lines)
        except Exception:
            pass

    # Fall back to PDF
    if len(body) < 200 and pdf_url:
        try:
            r = _SESSION.get(pdf_url, timeout=60)
            if r.status_code == 200 and "pdf" in r.headers.get("content-type", "").lower():
                with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                    pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
                body = "\n".join(pages)
        except Exception:
            pass

    return body


# ── Public entry points ───────────────────────────────────────────────────────

def _get_existing_date_speakers(conn: sqlite3.Connection) -> set:
    """Return set of (date, speaker) pairs already stored for CBRT."""
    rows = conn.execute(
        "SELECT date, speaker FROM speeches WHERE central_bank='CBRT'"
    ).fetchall()
    return {(r[0], r[1]) for r in rows}


def get_all_cbrt_speeches(start_year: int = 2016, end_year: int = None) -> list[dict]:
    """Scrape all CBRT speeches from TCMB native site + BIS, store to DB."""
    if end_year is None:
        end_year = datetime.now().year

    existing = get_existing_urls()
    conn = _conn()
    existing_date_speakers = _get_existing_date_speakers(conn)
    to_rate = []

    # ── TCMB native site (primary) ──
    total_native = 0
    for year in range(start_year, end_year + 1):
        entries = _scrape_tcmb_year(year)
        new = [e for e in entries
               if e["url"] not in existing
               and (e["date"], e["speaker"]) not in existing_date_speakers]
        total_native += len(new)
        print(f"  TCMB {year}: {len(entries)} listed, {len(new)} new")

        for e in new:
            body = _fetch_tcmb_body(e["url"], e.get("pdf_url"))
            if len(body) < 100:
                print(f"    SKIP (no body): {e['title'][:60]}")
                time.sleep(0.3)
                continue

            from translator import detect_language
            lang = detect_language(body, e["title"])

            conn.execute(
                "INSERT OR IGNORE INTO speeches "
                "(url, date, speaker, title, body, central_bank, country, language) "
                "VALUES (?, ?, ?, ?, ?, 'CBRT', 'TRY', ?)",
                (e["url"], e["date"], e["speaker"], e["title"], body, lang),
            )
            existing.add(e["url"])
            existing_date_speakers.add((e["date"], e["speaker"]))
            to_rate.append({**e, "body": body, "language": lang})
            print(f"    Stored: {e['speaker']} | {e['date']} | {e['title'][:55]}")
            time.sleep(0.4)

    conn.commit()

    # ── BIS (supplementary — catches any international speeches not on TCMB) ──
    cutoff = f"{start_year}-01-01"
    doc_list = _fetch_bis_doc_list()
    bis_new = []
    for path, item in doc_list.items():
        title_raw = item.get("short_title", "")
        pub_date = item.get("publication_start_date", "")
        if not pub_date or pub_date < cutoff:
            continue
        if not _matches_cbrt(title_raw):
            continue
        if ":" in title_raw:
            speaker_raw, _, speech_title = title_raw.partition(":")
            speaker = _normalize_speaker(speaker_raw.strip())
            title = speech_title.strip()
        else:
            speaker, title = "", title_raw
        if speaker not in ALL_CBRT:
            continue
        url = f"{BIS_BASE}{path}.htm"
        if url not in existing:
            bis_new.append((url, speaker, title, pub_date))

    print(f"  BIS: {len(bis_new)} additional speeches not already in DB")
    for url, speaker, title, pub_date in bis_new:
        body, date_iso = _fetch_body_and_date(url)
        if not date_iso:
            date_iso = pub_date
        if len(body) < 100:
            time.sleep(0.3)
            continue
        from translator import detect_language
        lang = detect_language(body, title)
        conn.execute(
            "INSERT OR IGNORE INTO speeches "
            "(url, date, speaker, title, body, central_bank, country, language) "
            "VALUES (?, ?, ?, ?, ?, 'CBRT', 'TRY', ?)",
            (url, date_iso, speaker, title, body, lang),
        )
        existing.add(url)
        to_rate.append({"url": url, "date": date_iso, "speaker": speaker,
                        "title": title, "body": body, "language": lang})
        time.sleep(0.4)

    conn.commit()
    conn.close()
    print(f"\n  Total new: {len(to_rate)} CBRT speeches stored")
    return to_rate


def get_new_cbrt_speeches() -> list[dict]:
    """Check TCMB native site + BIS for new CBRT speeches (current year + previous)."""
    year = datetime.now().year
    check_years = [year - 1, year] if datetime.now().month <= 3 else [year]

    existing = get_existing_urls()
    conn = _conn()
    to_rate = []

    # TCMB native
    for y in check_years:
        for e in _scrape_tcmb_year(y):
            if e["url"] in existing:
                continue
            body = _fetch_tcmb_body(e["url"], e.get("pdf_url"))
            if len(body) < 100:
                time.sleep(0.3)
                continue
            from translator import detect_language
            lang = detect_language(body, e["title"])
            conn.execute(
                "INSERT OR IGNORE INTO speeches "
                "(url, date, speaker, title, body, central_bank, country, language) "
                "VALUES (?, ?, ?, ?, ?, 'CBRT', 'TRY', ?)",
                (e["url"], e["date"], e["speaker"], e["title"], body, lang),
            )
            existing.add(e["url"])
            to_rate.append({**e, "body": body, "language": lang})
            time.sleep(0.4)

    conn.commit()

    # Pick up stored-but-unrated speeches
    cutoff = f"{year - 1}-01-01"
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body, language, body_en FROM speeches "
        "WHERE central_bank='CBRT' AND score IS NULL AND date >= ? AND body IS NOT NULL",
        (cutoff,),
    ).fetchall()
    conn.close()

    already = {s["url"] for s in to_rate}
    for url, dt, speaker, title, body, lang, body_en in unrated:
        if url not in already and body:
            to_rate.append({"url": url, "date": dt, "speaker": speaker,
                            "title": title, "body": body,
                            "language": lang or "en", "body_en": body_en or ""})

    print(f"  {len(to_rate)} CBRT speeches to rate")
    return to_rate
