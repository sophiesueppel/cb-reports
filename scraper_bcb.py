"""
BCB (Banco Central do Brasil) speech scraper.

Uses the BCB's Portuguese /acessoinformacao/discursos API (requires a browser
session via Playwright to authenticate):
  - List:  /api/servico/sitebcb/discursos?ano=<YEAR>
  - PDFs:  https://www.bcb.gov.br/<ServerRelativeUrl>  (direct download)

Portuguese page has far more speeches than the English API (400+ vs 68 for 2021-26).
PDF text is in Portuguese; GPT-4 handles Portuguese fine for hawkish/dovish scoring.
"""

import io
import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests

BCB_BASE = "https://www.bcb.gov.br"
DISCURSOS_PAGE = f"{BCB_BASE}/acessoinformacao/discursos"
DISCURSOS_API = f"{BCB_BASE}/api/servico/sitebcb/discursos"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
    "Referer": DISCURSOS_PAGE,
}

DB_PATH = Path("data/speeches.db")

# ---------------------------------------------------------------------------
# Copom member lists (all 9 members vote, so track all board members)
# ---------------------------------------------------------------------------

_COPOM_CURRENT = {
    "Gabriel Galípolo",          # President, 2025-present
    "Diogo Guillen",             # Deputy Governor for Economic Policy, 2021-present
    "Paulo Picchetti",           # Deputy Governor for Monetary Policy, 2023-present
    "Renato Gomes",              # Deputy Governor
    "Nilton David",              # Deputy Governor
    "Carolina de Assis Barros",  # Deputy Governor for Prudential Supervision, 2023-present
    "Ailton Santos",             # Deputy Governor for Regulation, 2023-present
    "Rodrigo Teixeira",          # Deputy Governor for Institutional Relations, 2023-present
    "Sérgio Gouvêa",            # Deputy Governor for Corporate Management, 2023-present
}

_COPOM_HISTORICAL = _COPOM_CURRENT | {
    "Roberto Campos Neto",       # President/Governor, 2019-2024
    "Fabio Kanczuk",             # Deputy Governor for Economic Policy, 2019-2022
    "Fernanda Guardado",         # Deputy Governor, 2019-2022
    "Bruno Serra Fernandes",     # Deputy Governor, 2019-2023
    "Maurício Costa de Moura",   # Deputy Governor, 2021-2023
    "Otavio Ribeiro Damaso",     # Deputy Governor, 2019-2021
    "Paulo Souza",               # Deputy Governor, 2021-2022
}

ALL_COPOM = _COPOM_HISTORICAL

# Name variants that appear in the discursos API → canonical name
_BCB_ALIASES: dict[str, str] = {
    # Renato Gomes — full legal name, case variants
    "Renato Dias De Brito Gomes": "Renato Gomes",
    "Renato Dias de Brito Gomes": "Renato Gomes",
    # Nilton David
    "Nilton José Aquino Moreira": "Nilton David",
    "Nilton Jose Aquino Moreira": "Nilton David",
    # Ailton Santos's full name includes "Aquino"
    "Ailton Aquino": "Ailton Santos",
    "Ailton Aquino Santos": "Ailton Santos",
    "Ailton de Aquino": "Ailton Santos",
    # Diogo Guillen — full name vs short name
    "Diogo Abry Guillen": "Diogo Guillen",
    # Otávio Damaso — accent variants, middle name absent
    "Otávio Damaso": "Otavio Ribeiro Damaso",
    "Otavio Damaso": "Otavio Ribeiro Damaso",
    "Otávio Damaso": "Otavio Ribeiro Damaso",
    # Slightly different spacing / accents for Sérgio Gouvêa
    "Sergio Gouvea": "Sérgio Gouvêa",
    "Sergio Gouvêa": "Sérgio Gouvêa",
    "Sérgio Gouvea": "Sérgio Gouvêa",
    # Maurício Costa de Moura — accent + short form
    "Mauricio Costa de Moura": "Maurício Costa de Moura",
    "Mauricio Moura": "Maurício Costa de Moura",
    "Maurício Moura": "Maurício Costa de Moura",
    # Roberto Campos Neto variant
    "Roberto Campos Neto J.P. Morgan": "Roberto Campos Neto",
}


