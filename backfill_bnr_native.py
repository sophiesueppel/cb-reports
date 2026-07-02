"""
BNR native site backfill — Playwright-based.

Scrapes ALL speeches from https://www.bnr.ro/2650-discursuri-publice (up to 136 pages).
The site is a SPA; pagination requires JS clicks. Every speech page also requires Playwright.

Run: python backfill_bnr_native.py
"""

import asyncio
import io
import os
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(Path(__file__).parent / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.environ.get("OPENAI_API_KEY"):
    sys.exit("Error: OPENAI_API_KEY not set.")

DB_PATH = Path("data/speeches.db")
BNR_BASE = "https://www.bnr.ro"
BNR_LISTING = f"{BNR_BASE}/2650-discursuri-publice"
MAX_LISTING_PAGES = 140  # safety ceiling; site has ~136

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": _UA})

# ── Member lists ──────────────────────────────────────────────────────────────

_BNR_CURRENT = {
    "Mugur Isarescu", "Florin Georgescu", "Leonardo Badea",
    "Eugen Nicolaescu", "Csaba Balint",
}

_BNR_HISTORICAL = _BNR_CURRENT | {
    "Bogdan Olteanu", "Cristian Popa", "Nicolae Cinteza",
    "Virgil Stoenescu", "Liviu Voinea",
}

ALL_BNR = _BNR_HISTORICAL

# URL slug (ASCII-folded lowercase) → canonical name
_SLUG_ALIASES = {
    "isarescu":   "Mugur Isarescu",
    "georgescu":  "Florin Georgescu",
    "badea":      "Leonardo Badea",
    "nicolaescu": "Eugen Nicolaescu",
    "balint":     "Csaba Balint",
    "olteanu":    "Bogdan Olteanu",
    "popa":       "Cristian Popa",
    "cinteza":    "Nicolae Cinteza",
    "stoenescu":  "Virgil Stoenescu",
    "voinea":     "Liviu Voinea",
}

# Also match diacritic variants in text
_TEXT_ALIASES = {
    "isarescu": "Mugur Isarescu",
    "isărescu": "Mugur Isarescu",
    "georgescu": "Florin Georgescu",
    "badea": "Leonardo Badea",
    "nicolaescu": "Eugen Nicolaescu",
    "balint": "Csaba Balint",
    "bălint": "Csaba Balint",
    "olteanu": "Bogdan Olteanu",
    "popa": "Cristian Popa",
    "cinteza": "Nicolae Cinteza",
    "cintează": "Nicolae Cinteza",
    "stoenescu": "Virgil Stoenescu",
    "voinea": "Liviu Voinea",
}


def _fold(s: str) -> str:
    """Strip diacritics, lowercase."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _speaker_from_slug(url: str) -> str:
    """Try to find speaker name from URL slug after date."""
    m = re.search(r"/\d+-\d{4}-\d{2}-\d{2}-(.+)$", url)
    if not m:
        return ""
    slug = m.group(1)
    for part in slug.split("-"):
        if part in _SLUG_ALIASES:
            return _SLUG_ALIASES[part]
    return ""


def _speaker_from_text(text: str) -> str:
    """Try to find speaker name in free text (handles diacritics)."""
    folded = _fold(text)
    for key, name in _TEXT_ALIASES.items():
        folded_key = _fold(key)
        if folded_key in folded:
            return name
    return ""


def _parse_url_date(url: str) -> str:
    """Extract YYYY-MM-DD from /NNNN-YYYY-MM-DD-slug."""
    m = re.search(r"/\d+-(\d{4})-(\d{2})-(\d{2})-", url)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


# ── DB ────────────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _get_existing() -> tuple[set, set]:
    conn = _conn()
    urls = {r[0] for r in conn.execute(
        "SELECT url FROM speeches WHERE central_bank='BNR'"
    )}
    date_speakers = {(r[0], r[1]) for r in conn.execute(
        "SELECT date, speaker FROM speeches WHERE central_bank='BNR'"
    )}
    conn.close()
    return urls, date_speakers


def _store(url, date, speaker, title, body, lang):
    conn = _conn()
    conn.execute(
        "INSERT OR IGNORE INTO speeches "
        "(url, date, speaker, title, body, central_bank, country, language) "
        "VALUES (?, ?, ?, ?, ?, 'BNR', 'RON', ?)",
        (url, date, speaker, title, body, lang),
    )
    conn.commit()
    conn.close()


def _save_rating(url, score, justification, rated_at, body_en=None):
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


# ── Phase 1: collect all listing entries ─────────────────────────────────────

async def _go_to_page(page, target_num: int) -> bool:
    """
    Click the target page number div in the BNR pagination.
    The pagination uses <div class="pagination-link"> elements (NOT <a> tags).
    Returns True if navigation succeeded.
    """
    # Snapshot current entry text to detect change
    try:
        old_data = await page.inner_text(".pagination-data")
    except Exception:
        old_data = ""

    # Try clicking the exact page number div
    # The visible divs are the current page ± a few numbers and the last page (136)
    try:
        btn = await page.query_selector(
            f'.pagination-controls .pagination-link:not(.filler):not(.selected)'
            f':text-is("{target_num}")'
        )
        if not btn:
            # Broader: any pagination-link div with that exact number
            all_links = await page.query_selector_all(".pagination-link")
            for el in all_links:
                txt = (await el.inner_text()).strip()
                if txt == str(target_num):
                    btn = el
                    break

        if btn:
            await btn.click()
            try:
                await page.wait_for_function(
                    "(old) => { const d = document.querySelector('.pagination-data'); "
                    "return d && d.innerText.slice(0, 100) !== old; }",
                    arg=old_data[:100],
                    timeout=7000,
                )
            except Exception:
                await page.wait_for_timeout(2500)
            # Confirm page changed
            new_data = await page.inner_text(".pagination-data")
            return new_data != old_data
    except Exception as e:
        print(f"  _go_to_page({target_num}) error: {e}")

    return False


async def _extract_page_entries(page) -> list[dict]:
    """Extract all speech entry links from the current listing page."""
    raw = await page.evaluate(r"""
        () => {
            const results = [];
            // Search inside pagination-data for better precision
            const root = document.querySelector('.pagination-data') || document.body;
            for (const a of root.querySelectorAll('a[href]')) {
                const href = a.getAttribute('href') || '';
                // Speech pages: /NNNN-YYYY-MM-DD-slug  (id has 3+ digits)
                if (!/^\/\d{3,}-\d{4}-\d{2}-\d{2}-/.test(href)) continue;

                // Walk up to find a container with the date
                let container = a.parentElement;
                for (let i = 0; i < 8 && container && container.tagName !== 'BODY'; i++) {
                    if (/\d{2}\.\d{2}\.\d{4}/.test(container.innerText || '')) break;
                    container = container.parentElement;
                }
                const ctx = container ? container.innerText.trim() : '';
                results.push({
                    href,
                    linkText: a.innerText.trim(),
                    ctx: ctx.slice(0, 400),
                });
            }
            return results;
        }
    """)

    entries = []
    seen = set()
    for e in raw:
        href = e["href"]
        if href in seen:
            continue
        seen.add(href)

        date = _parse_url_date(href)
        if not date:
            dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", e["ctx"])
            if dm:
                d, mo, y = dm.groups()
                date = f"{y}-{mo}-{d}"
        if not date:
            continue

        speaker = _speaker_from_slug(href) or _speaker_from_text(e["ctx"])
        if not speaker:
            continue  # skip unknown speakers immediately

        link_type = "pdf" if (
            "pdf" in href.lower()
            or "descarca" in e["linkText"].lower()
            or "descărcă" in e["linkText"].lower()
        ) else "html"

        # Try to extract title from context text
        title = _title_from_ctx(e["ctx"], speaker, date)

        entries.append({
            "url": BNR_BASE + href,
            "date": date,
            "speaker": speaker,
            "title": title,
            "link_type": link_type,
        })

    return entries


def _title_from_ctx(text: str, speaker: str, date: str) -> str:
    """Extract speech title from listing-entry context text."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    filtered = []
    skip_lower = {"deschide", "descarcă", "descarca", "open", "download"}
    for line in lines:
        if re.match(r"^\d{2}\.\d{2}\.\d{4}$", line):
            continue
        if line.lower() in skip_lower:
            continue
        if _fold(line) == _fold(speaker):
            continue
        # Skip if line is just the date in another format
        if re.match(r"^\d{4}-\d{2}-\d{2}$", line):
            continue
        if len(line) >= 8:
            filtered.append(line)
    return filtered[0] if filtered else ""


async def collect_all_listing_entries() -> list[dict]:
    """
    Navigate all listing pages and return unique speech entries.
    Filters to known BNR board members only.
    """
    all_entries: list[dict] = []
    seen_urls: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(user_agent=_UA, locale="ro-RO")
        page = await ctx.new_page()

        print(f"Loading listing: {BNR_LISTING}")
        await page.goto(BNR_LISTING, wait_until="networkidle", timeout=40000)
        await page.wait_for_timeout(2500)

        for page_num in range(1, MAX_LISTING_PAGES + 1):
            entries = await _extract_page_entries(page)
            new_count = 0
            for e in entries:
                if e["url"] not in seen_urls:
                    seen_urls.add(e["url"])
                    all_entries.append(e)
                    new_count += 1

            print(f"  Listing page {page_num:3d}: {len(entries):2d} entries, "
                  f"{new_count:2d} new  (total={len(all_entries)})")

            if page_num >= MAX_LISTING_PAGES:
                break

            navigated = await _go_to_page(page, page_num + 1)
            if not navigated:
                print(f"  Pagination stopped after page {page_num}.")
                break
            await page.wait_for_timeout(1500)

        await browser.close()

    print(f"\nListing complete: {len(all_entries)} unique entries from BNR members.\n")
    return all_entries


# ── Phase 2: fetch speech bodies ──────────────────────────────────────────────

async def _fetch_html_body(page, url: str) -> tuple[str, str]:
    """Use Playwright to render an HTML speech page. Returns (title, body_text)."""
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)

        result = await page.evaluate("""
            () => {
                // Try to find the main speech content area
                const selectors = [
                    '.article-content', '.speech-content', '#pagecontent',
                    'article', '[class*="content-body"]', 'main .content',
                    '.news-body', '.entry-content', 'main',
                ];
                let el = null;
                for (const sel of selectors) {
                    el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 200) break;
                }
                if (!el) el = document.body;

                // Get all paragraphs with meaningful text
                const paras = Array.from(el.querySelectorAll('p, h1, h2, h3'))
                    .map(p => p.innerText.trim())
                    .filter(t => t.length > 20);

                // Get title from <h1> or <title>
                const h1 = document.querySelector('h1');
                const title = h1 ? h1.innerText.trim()
                             : document.title.split('|')[0].trim();

                return {
                    title: title.slice(0, 300),
                    body: paras.join('\\n\\n').slice(0, 60000),
                };
            }
        """)
        return result.get("title", ""), result.get("body", "")
    except Exception as e:
        print(f"    Playwright fetch failed for {url}: {e}")
        return "", ""


