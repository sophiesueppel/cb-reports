import io
import json
import os
import posixpath
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pdfplumber
import requests
from bs4 import BeautifulSoup

BOJ_BASE = "https://www.boj.or.jp"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))

_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

# BoJ names BoJ-website style are "FAMILY Given" (family name in all caps).
# We normalise to "Given Family" for storage consistency.
def _normalize_name(raw: str) -> str:
    """Convert 'FAMILY Given[, Role]' → 'Given Family'."""
    name_part = raw.split(",")[0].strip()
    parts = name_part.split()
    if not parts:
        return raw
    if parts[0].isupper() and len(parts) >= 2:
        family = parts[0].capitalize()
        given = " ".join(parts[1:])
        return f"{given} {family}"
    return name_part


# ---------------------------------------------------------------------------
# Member list (Policy Board only — excludes Executive Directors)
# ---------------------------------------------------------------------------

_BOJ_BOARD_DEFAULT = [
    "Kazuo Ueda",
    "Ryozo Himino",
    "Shinichi Uchida",
    "Naoki Tamura",
    "Hajime Takata",
    "Junko Nakagawa",
    "Junko Koeda",
    "Kazuyuki Masu",
    "Toichiro Asada",
]

def _load_policy_board() -> set[str]:
    p = Path("data/members.json")
    if p.exists():
        return set(json.loads(p.read_text(encoding="utf-8")).get("boj_policy_board", _BOJ_BOARD_DEFAULT))
    return set(_BOJ_BOARD_DEFAULT)


BOJ_POLICY_BOARD = _load_policy_board()

# All Policy Board members active at any point since 2021 (for historical backfill).
ALL_BOJ_BOARD = BOJ_POLICY_BOARD | {
    "Haruhiko Kuroda",
    "Masayoshi Amamiya",
    "Masazumi Wakatabe",
    "Seiji Adachi",
    "Hitoshi Suzuki",
}


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


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_JP_MONTH_MAP = {
    "1": "01", "2": "02", "3": "03", "4": "04", "5": "05", "6": "06",
    "7": "07", "8": "08", "9": "09", "10": "10", "11": "11", "12": "12",
}


def _parse_boj_date(raw: str) -> str:
    """Parse English ('June 25, 2026') or Japanese ('2024年12月25日') → 'YYYY-MM-DD'."""
    raw = raw.strip()
    # Japanese: 2024年12月25日 or 2024年12月 5日 (with space-padded day)
    m = re.match(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # English: June 25, 2026 or Mar. 3, 2026
    m = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2}),\s+(\d{4})", raw)
    if m:
        mon = _MONTH_MAP.get(m.group(1)[:3].lower(), "01")
        return f"{m.group(3)}-{mon}-{int(m.group(2)):02d}"
    return raw


def _pdf_url(speech_url: str) -> str:
    """Derive the likely PDF URL from a BoJ speech page URL.

    /en/about/press/koen_2026/ko260625a.htm
    → /en/about/press/koen_2026/data/ko260625a1.pdf
    """
    parsed = urlparse(speech_url)
    dir_part = posixpath.dirname(parsed.path)
    stem = posixpath.splitext(posixpath.basename(parsed.path))[0]
    pdf_path = f"{dir_part}/data/{stem}1.pdf"
    return urlunparse(parsed._replace(path=pdf_path))


def _find_pdf_link(soup: BeautifulSoup, speech_url: str) -> str | None:
    """Scan speech page HTML for a PDF download link."""
    for a in soup.find_all("a", href=re.compile(r"\.pdf$", re.I)):
        href = a["href"]
        if not href.startswith("http"):
            base = speech_url.rsplit("/", 1)[0]
            href = f"{base}/{href.lstrip('/')}"
        return href
    return None


def _extract_pdf_text(pdf_url: str, session: requests.Session) -> str:
    """Download a PDF and extract all text using pdfplumber."""
    try:
        r = session.get(pdf_url, timeout=45)
        if r.status_code != 200:
            return ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
        return "\n".join(pages)
    except Exception as e:
        print(f"    PDF extraction failed ({pdf_url}): {e}")
        return ""


# ---------------------------------------------------------------------------
# Index scraping
# ---------------------------------------------------------------------------

BOJ_BASE_ARCHIVE = "https://www2.boj.or.jp"


