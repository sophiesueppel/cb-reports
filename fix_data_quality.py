"""
Data quality fix:
1. Delete junk bodies (too short, boilerplate, slide-only entries)
2. Retry BoJ PDF downloads for no-body speeches
3. Try to fetch ECB no-body speeches from ECB website
4. Delete anything still lacking a usable body
"""
import io
import re
import sqlite3
import sys
import time
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = Path("data/speeches.db")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}

MIN_BODY_LEN = 800  # chars — anything shorter is not a usable speech

# ---------------------------------------------------------------------------
# Junk detection — length only.
# Pattern checks on long bodies incorrectly flag normal speeches that happen
# to contain those words (e.g. every Fed speech starts with ".gov" boilerplate
# but then has the full speech text). Only short bodies are junk.
# ---------------------------------------------------------------------------

def is_junk(body: str) -> bool:
    return not body or len(body.strip()) < MIN_BODY_LEN


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    return c


# ---------------------------------------------------------------------------
# 1. Identify all bad rows
# ---------------------------------------------------------------------------

def find_bad_rows() -> list[dict]:
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT url, central_bank, date, speaker, title, body, score "
        "FROM speeches"
    ).fetchall()
    bad = [dict(r) for r in rows if is_junk(r["body"] or "")]
    c.close()
    return bad


# ---------------------------------------------------------------------------
# 2. BoJ: retry PDF download
# ---------------------------------------------------------------------------

BOJ_BASE = "https://www.boj.or.jp"