def _fetch_pdf_body(url: str) -> str:
    """Download PDF and extract text. Returns body string."""
    try:
        r = _SESSION.get(url, timeout=60)
        if r.status_code == 200 and "pdf" in r.headers.get("content-type", "").lower():
            with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
            return "\n".join(pages)[:60000]
    except Exception as e:
        print(f"    PDF fetch failed for {url}: {e}")
    return ""


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def _run_fetch_phase(entries: list[dict], existing_urls: set, existing_ds: set) -> list[dict]:
    """
    For each listing entry not already in DB, fetch body text.
    Returns list of stored speech dicts for rating.
    """
    to_process = [
        e for e in entries
        if e["url"] not in existing_urls
        and (e["date"], e["speaker"]) not in existing_ds
    ]

    print(f"Entries to fetch: {len(to_process)} (skipping {len(entries) - len(to_process)} already in DB)\n")
    if not to_process:
        return []

    from translator import detect_language

    stored = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = await browser.new_context(user_agent=_UA, locale="ro-RO")
        page = await ctx.new_page()

        for i, e in enumerate(to_process, 1):
            url = e["url"]
            date = e["date"]
            speaker = e["speaker"]
            link_type = e["link_type"]
            title = e["title"]

            print(f"[{i}/{len(to_process)}] {date} | {speaker} | {title[:55]}")

            if link_type == "pdf":
                body = _fetch_pdf_body(url)
            else:
                html_title, body = await _fetch_html_body(page, url)
                if html_title and len(html_title) > len(title):
                    title = html_title

            if len(body) < 80:
                print(f"  SKIP — body too short ({len(body)} chars)")
                await asyncio.sleep(0.5)
                continue

            lang = detect_language(body, title)
            _store(url, date, speaker, title, body, lang)
            existing_urls.add(url)
            existing_ds.add((date, speaker))

            stored.append({
                "url": url, "date": date, "speaker": speaker,
                "title": title, "body": body, "language": lang,
            })
            print(f"  Stored  lang={lang}  len={len(body)}")

            # Polite delay
            await asyncio.sleep(0.8 if link_type == "html" else 0.3)

        await browser.close()

    return stored