def _scrape_year_index(year: int, session: requests.Session) -> list[dict]:
    """Scrape all speech entries from one year's BoJ index page.
    Years < 2011 fall back to the archived domain www2.boj.or.jp.
    """
    candidates = [f"{BOJ_BASE}/en/about/press/koen_{year}/index.htm"]
    if year < 2011:
        candidates.append(f"{BOJ_BASE_ARCHIVE}/en/about/press/koen_{year}/index.htm")

    r = None
    fetched_base = BOJ_BASE
    for url in candidates:
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code == 200:
                r = resp
                # Determine base domain from whichever URL succeeded
                fetched_base = BOJ_BASE_ARCHIVE if "www2" in url else BOJ_BASE
                break
        except Exception as e:
            print(f"  BoJ {year} index fetch failed ({url}): {e}")
    if r is None:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    entries = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        date_raw = cells[0].get_text(strip=True)
        speaker_raw = cells[1].get_text(strip=True)
        title_cell = cells[2]
        a_tag = title_cell.find("a")
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        href = a_tag.get("href", "")
        if not href:
            continue
        speech_url = href if href.startswith("http") else f"{fetched_base}{href}"
        date = _parse_boj_date(date_raw)
        speaker = _normalize_name(speaker_raw)
        if not date or not speaker or not title:
            continue
        entries.append({
            "url":     speech_url,
            "date":    date,
            "speaker": speaker,
            "title":   title,
        })
    return entries


# Japanese Policy Board name → canonical English name map
_BOJ_JP_NAME_MAP = {
    "植田 和男": "Kazuo Ueda",
    "植田和男":  "Kazuo Ueda",
    "氷見野 良三": "Ryozo Himino",
    "氷見野良三":  "Ryozo Himino",
    "内田 真一": "Shinichi Uchida",
    "内田真一":  "Shinichi Uchida",
    "田村 直樹": "Naoki Tamura",
    "田村直樹":  "Naoki Tamura",
    "高田 創":   "Hajime Takata",
    "高田創":    "Hajime Takata",
    "中川 順子": "Junko Nakagawa",
    "中川順子":  "Junko Nakagawa",
    "小枝 淳子": "Junko Koeda",
    "小枝淳子":  "Junko Koeda",
    "増田 和也": "Kazuyuki Masu",
    "増田和也":  "Kazuyuki Masu",
    "浅田 俊一": "Toichiro Asada",
    "浅田俊一":  "Toichiro Asada",
    "黒田 東彦": "Haruhiko Kuroda",
    "黒田東彦":  "Haruhiko Kuroda",
    "天野 篤":   "Masayoshi Amamiya",
    "天野篤":    "Masayoshi Amamiya",
    "若田部 昌澄": "Masazumi Wakatabe",
    "若田部昌澄":  "Masazumi Wakatabe",
    "安達 誠司": "Seiji Adachi",
    "安達誠司":  "Seiji Adachi",
    "鈴木 人司": "Hitoshi Suzuki",
    "鈴木人司":  "Hitoshi Suzuki",
    "中村 豊明": "Toyoaki Nakamura",
    "中村豊明":  "Toyoaki Nakamura",
    "野口 旭":   "Asahi Noguchi",
    "野口旭":    "Asahi Noguchi",
    "中川 準子": "Junko Nakagawa",  # alternate kanji variant
}

# JP index uses "Family名+title" e.g. "植田総裁" — map family kanji → English full name
_BOJ_JP_FAMILY_MAP = {
    "植田": "Kazuo Ueda",
    "氷見野": "Ryozo Himino",
    "内田": "Shinichi Uchida",
    "田村": "Naoki Tamura",
    "高田": "Hajime Takata",
    "中川": "Junko Nakagawa",
    "小枝": "Junko Koeda",
    "増田": "Kazuyuki Masu",
    "浅田": "Toichiro Asada",
    "黒田": "Haruhiko Kuroda",
    "天野": "Masayoshi Amamiya",
    "若田部": "Masazumi Wakatabe",
    "安達": "Seiji Adachi",
    "鈴木": "Hitoshi Suzuki",
    "中村": "Toyoaki Nakamura",
    "野口": "Asahi Noguchi",
    "栄畑": "Hideaki Sakahata",
}