def _boj_extract_pdf(speech_url: str, session: requests.Session) -> str:
    """Try to get PDF text from a BoJ speech page."""
    try:
        r = session.get(speech_url, timeout=20)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")

        # Use the PDF link found on the page (don't derive — derived URLs add '1' suffix which 404s)
        pdf_url = None
        for a in soup.find_all("a", href=re.compile(r"\.pdf$", re.I)):
            href = a["href"]
            if href.startswith("/"):
                pdf_url = BOJ_BASE + href          # absolute path
            elif href.startswith("http"):
                pdf_url = href
            else:
                base_dir = speech_url.rsplit("/", 1)[0]
                pdf_url = base_dir + "/" + href
            break

        if not pdf_url:
            return ""

        pr = session.get(pdf_url, timeout=45)
        if pr.status_code != 200:
            return ""
        with pdfplumber.open(io.BytesIO(pr.content)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
        return "\n".join(pages)
    except Exception as e:
        print(f"    BoJ PDF fail {speech_url}: {e}")
        return ""


def retry_boj_no_body() -> dict[str, str]:
    """Return {url: body_text} for BoJ speeches where we got text."""
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    raw = c.execute(
        "SELECT url, date, speaker FROM speeches "
        "WHERE central_bank='Bank of Japan' AND (body IS NULL OR body='')"
    ).fetchall()
    rows = [dict(r) for r in raw]
    c.close()

    session = requests.Session()
    session.headers.update(HEADERS)

    results = {}
    for r in rows:
        url = r["url"]
        print(f"  BoJ fetch: {r['date']} {r['speaker']} — {url}")
        text = _boj_extract_pdf(url, session)
        if text and len(text) >= MIN_BODY_LEN:
            results[url] = text
            print(f"    OK ({len(text)} chars)")
        else:
            print(f"    FAIL (got {len(text)} chars)")
        time.sleep(0.5)
    return results


# ---------------------------------------------------------------------------
# 3. BoE: re-fetch short/junk body speeches
# ---------------------------------------------------------------------------

def _boe_extract_text(url: str, session: requests.Session) -> str:
    """Re-fetch a BoE speech page and extract body text."""
    try:
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")

        # Try main article body
        for sel in ["article", ".page-content", ".hero-copy", "main", "#content"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) > MIN_BODY_LEN:
                    return text

        # Try PDF link on page
        for a in soup.find_all("a", href=re.compile(r"\.pdf$", re.I)):
            href = a["href"]
            if not href.startswith("http"):
                href = "https://www.bankofengland.co.uk" + href
            try:
                pr = session.get(href, timeout=30)
                if pr.status_code == 200:
                    with pdfplumber.open(io.BytesIO(pr.content)) as pdf:
                        pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
                    text = "\n".join(pages)
                    if len(text) > MIN_BODY_LEN:
                        return text
            except Exception:
                pass

        return ""
    except Exception as e:
        print(f"    BoE re-fetch fail {url}: {e}")
        return ""


def retry_boe_bad_body(bad_boe: list[dict]) -> dict[str, str]:
    """Try to re-fetch BoE speeches with bad bodies. Return {url: new_body}."""
    session = requests.Session()
    session.headers.update(HEADERS)
    results = {}
    for row in bad_boe:
        url = row["url"]
        if not url.startswith("http"):
            continue
        print(f"  BoE re-fetch: {row['date']} {row['speaker']} — {url}")
        text = _boe_extract_text(url, session)
        if text and len(text) >= MIN_BODY_LEN:
            results[url] = text
            print(f"    OK ({len(text)} chars)")
        else:
            print(f"    FAIL (got {len(text)} chars)")
        time.sleep(0.3)
    return results


# ---------------------------------------------------------------------------
# 4. ECB: re-download CSV to pick up any speeches now having content
# ---------------------------------------------------------------------------

ECB_CSV_URL = (
    "https://www.ecb.europa.eu/press/key/shared/data/all_ECB_speeches.csv"
    "?b817ea0464300d26845bc915c07dfb17"
)

def retry_ecb_no_body() -> dict[str, str]:
    """Re-download ECB CSV and return {url_key: body_text} for speeches
    that now have content in the CSV but were empty when first loaded."""
    import pandas as pd
    from scraper_ecb import ecb_url_key

    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    raw = c.execute(
        "SELECT url, date, title FROM speeches "
        "WHERE central_bank='ECB' AND (body IS NULL OR body='')"
    ).fetchall()
    no_body = {dict(r)["url"]: {"date": dict(r)["date"], "title": dict(r)["title"]} for r in raw}
    c.close()

    if not no_body:
        print("  No ECB no-body speeches to fix.")
        return {}

    print(f"  Downloading ECB CSV ({len(no_body)} speeches to look up)...")
    session = requests.Session()
    session.headers.update(HEADERS)
    r = session.get(ECB_CSV_URL, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(__import__("io").StringIO(r.content.decode("utf-8", errors="replace")), sep="|")
    df["contents"] = df["contents"].fillna("").astype(str)
    df["title"] = df["title"].fillna("").astype(str)
    df["date"] = df["date"].fillna("").astype(str)

    # Build lookup: url_key → contents
    csv_contents = {
        ecb_url_key(row["date"], row["title"]): row["contents"]
        for _, row in df.iterrows()
    }

    results = {}
    for url_key in no_body:
        text = csv_contents.get(url_key, "").strip()
        if text and len(text) >= MIN_BODY_LEN:
            results[url_key] = text
            print(f"  ECB recovered from CSV: {url_key[:70]} ({len(text)} chars)")
        else:
            print(f"  ECB still empty in CSV: {url_key[:70]}")

    return results


# ---------------------------------------------------------------------------
# 5. Apply updates and delete unrecoverable rows
# ---------------------------------------------------------------------------

def apply_fixes(new_bodies: dict[str, str], bad_rows: list[dict]) -> None:
    fixed_urls = set(new_bodies.keys())
    delete_urls = [r["url"] for r in bad_rows if r["url"] not in fixed_urls]

    c = sqlite3.connect(str(DB_PATH))
    try:
        for url_key, text in new_bodies.items():
            c.execute("UPDATE speeches SET body=? WHERE url=?", (text, url_key))
            print(f"  UPDATED body: {url_key[:80]}")

        for url in delete_urls:
            c.execute("DELETE FROM speeches WHERE url=?", (url,))
            print(f"  DELETED: {url[:80]}")

        c.commit()
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== STEP 1: Find all bad/junk rows ===")
    bad_rows = find_bad_rows()
    print(f"Found {len(bad_rows)} bad rows total")
    by_bank = {}
    for r in bad_rows:
        by_bank.setdefault(r["central_bank"], []).append(r)
    for bank, rows in sorted(by_bank.items()):
        rated = sum(1 for r in rows if r["score"] is not None)
        print(f"  {bank}: {len(rows)} bad ({rated} have a score that will be lost)")

    print("\n=== STEP 2: BoJ — retry PDF downloads ===")
    boj_recovered = retry_boj_no_body()
    print(f"BoJ: recovered {len(boj_recovered)} speeches")

    print("\n=== STEP 3: BoE — re-fetch short/junk bodies ===")
    bad_boe = by_bank.get("Bank of England", [])
    boe_recovered = retry_boe_bad_body(bad_boe)
    print(f"BoE: recovered {len(boe_recovered)} speeches")

    print("\n=== STEP 4: ECB — fetch no-body speeches from website ===")
    ecb_recovered = retry_ecb_no_body()
    print(f"ECB: recovered {len(ecb_recovered)} speeches")

    all_recovered = {**boj_recovered, **boe_recovered, **ecb_recovered}
    print(f"\nTotal recovered: {len(all_recovered)}")
    print(f"Will delete: {len(bad_rows) - len(all_recovered)} rows")

    print("\n=== STEP 5: Apply fixes ===")
    apply_fixes(all_recovered, bad_rows)

    print("\n=== FINAL SUMMARY ===")
    with sqlite3.connect(str(DB_PATH)) as c:
        c.row_factory = sqlite3.Row
        for row in c.execute("""
            SELECT central_bank,
                   COUNT(*) as total,
                   SUM(CASE WHEN body IS NOT NULL AND LENGTH(body) >= 800 THEN 1 ELSE 0 END) as good_body,
                   SUM(CASE WHEN score IS NOT NULL THEN 1 ELSE 0 END) as rated
            FROM speeches GROUP BY central_bank ORDER BY central_bank
        """):
            print(f"  {row[0]}: {row[1]} total, {row[2]} good body, {row[3]} rated")