def _rate_all(speeches: list[dict]) -> None:
    """Rate all speeches (translate Romanian first if needed)."""
    from rater import rate_speech
    from translator import translate_speech

    errors = 0
    for i, sp in enumerate(speeches, 1):
        print(f"Rating [{i}/{len(speeches)}] {sp['speaker']} | {sp['date']} | {sp['title'][:50]}")
        try:
            lang = sp.get("language", "en")
            body_en = sp.get("body_en") or ""

            if lang not in ("en", "en-gb") and not body_en:
                body_en = translate_speech(
                    sp["body"], lang, title=sp["title"], speaker=sp["speaker"]
                )
                time.sleep(0.3)

            rating = rate_speech(
                sp["title"], sp["speaker"], sp["date"], sp["body"],
                bank="BNR", db_path=str(DB_PATH),
                language=lang, body_en=body_en,
            )
            now = datetime.now(timezone.utc).isoformat()
            _save_rating(sp["url"], rating["score"], rating["justification"], now,
                         body_en=body_en or None)
            print(f"  Score {rating['score']}/10 — {rating['justification'][:70]}")
        except Exception as e:
            print(f"  Error rating: {e}")
            errors += 1
        time.sleep(0.3)

    print(f"\nRating done. {len(speeches) - errors} rated, {errors} errors.")


