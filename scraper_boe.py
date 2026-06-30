import io
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

BASE = "https://www.bankofengland.co.uk"
SITEMAP_URL = f"{BASE}/sitemap/speeches"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
DB_PATH = Path("data/speeches.db")

# Current MPC members — loaded from data/members.json (updated by check_members.py).
# The hardcoded set below is the fallback if the JSON file doesn't exist yet.
def _load_mpc_members() -> set[str]:
    import json
    p = Path("data/members.json")
    if p.exists():
        names = set(json.loads(p.read_text(encoding="utf-8")).get("boe_mpc", []))
        # Add dot-stripped variants for middle initials (e.g. "Catherine L. Mann" → "Catherine L Mann")
        extras = set()
        for name in names:
            stripped = name.replace(".", "")
            if stripped != name:
                extras.add(stripped)
        return names | extras
    return {
        "Andrew Bailey", "Sarah Breeden", "Clare Lombardelli", "Dave Ramsden",
        "Swati Dhingra", "Megan Greene", "Alan Taylor", "Catherine Mann",
        "Catherine L. Mann", "Catherine L Mann", "Huw Pill",
    }

MPC_MEMBERS = _load_mpc_members()

# All MPC members ever — Governors, Deputy Governors, Chief Economists, external members.
# Used for DB filtering: keep only speeches from people who voted on rates.
ALL_BOE_MPC_MEMBERS = MPC_MEMBERS | {
    # Governors
    "Edward George", "Sir Edward George", "Mervyn King", "Mark Carney",
    # Deputy Governors
    "Rachel Lomax", "John Gieve", "Charles Bean", "Charlie Bean",
    "Paul Tucker", "Jon Cunliffe", "Sir Jon Cunliffe", "Minouche Shafik",
    # Chief Economists
    "Spencer Dale", "Andrew Haldane", "Andy Haldane",
    # External MPC members (historical)
    "Sushil Wadhwani", "Marian Bell", "DeAnne Julius", "Stephen Nickell",
    "Professor Stephen Nickell", "Christopher Allsopp", "Kate Barker",
    "Richard Lambert", "David Blanchflower", "David Walton", "David Miles",
    "Adam Posen", "Adam S. Posen", "Andrew Sentance", "Andrew Sentence",
    "Timothy Besley", "Tim Besley", "Martin Weale", "Ian McCafferty",
    "Kristin Forbes", "Michael Saunders", "Silvana Tenreyro",
    "Gertjan Vlieghe", "Paul Fisher", "Martin Taylor",
    "Willem Buiter", "Willem H. Buiter",
    "Donald Kohn", "Don Kohn", "Anil Kashyap",
    "Randall Kroszner", "Randy Kroszner",
    "Carolyn Wilkins", "Carolyn A Wilkins",
    "Charles Goodhart",
}

