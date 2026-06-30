"""
Central Bank of the Republic of Turkey (CBRT / TCMB) speech scraper.

Uses BIS document_lists API to discover CBRT speeches. Turkey has had
significant monetary policy cycles: the unorthodox rate-cutting regime
(2021-2023) and the subsequent orthodox tightening under Erkan/Karahan.

BIS coverage of CBRT is good — Governors frequently speak at international
conferences indexed by BIS.
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


# ── Public entry points ───────────────────────────────────────────────────────

def get_all_cbrt_speeches(start_year: int = 2021, end_year: int = None) -> list[dict]:
    """Scrape all CBRT speeches via BIS from start_year to end_year, store to DB."""
    if end_year is None:
        end_year = datetime.now().year

    cutoff = f"{start_year}-01-01"
    end_date = f"{end_year}-12-31"
    existing = get_existing_urls()
    doc_list = _fetch_bis_doc_list()

    speeches = []
    for path, item in doc_list.items():
        title_raw = item.get("short_title", "")
        pub_date = item.get("publication_start_date", "")
        if not pub_date or pub_date < cutoff or pub_date > end_date:
            continue
        if not _matches_cbrt(title_raw):
            continue

        if ":" in title_raw:
            speaker_raw, _, speech_title = title_raw.partition(":")
            speaker = _normalize_speaker(speaker_raw.strip())
            title = speech_title.strip()
        else:
            speaker = ""
            title = title_raw

        if speaker not in ALL_CBRT:
            continue

        url = f"{BIS_BASE}{path}.htm"
        if url in existing:
            continue
        speeches.append((url, speaker, title, pub_date))

    speeches.sort(key=lambda x: x[3])
    print(f"  {len(speeches)} new CBRT speeches to fetch from BIS (since {cutoff})")

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
            "VALUES (?, ?, ?, ?, ?, 'CBRT', 'TRY', ?)",
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


def get_new_cbrt_speeches() -> list[dict]:
    """Check BIS for new CBRT speeches from this year (and previous if early in year)."""
    year = datetime.now().year
    cutoff_year = year - 1 if datetime.now().month <= 3 else year
    cutoff = f"{cutoff_year}-01-01"
    end_date = f"{year}-12-31"

    existing = get_existing_urls()
    doc_list = _fetch_bis_doc_list()

    candidates = []
    for path, item in doc_list.items():
        title_raw = item.get("short_title", "")
        pub_date = item.get("publication_start_date", "")
        if not pub_date or pub_date < cutoff or pub_date > end_date:
            continue
        if not _matches_cbrt(title_raw):
            continue

        if ":" in title_raw:
            speaker_raw, _, speech_title = title_raw.partition(":")
            speaker = _normalize_speaker(speaker_raw.strip())
            title = speech_title.strip()
        else:
            speaker = ""
            title = title_raw

        if speaker not in _CBRT_CURRENT:
            continue

        url = f"{BIS_BASE}{path}.htm"
        if url in existing:
            continue
        candidates.append((url, speaker, title, pub_date))

    print(f"  CBRT: {len(candidates)} new speeches on BIS")

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
            "VALUES (?, ?, ?, ?, ?, 'CBRT', 'TRY', ?)",
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
        "WHERE central_bank='CBRT' AND score IS NULL AND date >= ? AND body IS NOT NULL",
        (f"{year}-01-01",),
    ).fetchall()
    conn.close()

    already = {s["url"] for s in to_rate}
    for url, dt, speaker, title, body, lang, body_en in unrated:
        if url not in already and speaker in _CBRT_CURRENT and body:
            to_rate.append({"url": url, "date": dt, "speaker": speaker,
                            "title": title, "body": body,
                            "language": lang or "en", "body_en": body_en or ""})

    print(f"  {len(to_rate)} CBRT speeches to rate")
    return to_rate