def _resolve_jp_speaker(raw: str) -> str | None:
    """Resolve 'Family名+title' (e.g. '植田総裁') to English full name."""
    # Try exact match in full-name map first
    name = _BOJ_JP_NAME_MAP.get(raw) or _BOJ_JP_NAME_MAP.get(raw.replace(" ", ""))
    if name:
        return name
    # Strip title suffixes (総裁, 副総裁, 審議委員, 理事, etc.) and match by family name
    family = re.sub(r"(総裁|副総裁|審議委員|理事|委員長|副委員長|局長|参与).*$", "", raw).strip()
    return _BOJ_JP_FAMILY_MAP.get(family)


def _scrape_year_index_ja(year: int, session: requests.Session) -> list[dict]:
    """Scrape the Japanese-language BoJ speech index for one year.

    URL pattern: /about/press/koen_{year}/index.htm  (no /en/)
    Returns entries with language='ja'. Speaker names are resolved from
    the Japanese kanji → English map; unrecognised speakers are dropped.
    Entries whose English-equivalent URL is already in the English index
    are duplicates and skipped by the caller.
    """
    url = f"{BOJ_BASE}/about/press/koen_{year}/index.htm"
    try:
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            return []
    except Exception as e:
        print(f"  BoJ JP {year} index fetch failed: {e}")
        return []

    # Force UTF-8 — BoJ Japanese pages are Shift-JIS or UTF-8; requests may misdetect
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    entries = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        date_raw = cells[0].get_text(strip=True)
        speaker_raw = cells[1].get_text(strip=True).strip()
        title_cell = cells[2]
        a_tag = title_cell.find("a")
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        href = a_tag.get("href", "")
        if not href:
            continue
        speech_url = href if href.startswith("http") else f"{BOJ_BASE}{href}"
        date = _parse_boj_date(date_raw)
        if not date:
            continue

        # Resolve speaker: family+title map, then full kanji map, then romaji fallback
        speaker = _resolve_jp_speaker(speaker_raw)
        if not speaker:
            m = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+)", speaker_raw)
            if m:
                speaker = _normalize_name(m.group(1))
        if not speaker or speaker not in ALL_BOJ_BOARD:
            continue

        entries.append({
            "url":      speech_url,
            "date":     date,
            "speaker":  speaker,
            "title":    title,
            "language": "ja",
        })
    return entries


def _pdf_url_ja(speech_url: str) -> str:
    """Derive the likely PDF URL for a Japanese BoJ speech page.

    /about/press/koen_2026/ko260625a.htm
    → /about/press/koen_2026/data/ko260625a1.pdf
    """
    parsed = urlparse(speech_url)
    dir_part = posixpath.dirname(parsed.path)
    stem = posixpath.splitext(posixpath.basename(parsed.path))[0]
    pdf_path = f"{dir_part}/data/{stem}1.pdf"
    return urlunparse(parsed._replace(path=pdf_path))


# ---------------------------------------------------------------------------
# Speech text retrieval
# ---------------------------------------------------------------------------

def _get_speech_text(speech_url: str, session: requests.Session) -> str:
    """Fetch a BoJ speech page and extract the full text from the PDF."""
    # Try derived PDF URL first (fast path)
    pdf_url = _pdf_url(speech_url)
    text = _extract_pdf_text(pdf_url, session)
    if len(text) >= 300:
        return text

    # Fallback: fetch the HTML page and hunt for a PDF link
    try:
        r = session.get(speech_url, timeout=15)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        fallback_url = _find_pdf_link(soup, speech_url)
        if fallback_url and fallback_url != pdf_url:
            text = _extract_pdf_text(fallback_url, session)
    except Exception:
        pass
    return text


# ---------------------------------------------------------------------------
# DB write helpers
# ---------------------------------------------------------------------------

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
    urls = {r[0] for r in conn.execute("SELECT url FROM speeches WHERE central_bank='Bank of Japan'")}
    conn.close()
    return urls