def _normalize_name(raw: str) -> str:
    """Strip HTML tags, trailing punctuation, and normalise a raw speaker name."""
    name = re.sub(r"<[^>]+>", "", raw).strip()
    name = name.rstrip(".")  # strip trailing period (API sometimes adds one)
    return _BCB_ALIASES.get(name, name)


_JOINT_RE = re.compile(r",\s*|\s+e\s+", re.IGNORECASE)


def _extract_speaker(descricao: str, titulo: str = "") -> str | None:
    """Extract speaker name from Portuguese discursos item fields.

    descricao format: "Speaker Name<br>City, State"
    Returns None for joint speeches (multiple names) or unknown speakers.
    Falls back to parsing titulo if descricao is empty/unusable.
    """
    if descricao:
        raw = descricao.split("<br>")[0].strip()
        raw = re.sub(r"<[^>]+>", "", raw).strip()
        if raw:
            # Skip joint speeches (e.g. "Galípolo, Ailton e Picchetti")
            parts = _JOINT_RE.split(raw)
            if len(parts) > 1:
                return None
            return _normalize_name(raw)

    # Fallback: scan titulo for exactly one known member name
    found = [n for n in ALL_COPOM if n.lower() in titulo.lower()]
    if len(found) == 1:
        return found[0]

    return None


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
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(_CREATE_TABLE)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    for col in ("body", "central_bank", "country", "language", "body_en"):
        if col not in cols:
            conn.execute(f"ALTER TABLE speeches ADD COLUMN {col} TEXT")
    conn.commit()
    return conn


def save_rating(url: str, score: int, justification: str, rated_at: str,
                body_en: str | None = None) -> None:
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
    urls = {r[0] for r in conn.execute("SELECT url FROM speeches WHERE central_bank='BCB'")}
    conn.close()
    return urls


def _store_speech(rec: dict, conn: sqlite3.Connection) -> None:
    from translator import detect_language
    body = rec.get("body", "")
    lang = detect_language(body, rec.get("title", "")) if body else "pt"
    conn.execute(
        "INSERT OR IGNORE INTO speeches "
        "(url, date, speaker, title, body, central_bank, country, language) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (rec["url"], rec["date"], rec["speaker"], rec["title"],
         body, "BCB", "BRL", lang),
    )


# ---------------------------------------------------------------------------
# PDF download (plain requests — PDFs are direct, no session needed)
# ---------------------------------------------------------------------------

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _extract_pdf_text(pdf_path: str, session: requests.Session) -> str:
    url = BCB_BASE + pdf_path if pdf_path.startswith("/") else pdf_path
    try:
        r = session.get(url, timeout=45)
        if r.status_code != 200:
            return ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
        return "\n".join(pages)
    except Exception as e:
        print(f"    BCB PDF extraction failed ({url}): {e}")
        return ""


# ---------------------------------------------------------------------------
# API fetching via Playwright (requires browser session for authentication)
# ---------------------------------------------------------------------------

def _fetch_year_playwright(year: int) -> list[dict]:
    """Fetch one year of discursos using a one-off Playwright session."""
    return _fetch_years_playwright([year]).get(year, [])


def _fetch_years_playwright(years: list[int]) -> dict[int, list[dict]]:
    """Fetch multiple years of discursos in a single Playwright session."""
    from playwright.sync_api import sync_playwright

    results: dict[int, list[dict]] = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        # Establish session once
        page.goto(DISCURSOS_PAGE, timeout=30000, wait_until="networkidle")

        for year in years:
            try:
                data = page.evaluate(f"""async () => {{
                    const r = await fetch('{DISCURSOS_API}?ano={year}',
                        {{headers: {{'Accept': 'application/json'}}}});
                    if (!r.ok) return [];
                    const d = await r.json();
                    return d.conteudo || [];
                }}""")
                results[year] = data or []
            except Exception as e:
                print(f"    Error fetching {year}: {e}")
                results[year] = []

        browser.close()

    return results


def _parse_date(iso: str) -> str:
    return iso[:10] if iso else ""


