"""
Banca Națională a României (BNR) speech scraper.

Primary source: BIS document_lists API (international speeches).
Supplementary: native bnr.ro website for domestic Romanian speeches.

BNR is primarily represented internationally by Governor Isarescu, who has
held the role since 1990. Coverage on BIS is good for his international speeches.
"""

import html as html_module
import io
import re
import sqlite3
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

DB_PATH = Path("data/speeches.db")
BIS_BASE = "https://www.bis.org"
BIS_DOC_LIST_URL = f"{BIS_BASE}/api/document_lists/cbspeeches.json"

BNR_BASE = "https://www.bnr.ro"
BNR_SPEECHES_URL = f"{BNR_BASE}/Speeches--6046.aspx"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": _UA})

# ── Member lists ─────────────────────────────────────────────────────────────

_BNR_CURRENT = {
    "Mugur Isarescu",
    "Florin Georgescu",
    "Leonardo Badea",
    "Eugen Nicolaescu",
    "Csaba Balint",
}

_BNR_HISTORICAL = _BNR_CURRENT | {
    "Bogdan Olteanu",
    "Cristian Popa",
    "Nicolae Cinteza",
    "Virgil Stoenescu",
    "Liviu Voinea",
}

ALL_BNR = _BNR_HISTORICAL

_BNR_SURNAMES = [
    "Isarescu", "Georgescu", "Badea", "Nicolaescu", "Balint",
    "Olteanu", "Popa", "Voinea",
]

_ALIASES = {
    "Isarescu":   "Mugur Isarescu",
    "Georgescu":  "Florin Georgescu",
    "Badea":      "Leonardo Badea",
    "Nicolaescu": "Eugen Nicolaescu",
    "Balint":     "Csaba Balint",
    "Olteanu":    "Bogdan Olteanu",
    "Popa":       "Cristian Popa",
    "Voinea":     "Liviu Voinea",
}

def _ascii_fold(s: str) -> str:
    """Decode HTML entities then strip diacritics to ASCII (e.g. Is&#259;rescu → Isarescu)."""
    decoded = html_module.unescape(s)
    return unicodedata.normalize("NFKD", decoded).encode("ascii", "ignore").decode("ascii")


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
    if name in ALL_BNR:
        return name
    last = name.split()[-1] if name else ""
    # Try exact match first, then ASCII-folded match
    if last in _ALIASES:
        return _ALIASES[last]
    folded_last = _ascii_fold(last)
    return _ALIASES.get(folded_last, name)


def _parse_date(text: str) -> str:
    m = _DATE_RE.search(text)
    if not m:
        return ""
    d, mon, y = m.group(1), m.group(2).capitalize(), m.group(3)
    return f"{y}-{_MONTHS[mon]}-{int(d):02d}"


def _matches_bnr(title_raw: str) -> bool:
    folded = _ascii_fold(title_raw)
    return any(s in folded for s in _BNR_SURNAMES)


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
    urls = {r[0] for r in conn.execute("SELECT url FROM speeches WHERE central_bank='BNR'")}
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


# ── BNR native site fetch ─────────────────────────────────────────────────────

def _fetch_bnr_native_speeches(year: int) -> list[dict]:
    """
    Scrape bnr.ro speeches listing page for a given year.
    Returns list of {url, title, date_raw, speaker_raw}.
    The BNR speeches page uses a year filter parameter.
    """
    url = f"{BNR_SPEECHES_URL}?year={year}"
    items = []
    try:
        resp = _SESSION.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"    BNR native fetch failed for {year}: {e}")
        return items

    soup = BeautifulSoup(resp.text, "html.parser")

    # BNR listing: look for speech entries with date + title pattern
    # The structure varies but typically uses a list or table
    for row in soup.find_all(["tr", "li", "div"], class_=re.compile(r"speech|item|row|entry", re.I)):
        link = row.find("a", href=True)
        if not link:
            continue
        href = link["href"]
        title = link.get_text(strip=True)
        if not title or len(title) < 5:
            continue
        full_url = f"{BNR_BASE}{href}" if href.startswith("/") else href

        # Try to find date in row text
        row_text = row.get_text(" ")
        date_raw = ""
        # Romanian date format: DD.MM.YYYY or DD Month YYYY
        dm = re.search(r"\d{1,2}[./]\d{1,2}[./]\d{4}", row_text)
        if dm:
            date_raw = dm.group(0)

        items.append({"url": full_url, "title": title, "date_raw": date_raw, "speaker_raw": ""})

    return items


def _parse_bnr_date(raw: str) -> str:
    if not raw:
        return ""
    # Try DD.MM.YYYY
    m = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", raw.strip())
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
    return _parse_date(raw)  # try English date parser


# ── Public entry points ───────────────────────────────────────────────────────

