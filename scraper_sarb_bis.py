"""
Scraper for SARB speeches from the BIS archive.

BIS has a comprehensive catalogue of SARB speeches going back to ~2009.
Individual pages are static HTML; full text is in the PDF (replace .htm → .pdf).

Run:
    python scraper_sarb_bis.py
"""

import io
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path("data/speeches.db")
BIS_BASE = "https://www.bis.org"
BIS_LISTING = f"{BIS_BASE}/list/cbspeeches/index.htm"
SARB_INSTITUTION_ID = "44"  # South African Reserve Bank in BIS dropdown

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = UA

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
}

_TITLE_RE = re.compile(
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
    name = _TITLE_RE.sub("", raw).strip()
    # Try full name match first
    if name in _SARB_HISTORICAL:
        return name
    # Try last name alias
    last = name.split()[-1] if name else ""
    return _ALIASES.get(last, name)


def _parse_date(s: str) -> str:
    m = _DATE_RE.search(s)
    if not m:
        return ""
    d, mon, y = m.group(1), m.group(2).capitalize(), m.group(3)
    return f"{y}-{_MONTHS[mon]}-{int(d):02d}"


# ---------------------------------------------------------------------------
# BIS listing: discover all SARB speech URLs via Playwright
# ---------------------------------------------------------------------------

def discover_bis_sarb_urls() -> list[str]:
    """Use Playwright to filter BIS listing by SARB and collect all speech URLs."""
    found: list[str] = []
    seen: set[str] = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        page.goto(BIS_LISTING, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Set institution filter to SARB (value=44)
        page.select_option("select[name='institutions']", SARB_INSTITUTION_ID)
        page.wait_for_timeout(1000)

        # Set page size to 25 (max available)
        page.select_option("select[name='paging_length']", "25")
        page.wait_for_timeout(500)

        # Click search/apply button if one exists
        for selector in ["button[type=submit]", "input[type=submit]", "button.btn-primary", "#frm_cbspeeches button"]:
            btn = page.query_selector(selector)
            if btn:
                btn.click()
                page.wait_for_timeout(3000)
                break

        def _collect_links() -> None:
            for lnk in page.query_selector_all("a[href*='/review/r']"):
                href = lnk.get_attribute("href") or ""
                if href.endswith(".htm"):
                    full = BIS_BASE + href if href.startswith("/") else href
                    if full not in seen:
                        seen.add(full)
                        found.append(full)

        _collect_links()
        print(f"  After filter: {len(found)} URLs on page 1")

        # Paginate
        page_num = 2
        while True:
            # Try to find next page button/link
            next_btn = None
            for selector in [
                "a.paginate_button.next:not(.disabled)",
                "li.next:not(.disabled) a",
                "a[data-dt-idx]:last-of-type",
                ".next a",
            ]:
                next_btn = page.query_selector(selector)
                if next_btn:
                    break

            if not next_btn:
                break

            try:
                next_btn.click()
                page.wait_for_timeout(2000)
                before = len(found)
                _collect_links()
                after = len(found)
                print(f"  Page {page_num}: +{after - before} URLs (total {after})")
                if after == before:  # No new links found
                    break
                page_num += 1
            except Exception as e:
                print(f"  Pagination stopped at page {page_num}: {e}")
                break

        browser.close()

    return found


# ---------------------------------------------------------------------------
# Parse individual BIS speech page
# ---------------------------------------------------------------------------

def _download_pdf_text(pdf_url: str) -> str:
    try:
        r = _SESSION.get(pdf_url, timeout=60)
        if r.status_code != 200:
            return ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
        return "\n".join(pages)
    except Exception:
        return ""


def parse_bis_speech(url: str) -> dict:
    """Fetch BIS speech page, extract metadata; get full body from PDF."""
    try:
        r = _SESSION.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    pc = soup.find(id="pagecontent")
    pc_text = pc.get_text(" ", strip=False) if pc else soup.get_text(" ", strip=False)

    # Title from <title> tag: "Speaker Name: Speech Title"
    title_tag = soup.find("title")
    title = ""
    speaker = ""
    if title_tag:
        raw_title = title_tag.get_text().strip()
        if ":" in raw_title:
            speaker_part, _, title_part = raw_title.partition(":")
            speaker = _normalize_speaker(speaker_part.strip())
            title = title_part.strip()
        else:
            title = raw_title

    # Date from pagecontent text
    date_iso = _parse_date(pc_text)

    # If speaker not found from title, try meta or pagecontent
    if not speaker or speaker not in _SARB_HISTORICAL:
        # Try "by [Name]" pattern in page text
        m = re.search(r"\bby\s+((?:Mr|Ms|Dr|Governor|Deputy Governor)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}))", pc_text)
        if m:
            speaker = _normalize_speaker(m.group(1).strip())

    # Full body from PDF (replace .htm → .pdf)
    pdf_url = url.replace(".htm", ".pdf")
    body = _download_pdf_text(pdf_url)

    # If PDF fails, try the HTML excerpt
    if not body and pc:
        paras = [p.get_text(strip=True) for p in pc.find_all("p") if p.get_text(strip=True)]
        body = "\n\n".join(paras)

    # If still no date, try PDF body
    if not date_iso and body:
        date_iso = _parse_date(body)

    return {
        "url": url,
        "date": date_iso,
        "speaker": speaker,
        "title": title,
        "body": body,
    }


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

def run() -> None:
    from dotenv import load_dotenv
    load_dotenv(Path("../.env") if not Path(".env").exists() else Path(".env"))

    print("=== SARB BIS scraper ===")
    print("Discovering SARB speech URLs from BIS listing...")
    urls = discover_bis_sarb_urls()
    print(f"Total BIS SARB URLs discovered: {len(urls)}")

    # Add any known URLs not found via Playwright (fallback)
    KNOWN_URLS = [
        "https://www.bis.org/review/r241021h.htm",
        "https://www.bis.org/review/r240313m.htm",
        "https://www.bis.org/review/r240426b.htm",
        "https://www.bis.org/review/r240806e.htm",
        "https://www.bis.org/review/r240910d.htm",
        "https://www.bis.org/review/r241007a.htm",
        "https://www.bis.org/review/r241113b.htm",
        "https://www.bis.org/review/r250218a.htm",
        "https://www.bis.org/review/r250623b.htm",
        "https://www.bis.org/review/r251031a.htm",
        "https://www.bis.org/review/r251105g.htm",
        "https://www.bis.org/review/r251106i.htm",
        "https://www.bis.org/review/r220729c.htm",
        "https://www.bis.org/review/r230718a.htm",
        "https://www.bis.org/review/r200619g.htm",
    ]
    url_set = set(urls)
    for ku in KNOWN_URLS:
        if ku not in url_set:
            urls.append(ku)
            url_set.add(ku)
    print(f"After adding known URLs: {len(urls)} total")

    existing = get_existing_urls()
    new_urls = [u for u in urls if u not in existing]
    print(f"New speeches to fetch: {len(new_urls)} (skipping {len(urls) - len(new_urls)} already in DB)")

    conn = _conn()
    stored = 0
    skipped = 0

    for i, url in enumerate(new_urls, 1):
        rec = parse_bis_speech(url)
        if not rec.get("date"):
            print(f"  [{i}/{len(new_urls)}] SKIP (no date): {url}")
            skipped += 1
            continue
        if not rec.get("speaker") or rec["speaker"] not in _SARB_HISTORICAL:
            print(f"  [{i}/{len(new_urls)}] SKIP (not MPC: {rec.get('speaker')!r}): {url}")
            skipped += 1
            continue
        body = rec.get("body", "")
        if len(body) < 200:
            print(f"  [{i}/{len(new_urls)}] SKIP (body too short: {len(body)}): {url}")
            skipped += 1
            continue

        conn.execute(
            "INSERT OR IGNORE INTO speeches "
            "(url, date, speaker, title, body, central_bank, country) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (url, rec["date"], rec["speaker"], rec["title"], body, "SARB", "ZAR"),
        )
        stored += 1
        print(f"  [{i}/{len(new_urls)}] Stored: {rec['speaker']} | {rec['date']} | {rec['title'][:60]}")

        if i % 10 == 0:
            conn.commit()
        time.sleep(0.3)

    conn.commit()
    conn.close()
    print(f"\nStored {stored} new speeches ({skipped} skipped)")

    # Rate and classify
    if stored > 0:
        _rate_new()
        _classify_new()
        _regenerate_report()
        _git_push(stored)


def _rate_new() -> None:
    import os
    from rater import rate_speech

    print("\n--- Rating new SARB speeches ---")
    conn = _conn()
    cutoff = f"{datetime.now().year - 5}-01-01"
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body FROM speeches "
        "WHERE central_bank='SARB' AND score IS NULL "
        "AND date >= ? AND body IS NOT NULL AND length(body) > 200 "
        "ORDER BY date DESC",
        (cutoff,),
    ).fetchall()
    print(f"  {len(unrated)} speeches to rate (from {cutoff})")

    import datetime as dt_module
    now = dt_module.datetime.now().isoformat()
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
            print(f"  [{i}/{len(unrated)}] {speaker} | {date} | {title[:50]} → {score}/10")
        except Exception as e:
            print(f"  [{i}/{len(unrated)}] ERROR rating {url}: {e}")

    conn.close()


def _classify_new() -> None:
    print("\n--- Classifying new neutral SARB speeches ---")
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
    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push"], check=True)
    print("Pushed.")


if __name__ == "__main__":
    run()