def _store_speech(rec: dict, conn: sqlite3.Connection) -> None:
    lang = rec.get("language", "en")
    conn.execute(
        "INSERT OR IGNORE INTO speeches "
        "(url, date, speaker, title, body, central_bank, country, language) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (rec["url"], rec["date"], rec["speaker"], rec["title"],
         rec.get("body", ""), "Bank of Japan", "JPN", lang),
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def get_all_boj_speeches(start_year: int = 2021, end_year: int = None) -> list[dict]:
    """Scrape all Policy Board speeches from start_year to end_year, store to DB.

    Returns list of stored-but-unrated speeches (for the caller to rate).
    Does NOT fetch PDFs for years older than start_year — those are stored
    as metadata-only rows and can be backfilled later.
    """
    if end_year is None:
        end_year = datetime.now().year

    session = _session()
    conn = _conn()
    existing = get_existing_urls()

    stored = 0
    to_rate = []

    for year in range(start_year, end_year + 1):
        print(f"  Fetching BoJ {year} index ...")
        # English index first
        en_entries = _scrape_year_index(year, session)
        en_urls = {e["url"] for e in en_entries}
        # Japanese index — only collect URLs not already on the English index
        ja_entries = _scrape_year_index_ja(year, session)
        # Deduplicate: JP speech URLs share the same stem as EN URLs (just no /en/)
        # e.g. /about/press/koen_2026/ko260625a.htm vs /en/about/press/koen_2026/ko260625a.htm
        ja_new = []
        for sp in ja_entries:
            en_equiv = sp["url"].replace("/about/press/", "/en/about/press/")
            if en_equiv not in en_urls and sp["url"] not in existing:
                ja_new.append(sp)

        all_entries = [(sp, "en") for sp in en_entries] + [(sp, "ja") for sp in ja_new]
        year_new = 0
        for sp, lang in all_entries:
            if sp["speaker"] not in ALL_BOJ_BOARD:
                continue
            if sp["url"] in existing:
                continue

            # For Japanese-only speeches, try the JP PDF URL
            if lang == "ja":
                body = _extract_pdf_text(_pdf_url_ja(sp["url"]), session)
            else:
                body = _get_speech_text(sp["url"], session)
            sp["body"] = body
            sp["language"] = lang
            _store_speech(sp, conn)
            existing.add(sp["url"])
            year_new += 1
            stored += 1

            if sp["speaker"] in BOJ_POLICY_BOARD and body:
                to_rate.append(sp)

            time.sleep(0.4)

        print(f"    {year}: {len(en_entries)} EN + {len(ja_new)} JP-only, {year_new} new stored")

    conn.commit()
    conn.close()
    print(f"  Total new speeches stored: {stored}")
    return to_rate


def get_new_boj_2026() -> list[dict]:
    """Scrape 2026 BoJ speeches, return any Policy Board speeches not yet rated."""
    print("Fetching BoJ 2026 speech index ...")
    session = _session()
    year = datetime.now().year

    entries = _scrape_year_index(year, session)
    # Also pick up any stragglers from the previous year if it's early in the year
    if datetime.now().month <= 3:
        entries += _scrape_year_index(year - 1, session)

    print(f"  {len(entries)} speeches found on BoJ website")

    existing = get_existing_urls()
    conn = _conn()

    to_rate = []
    for sp in entries:
        if sp["speaker"] not in ALL_BOJ_BOARD:
            continue  # Executive Director or other non-voting staff
        if sp["url"] in existing:
            continue  # Already stored

        print(f"  Fetching text: {sp['speaker']} | {sp['title'][:55]}")
        body = _get_speech_text(sp["url"], session)
        sp["body"] = body
        _store_speech(sp, conn)

        if sp["speaker"] in BOJ_POLICY_BOARD and body and sp["date"] >= "2026-01-01":
            to_rate.append(sp)

        time.sleep(0.5)

    conn.commit()
    conn.close()

    # Also find any stored-but-unrated 2026 Policy Board speeches
    conn2 = _conn()
    unrated = conn2.execute(
        "SELECT url, date, speaker, title, body FROM speeches "
        "WHERE central_bank='Bank of Japan' AND score IS NULL AND date >= '2026-01-01'",
    ).fetchall()
    conn2.close()

    already_queued = {s["url"] for s in to_rate}
    for row in unrated:
        url, date, speaker, title, body = row
        if url not in already_queued and speaker in BOJ_POLICY_BOARD and body:
            to_rate.append({"url": url, "date": date, "speaker": speaker, "title": title, "body": body})

    print(f"  {len(to_rate)} new 2026 Policy Board speeches to rate")
    return to_rate