# Historical MPC membership date ranges. Each entry maps a name variant to a list
# of (start_date, end_date) pairs (YYYY-MM-DD strings). end_date is None if still serving.
MPC_MEMBERSHIP: dict[str, list[tuple[str, str | None]]] = {
    # Governors
    "Andrew Bailey":           [("2020-03-16", None)],
    "Mervyn King":             [("2003-06-01", "2013-06-30")],
    "Edward George":           [("1993-07-01", "2003-06-30")],
    "Sir Edward George":       [("1993-07-01", "2003-06-30")],
    "Mark Carney":             [("2013-07-01", "2020-03-15")],
    # Deputy Governors
    "Dave Ramsden":            [("2017-09-04", None)],
    "Ben Broadbent":           [("2011-05-01", "2024-06-30")],
    "Sarah Breeden":           [("2023-11-01", None)],
    "Jon Cunliffe":            [("2013-11-01", "2023-10-31")],
    "Sir Jon Cunliffe":        [("2013-11-01", "2023-10-31")],
    "Rachel Lomax":            [("2003-07-01", "2008-06-30")],
    "John Gieve":              [("2006-01-01", "2009-03-31")],
    "Charles Bean":            [("2000-10-01", "2014-06-30")],
    "Charlie Bean":            [("2000-10-01", "2014-06-30")],
    "Paul Tucker":             [("2002-06-01", "2013-10-31")],
    "Minouche Shafik":         [("2014-08-01", "2017-02-28")],
    # Chief Economists
    "Andrew Haldane":          [("2014-07-01", "2021-06-30")],
    "Andy Haldane":            [("2014-07-01", "2021-06-30")],
    "Huw Pill":                [("2021-09-06", None)],
    "Spencer Dale":            [("2008-06-01", "2014-06-30")],
    # External members (recent)
    "Silvana Tenreyro":        [("2017-07-01", "2023-07-31")],
    "Gertjan Vlieghe":         [("2015-09-01", "2021-08-31")],
    "Michael Saunders":        [("2016-08-01", "2022-08-31")],
    "Jonathan Haskel":         [("2018-09-01", "2024-08-31")],
    "Catherine Mann":          [("2021-09-01", None)],
    "Catherine L. Mann":       [("2021-09-01", None)],
    "Catherine L Mann":        [("2021-09-01", None)],
    "Megan Greene":            [("2023-07-01", None)],
    "Swati Dhingra":           [("2022-08-01", None)],
    "Clare Lombardelli":       [("2024-07-01", None)],
    "Alan Taylor":             [("2024-09-01", None)],
    "Carolyn Wilkins":         [("2021-01-01", "2023-12-31")],
    "Carolyn A Wilkins":       [("2021-01-01", "2023-12-31")],
    "Randall Kroszner":        [("2018-09-01", "2023-08-31")],
    "Randy Kroszner":          [("2018-09-01", "2023-08-31")],
    "Anil Kashyap":            [("2016-09-01", "2020-08-31")],
    "Donald Kohn":             [("2014-07-01", "2018-05-31")],
    "Don Kohn":                [("2014-07-01", "2018-05-31")],
    "Kristin Forbes":          [("2014-07-01", "2017-06-30")],
    "Ian McCafferty":          [("2012-09-01", "2018-08-31")],
    "Martin Weale":            [("2010-08-01", "2016-07-31")],
    "Paul Fisher":             [("2009-03-01", "2014-06-30")],
    "Adam Posen":              [("2009-09-01", "2012-08-31")],
    "Adam S. Posen":           [("2009-09-01", "2012-08-31")],
    "David Miles":             [("2009-06-01", "2015-07-31")],
    "David Blanchflower":      [("2006-06-01", "2009-05-31")],
    "Timothy Besley":          [("2006-06-01", "2009-05-31")],
    "Tim Besley":              [("2006-06-01", "2009-05-31")],
    "Andrew Sentance":         [("2006-10-01", "2011-05-31")],
    "Andrew Sentence":         [("2006-10-01", "2011-05-31")],
    "Richard Lambert":         [("2003-06-01", "2006-05-31")],
    "Kate Barker":             [("2001-06-01", "2010-05-31")],
    "Stephen Nickell":         [("2000-06-01", "2006-05-31")],
    "Professor Stephen Nickell": [("2000-06-01", "2006-05-31")],
    "Christopher Allsopp":     [("2000-06-01", "2003-05-31")],
    "David Walton":            [("2005-07-01", "2006-06-23")],
    "Marian Bell":             [("2002-06-01", "2005-05-31")],
    "DeAnne Julius":           [("1997-06-01", "2001-05-31")],
    "Sushil Wadhwani":         [("1999-06-01", "2002-05-31")],
    "Charles Goodhart":        [("1997-06-01", "2000-05-31")],
    "Martin Taylor":           [("1998-06-01", "1999-05-31")],
    "Willem Buiter":           [("1997-06-01", "2000-05-31")],
    "Willem H. Buiter":        [("1997-06-01", "2000-05-31")],
}


def was_mpc_member(name: str, speech_date: str) -> bool:
    """Return True if `name` held an MPC seat on `speech_date` (YYYY-MM-DD)."""
    from membership import was_member
    # Check membership.py first (kept up to date automatically)
    if was_member("boe", name, speech_date):
        return True
    # Fall back to local hardcoded dict for any names not yet in members_history.json
    periods = MPC_MEMBERSHIP.get(name)
    if not periods:
        return False
    for start, end in periods:
        if speech_date >= start and (end is None or speech_date <= end):
            return True
    return False


_MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

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
    for col in ("body", "central_bank", "country"):
        if col not in cols:
            conn.execute(f"ALTER TABLE speeches ADD COLUMN {col} TEXT")
    conn.commit()
    return conn


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def get_all_boe_urls() -> list[str]:
    """Fetch all speech URLs from the BoE sitemap (one static page)."""
    s = _session()
    r = s.get(SITEMAP_URL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    links = soup.find_all("a", href=re.compile(r"/speech/\d{4}/"))
    urls = []
    for a in links:
        href = a["href"]
        url = href if href.startswith("http") else BASE + href
        urls.append(url)
    return urls


def _parse_date(soup: BeautifulSoup, url: str) -> str:
    """Extract YYYY-MM-DD date from a speech page."""
    # Strategy 1: "Published on {day} {Month} {year}" in page text
    text = soup.get_text(separator="\n")
    m = re.search(
        r"Published\s+on\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text
    )
    if m:
        day, mon, yr = m.group(1), m.group(2).lower(), m.group(3)
        mm = _MONTH_MAP.get(mon)
        if mm:
            return f"{yr}-{mm}-{int(day):02d}"

    # Strategy 2: <time datetime="YYYY-MM-DD"> in the page-banner section
    banner = soup.find(class_="page-banner")
    if banner:
        t = banner.find("time", {"datetime": re.compile(r"\d{4}-\d{2}-\d{2}")})
        if t:
            return t["datetime"][:10]

    # Strategy 3: first <time datetime> on page
    t = soup.find("time", {"datetime": re.compile(r"\d{4}-\d{2}-\d{2}")})
    if t:
        return t["datetime"][:10]

    # Strategy 4: year from URL
    m2 = re.search(r"/speech/(\d{4})/", url)
    if m2:
        return f"{m2.group(1)}-01-01"

    return ""


def _parse_speaker_title(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract (speaker, clean_title) from H1 or og:title meta."""
    # Try og:title first — reliably formatted
    og = soup.find("meta", {"property": "og:title"})
    raw = og["content"] if og else ""
    if not raw:
        h1 = soup.find("h1")
        raw = h1.get_text(strip=True) if h1 else ""

    # Pattern: "Title - Speech by Speaker" / "Title - Remarks by Speaker" etc.
    # Split on " - " then find "by "
    m = re.search(
        r"^(.*?)\s*[-–—−?]\s*(?:Speech|Remarks|Address|Lecture|Keynote|Statement|Presentation|Hearing|Panel\s+discussion|Panel|Slides)\s+(?:given\s+)?by\s+(.+)$",
        raw, re.IGNORECASE
    )
    # Also handle "Slides from {Name}'s ..." pattern
    if not m:
        m2 = re.search(r"^Slides from\s+(.+?)(?:'s|'s)\s+(.+)$", raw, re.IGNORECASE)
        if m2:
            return m2.group(1).strip(), raw.strip()
    if m:
        title = m.group(1).strip()
        speaker = m.group(2).strip()
        # Strip trailing role designations like ", Governor, Bank of England"
        speaker = re.split(r",\s*(?:Governor|Deputy|Chief|Member|Director)", speaker)[0].strip()
        return speaker, title

    # Fallback: use full string as title, unknown speaker
    return "Unknown", raw.strip()


def _find_boe_speech_pdf(soup: BeautifulSoup) -> str | None:
    """Return the URL of the primary BoE-hosted speech PDF, if present."""
    for a in soup.find_all("a", href=re.compile(r"/-/media/boe/files/speech/.*\.pdf", re.I)):
        href = a["href"]
        return href if href.startswith("http") else BASE + href
    return None


def _extract_pdf_text(pdf_url: str, session: requests.Session) -> str:
    """Download a PDF and extract all text using pdfplumber."""
    try:
        r = session.get(pdf_url, timeout=30)
        if r.status_code != 200:
            return ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
        return "\n".join(pages)
    except Exception as e:
        print(f"    PDF extraction failed ({pdf_url}): {e}")
        return ""


def _parse_body(soup: BeautifulSoup, session: requests.Session | None = None) -> str:
    """Extract speech body text. Falls back to BoE-hosted PDF when HTML has only a summary."""
    # Try page-content first (full HTML speeches)
    # Threshold is 2000 chars — short summaries (500-2000) still trigger PDF fallback
    pc = soup.find(class_="page-content")
    if pc:
        txt = pc.get_text(separator=" ", strip=True)
        if len(txt) >= 2000:
            return txt

    # PDF-only pages: look for a BoE-hosted speech PDF and extract its text
    if session:
        pdf_url = _find_boe_speech_pdf(soup)
        if pdf_url:
            pdf_text = _extract_pdf_text(pdf_url, session)
            if len(pdf_text) >= 500:
                return pdf_text

    # Last resort: strip noise from <main>
    import copy
    main = soup.find("main")
    if not main:
        return pc.get_text(separator=" ", strip=True) if pc else ""
    main = copy.copy(main)
    for noise in main.find_all(class_=re.compile(
        r"nav|footer|cookie|search|modal|breadcrumb|related|release-content|release-meta|release-tag|scroll-to-top"
    )):
        noise.decompose()
    for el in main.find_all(class_=re.compile(r"container-latest|med-block")):
        el.decompose()
    return main.get_text(separator=" ", strip=True)


def scrape_speech(url: str, session: requests.Session) -> dict | None:
    """Fetch a single BoE speech page and return parsed data."""
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        speaker, title = _parse_speaker_title(soup)
        date = _parse_date(soup, url)
        body = _parse_body(soup, session)
        return {
            "url":          url,
            "date":         date,
            "speaker":      speaker,
            "title":        title,
            "body":         body,
            "central_bank": "Bank of England",
            "country":      "GBR",
        }
    except Exception as e:
        print(f"    Error scraping {url}: {e}")
        return None


def store_speech(rec: dict, conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO speeches "
        "(url, date, speaker, title, body, central_bank, country) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rec["url"], rec["date"], rec["speaker"], rec["title"],
         rec["body"], rec["central_bank"], rec["country"]),
    )


def save_rating(url: str, score: int, justification: str, rated_at: str) -> None:
    conn = _conn()
    conn.execute(
        "UPDATE speeches SET score=?, justification=?, rated_at=? WHERE url=?",
        (score, justification, rated_at, url),
    )
    conn.commit()
    conn.close()


def get_existing_urls() -> set[str]:
    conn = _conn()
    urls = {r[0] for r in conn.execute("SELECT url FROM speeches WHERE central_bank='Bank of England'")}
    conn.close()
    return urls


RSS_URL = f"{BASE}/rss/speeches"


def _speaker_from_title_text(title: str) -> str:
    """Extract speaker name from a plain RSS title string without fetching the page."""
    m = re.search(
        r"[-–—−?]\s*(?:Speech|Remarks|Address|Lecture|Keynote|Statement|"
        r"Presentation|Panel(?:\s+discussion)?|Slides)\s+(?:given\s+)?by\s+(.+?)(?:\s+at\b|\s+in\b|$)",
        title, re.IGNORECASE,
    )
    if m:
        speaker = m.group(1).strip()
        return re.split(r",\s*(?:Governor|Deputy|Chief|Member|Director)", speaker)[0].strip()
    m2 = re.search(r"Slides from\s+(.+?)(?:'s|[’‘]s)\s+", title, re.IGNORECASE)
    if m2:
        return m2.group(1).strip()
    return ""


def get_recent_boe_rss() -> list[tuple[str, str]]:
    """Return (url, title) for the 50 most recent BoE speeches from the RSS feed."""
    s = _session()
    r = s.get(RSS_URL, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    channel = root.find("channel")
    if channel is None:
        return []
    results = []
    for item in channel.findall("item"):
        link = item.findtext("link", "").strip()
        title = item.findtext("title", "").strip()
        if link and "/speech/" in link:
            results.append((link, title))
    return results


def get_new_boe_2026() -> list[dict]:
    """
    Poll the RSS feed (real-time) for new speeches. Pre-filters by speaker name
    extracted from the RSS title — non-MPC speakers are skipped without fetching
    their pages. Returns unrated 2026 MPC speeches ready for rating.
    """
    print("Fetching BoE RSS feed ...")
    rss_items = get_recent_boe_rss()
    print(f"  {len(rss_items)} speeches in RSS feed")

    existing = get_existing_urls()
    new_items = [(url, title) for url, title in rss_items if url not in existing]
    print(f"  {len(new_items)} new (not yet in DB)")

    session = _session()
    conn = _conn()
    new_2026_mpc = []

    for url, rss_title in new_items:
        # Pre-filter: extract speaker from RSS title text without fetching the page
        rss_speaker = _speaker_from_title_text(rss_title)
        if rss_speaker not in MPC_MEMBERS:
            print(f"  Skip (non-MPC): {rss_speaker or '?'} | {rss_title[:50]}")
            continue

        rec = scrape_speech(url, session)
        if rec:
            store_speech(rec, conn)
            conn.commit()
            if rec["date"] >= "2026-01-01" and rec["speaker"] in MPC_MEMBERS:
                new_2026_mpc.append(rec)
            print(f"  Stored: {rec['speaker']} | {rec['title'][:55]}")
        time.sleep(0.4)

    conn.close()
    print(f"  {len(new_2026_mpc)} new 2026 MPC speeches to rate")
    return new_2026_mpc


def scrape_all_history(delay: float = 0.4) -> None:
    """
    One-time full historical scrape. Skips URLs already in DB.
    Run via: python scraper_boe.py --history
    """
    print("Fetching BoE sitemap ...")
    all_urls = get_all_boe_urls()
    existing = get_existing_urls()
    to_scrape = [u for u in all_urls if u not in existing]
    print(f"  {len(to_scrape)} speeches to scrape (of {len(all_urls)} total)\n")

    session = _session()
    conn = _conn()
    errors = 0

    for i, url in enumerate(to_scrape, 1):
        rec = scrape_speech(url, session)
        if rec:
            store_speech(rec, conn)
            year = url.split("/speech/")[1][:4] if "/speech/" in url else "?"
            print(f"[{i}/{len(to_scrape)}] {year} | {rec['speaker'][:30]} | {rec['title'][:50]}")
        else:
            print(f"[{i}/{len(to_scrape)}] SKIP {url}")
            errors += 1

        if i % 100 == 0:
            conn.commit()
        time.sleep(delay)

    conn.commit()
    conn.close()
    print(f"\nDone. {len(to_scrape) - errors} stored, {errors} errors.")


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--history" in sys.argv:
        scrape_all_history()
    else:
        results = get_new_boe_2026()
        print(f"\n{len(results)} new 2026 MPC speeches found.")