def _item_to_record(item: dict, session: requests.Session, fetch_text: bool = True) -> dict | None:
    titulo = (item.get("titulo") or "").strip()
    descricao = (item.get("descricao") or "").strip()
    date_raw = item.get("dataReferencia") or ""
    arquivo = item.get("arquivo") or {}
    pdf_path = (
        arquivo.get("ServerRelativeUrl")
        or item.get("Url")
        or ""
    )

    date = _parse_date(date_raw)
    if not date:
        return None

    speaker = _extract_speaker(descricao, titulo)
    if not speaker:
        return None

    url_key = f"bcb::{date}::{pdf_path or titulo[:100]}"

    body = ""
    if fetch_text and pdf_path:
        body = _extract_pdf_text(pdf_path, session)

    return {
        "url": url_key,
        "date": date,
        "speaker": speaker,
        "title": titulo,
        "body": body,
        "pdf_path": pdf_path,
    }


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def get_all_bcb_speeches(start_year: int = 2021, end_year: int = None) -> list[dict]:
    """
    Scrape all Copom member speeches from start_year to end_year, store to DB.
    Returns list of stored-but-unrated speeches by current members.
    """
    if end_year is None:
        end_year = datetime.now().year

    session = _session()
    conn = _conn()
    existing = get_existing_urls()

    stored = 0
    to_rate = []

    years = list(range(start_year, end_year + 1))
    print(f"  Fetching BCB discursos {years[0]}-{years[-1]} in one browser session ...")
    all_year_data = _fetch_years_playwright(years)

    for year in years:
        items = all_year_data.get(year, [])
        year_new = 0

        for item in items:
            # Extract speaker from API metadata first (no PDF download yet)
            rec = _item_to_record(item, session, fetch_text=False)
            if rec is None:
                continue
            if rec["speaker"] not in ALL_COPOM:
                continue  # skip PDF download for non-members
            if rec["url"] in existing:
                continue

            # Only now download the PDF for confirmed Copom members
            pdf_path = rec.pop("pdf_path", "")
            if pdf_path:
                rec["body"] = _extract_pdf_text(pdf_path, session)
            else:
                rec["body"] = ""

            _store_speech(rec, conn)
            existing.add(rec["url"])
            year_new += 1
            stored += 1

            if rec["speaker"] in ALL_COPOM and rec["body"]:
                to_rate.append(rec)

            time.sleep(0.2)

        conn.commit()  # commit per-year so interruptions don't lose work
        print(f"    {year}: {len(items)} on site, {year_new} new stored")

    conn.close()
    print(f"  BCB total new speeches stored: {stored}")
    return to_rate


def get_new_bcb_speeches() -> list[dict]:
    """
    Check current (and previous, if Jan-Mar) year for new Copom speeches.
    Returns unrated speeches by current Copom members.
    """
    session = _session()
    year = datetime.now().year

    years_to_check = [year]
    if datetime.now().month <= 3:
        years_to_check.append(year - 1)

    existing = get_existing_urls()
    conn = _conn()
    to_rate = []

    all_year_data = _fetch_years_playwright(years_to_check)

    for y in years_to_check:
        items = all_year_data.get(y, [])
        print(f"  BCB discursos {y}: {len(items)} speeches on site")

        for item in items:
            rec = _item_to_record(item, session, fetch_text=False)
            if rec is None:
                continue
            if rec["speaker"] not in ALL_COPOM:
                continue
            if rec["url"] in existing:
                continue

            print(f"  Fetching PDF: {rec['speaker']} | {rec['title'][:55]}")
            pdf_path = rec.pop("pdf_path", "")
            if pdf_path:
                rec["body"] = _extract_pdf_text(pdf_path, session)
            else:
                rec["body"] = ""

            _store_speech(rec, conn)
            existing.add(rec["url"])

            if rec["speaker"] in _COPOM_CURRENT and rec["body"] and rec["date"] >= f"{year}-01-01":
                to_rate.append(rec)

            time.sleep(0.4)

    conn.commit()
    conn.close()

    # Also pick up stored-but-unrated current-year speeches
    conn2 = _conn()
    unrated = conn2.execute(
        "SELECT url, date, speaker, title, body FROM speeches "
        "WHERE central_bank='BCB' AND score IS NULL AND date >= ?",
        (f"{year}-01-01",),
    ).fetchall()
    conn2.close()

    already_queued = {s["url"] for s in to_rate}
    for row in unrated:
        url, date, speaker, title, body = row
        if url not in already_queued and speaker in _COPOM_CURRENT and body:
            to_rate.append({
                "url": url, "date": date, "speaker": speaker,
                "title": title, "body": body,
            })

    print(f"  {len(to_rate)} new BCB Copom speeches to rate")
    return to_rate


# Keep old name as alias for backwards compatibility
get_new_bcb_2026 = get_new_bcb_speeches