def get_all_bnr_speeches(start_year: int = 2021, end_year: int = None) -> list[dict]:
    """Scrape all BNR speeches via BIS from start_year to end_year, store to DB."""
    if end_year is None:
        end_year = datetime.now().year

    cutoff = f"{start_year}-01-01"
    end_date = f"{end_year}-12-31"
    existing = get_existing_urls()
    doc_list = _fetch_bis_doc_list()

    speeches = []
    for path, item in doc_list.items():
        title_raw = html_module.unescape(item.get("short_title", "").strip())
        pub_date = item.get("publication_start_date", "")
        if not pub_date or pub_date < cutoff or pub_date > end_date:
            continue
        if not _matches_bnr(title_raw):
            continue

        if ":" in title_raw:
            speaker_raw, _, speech_title = title_raw.partition(":")
            speaker = _normalize_speaker(speaker_raw.strip())
            title = speech_title.strip()
        else:
            speaker = ""
            title = title_raw

        if speaker not in ALL_BNR:
            continue

        url = f"{BIS_BASE}{path}.htm"
        if url in existing:
            continue
        speeches.append((url, speaker, title, pub_date))

    speeches.sort(key=lambda x: x[3])
    print(f"  {len(speeches)} new BNR speeches to fetch from BIS (since {cutoff})")

    conn = _conn()
    to_rate = []
    for i, (url, speaker, title, pub_date) in enumerate(speeches, 1):
        body, date_iso = _fetch_body_and_date(url)
        if not date_iso:
            date_iso = pub_date
        if len(body) < 100:
            print(f"  [{i}/{len(speeches)}] SKIP (no body): {title[:60]}")
            time.sleep(0.3)
            continue

        from translator import detect_language
        lang = detect_language(body, title)

        conn.execute(
            "INSERT OR IGNORE INTO speeches "
            "(url, date, speaker, title, body, central_bank, country, language) "
            "VALUES (?, ?, ?, ?, ?, 'BNR', 'RON', ?)",
            (url, date_iso, speaker, title, body, lang),
        )
        existing.add(url)
        to_rate.append({"url": url, "date": date_iso, "speaker": speaker,
                        "title": title, "body": body, "language": lang})
        print(f"  [{i}/{len(speeches)}] Stored: {speaker} | {date_iso} | {title[:55]}")
        time.sleep(0.4)

    conn.commit()
    conn.close()
    return to_rate


def get_new_bnr_speeches() -> list[dict]:
    """Check BIS for new BNR speeches from this year (and previous if early in year)."""
    year = datetime.now().year
    cutoff_year = year - 1 if datetime.now().month <= 3 else year
    cutoff = f"{cutoff_year}-01-01"
    end_date = f"{year}-12-31"

    existing = get_existing_urls()
    doc_list = _fetch_bis_doc_list()

    candidates = []
    for path, item in doc_list.items():
        title_raw = html_module.unescape(item.get("short_title", "").strip())
        pub_date = item.get("publication_start_date", "")
        if not pub_date or pub_date < cutoff or pub_date > end_date:
            continue
        if not _matches_bnr(title_raw):
            continue

        if ":" in title_raw:
            speaker_raw, _, speech_title = title_raw.partition(":")
            speaker = _normalize_speaker(speaker_raw.strip())
            title = speech_title.strip()
        else:
            speaker = ""
            title = title_raw

        if speaker not in _BNR_CURRENT:
            continue

        url = f"{BIS_BASE}{path}.htm"
        if url in existing:
            continue
        candidates.append((url, speaker, title, pub_date))

    print(f"  BNR: {len(candidates)} new speeches on BIS")

    conn = _conn()
    to_rate = []
    for url, speaker, title, pub_date in candidates:
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
            "VALUES (?, ?, ?, ?, ?, 'BNR', 'RON', ?)",
            (url, date_iso, speaker, title, body, lang),
        )
        existing.add(url)
        to_rate.append({"url": url, "date": date_iso, "speaker": speaker,
                        "title": title, "body": body, "language": lang})
        time.sleep(0.4)

    conn.commit()

    # Pick up stored-but-unrated current-year speeches
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body, language, body_en FROM speeches "
        "WHERE central_bank='BNR' AND score IS NULL AND date >= ? AND body IS NOT NULL",
        (f"{year}-01-01",),
    ).fetchall()
    conn.close()

    already = {s["url"] for s in to_rate}
    for url, dt, speaker, title, body, lang, body_en in unrated:
        if url not in already and speaker in _BNR_CURRENT and body:
            to_rate.append({"url": url, "date": dt, "speaker": speaker,
                            "title": title, "body": body,
                            "language": lang or "en", "body_en": body_en or ""})

    print(f"  {len(to_rate)} BNR speeches to rate")
    return to_rate