async def main():
    print("=" * 60)
    print("BNR Native Site Backfill (Playwright)")
    print("=" * 60)

    existing_urls, existing_ds = _get_existing()
    print(f"Already in DB: {len(existing_urls)} BNR speeches\n")

    # Phase 1: collect all listing entries
    print("── Phase 1: Scrape listing pages ──")
    entries = await collect_all_listing_entries()

    # Phase 2: fetch bodies for new entries
    print("── Phase 2: Fetch speech bodies ──")
    stored = await _run_fetch_phase(entries, existing_urls, existing_ds)

    if not stored:
        print("No new speeches fetched.")
    else:
        # Phase 3: rate
        print(f"\n── Phase 3: Rate {len(stored)} speeches ──")
        _rate_all(stored)

    # Phase 4: also rate any stored-but-unrated BNR speeches
    conn = _conn()
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body, language, body_en FROM speeches "
        "WHERE central_bank='BNR' AND score IS NULL AND body IS NOT NULL"
    ).fetchall()
    conn.close()

    if unrated:
        print(f"\n── Phase 4: Rate {len(unrated)} stored-but-unrated BNR speeches ──")
        extra = [
            {"url": r[0], "date": r[1], "speaker": r[2], "title": r[3],
             "body": r[4], "language": r[5] or "ro", "body_en": r[6] or ""}
            for r in unrated
        ]
        _rate_all(extra)

    # Phase 5: classify and generate report
    total = _conn().execute(
        "SELECT COUNT(*) FROM speeches WHERE central_bank='BNR'"
    ).fetchone()[0]
    print(f"\n── Phase 5: Classify + generate report ({total} BNR speeches total) ──")

    from classify_relevance_llm import run_classification
    run_classification(bank="BNR")

    from report_bnr_filtered import generate_bnr_filtered_report
    generate_bnr_filtered_report()

    # Phase 6: commit and push
    import subprocess
    subprocess.run(
        ["git", "add", "report_bnr_filtered.html",
         "scraper_bnr.py", "backfill_bnr_native.py"],
        check=False,
    )
    msg = f"BNR native: +{len(stored)} speeches from bnr.ro ({total} total)"
    subprocess.run(["git", "commit", "-m", msg], check=False)
    subprocess.run(["git", "push"], check=False)
    print(f"\nDone. Pushed: {msg}")


if __name__ == "__main__":
    asyncio.run(main())
