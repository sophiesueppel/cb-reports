"""Enumerate Fed 1996-2005 speeches by fetching old Wayback Machine snapshots
of the annual listing pages, which in the 1990s-2000s actually listed the speeches.
"""
import re
import sqlite3
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DB_PATH = Path("data/speeches.db")
FED_BASE = "https://www.federalreserve.gov"

# Wayback snapshots that contain complete listings.
# Pre-2001 pages list speeches as {date}.htm
# 2001+ pages list speeches as {date}/default.htm
# Use a snapshot timestamp from a few months after year-end to get the full year.
SNAPSHOT_YEARS = {
    2004: "20050601",
    2005: "20060601",
}

# Pre-2001 style: relative link "19981112.htm" or "199810222.htm"
REL_OLD_RE = re.compile(r"^(\d{8,9})\.htm$", re.I)
# 2001+ style: relative link "20011218/default.htm" or "200111302/default.htm"
REL_NEW_RE = re.compile(r"^(\d{8,9})/default\.htm$", re.I)
# Wayback-wrapped full URL either style
WB_OLD_RE = re.compile(r"/boarddocs/speeches/(\d{4})/(\d{8,9})\.htm", re.I)
WB_NEW_RE = re.compile(r"/boarddocs/speeches/(\d{4})/(\d{8,9})/default\.htm", re.I)


def get_wayback_listing(year: int, snap: str, session: requests.Session) -> list[str]:
    """Fetch the Wayback Machine snapshot of the boarddocs/{year}/ listing page
    and return individual speech URLs found on it.

    Handles two URL formats:
      Pre-2001: boarddocs/speeches/1998/19981112.htm
      2001+:    boarddocs/speeches/2001/20011218/default.htm
    """
    wb_url = f"https://web.archive.org/web/{snap}/https://www.federalreserve.gov/boarddocs/speeches/{year}/"
    try:
        r = session.get(wb_url, timeout=30)
        if r.status_code != 200:
            print(f"  Wayback {year} listing: {r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        urls = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = REL_OLD_RE.match(href)
            if m:
                urls.add(f"{FED_BASE}/boarddocs/speeches/{year}/{m.group(1)}.htm")
                continue
            m = REL_NEW_RE.match(href)
            if m:
                urls.add(f"{FED_BASE}/boarddocs/speeches/{year}/{m.group(1)}/default.htm")
                continue
            m = WB_OLD_RE.search(href)
            if m and int(m.group(1)) == year:
                urls.add(f"{FED_BASE}/boarddocs/speeches/{year}/{m.group(2)}.htm")
                continue
            m = WB_NEW_RE.search(href)
            if m and int(m.group(1)) == year:
                urls.add(f"{FED_BASE}/boarddocs/speeches/{year}/{m.group(2)}/default.htm")
        return sorted(urls)
    except Exception as e:
        print(f"  Wayback {year}: ERROR {e}")
        return []


def fetch_speech(url: str, session: requests.Session) -> dict | None:
    """Fetch a single old Fed speech and return its parsed data."""
    try:
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        # Date from URL — both formats: .../19981112.htm  and  .../20011218/default.htm
        m = re.search(r"/(\d{8})\d?(?:\.htm|/default\.htm)$", url)
        if m:
            d = m.group(1)
            date = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        else:
            date = "Unknown"

        # Title: usually in <title> or <h2>/<h3>
        title = "Unknown"
        t = soup.find("title")
        if t:
            title = t.get_text(strip=True)
            # Strip "FRB: Speech, NAME -- TITLE -- DATE"
            if "--" in title:
                parts = title.split("--")
                if len(parts) >= 2:
                    title = parts[1].strip()
            elif ":" in title:
                title = title.split(":", 1)[-1].strip()

        # Speaker: "Remarks by Governor X" or just from the page
        speaker = "Unknown"
        for tag in soup.find_all(["p", "h1", "h2", "h3", "b"]):
            text = tag.get_text(" ", strip=True)
            m2 = re.search(
                r"(?:Remarks|Speech|Statement|Comments|Testimony)"
                r"\s+by\s+((?:Chairman|Governor|President|Vice Chair|Chair)\s+[A-Z][a-z]+"
                r"(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)*)",
                text
            )
            if m2:
                speaker = m2.group(1)
                break

        # Body: all <p> with > 80 chars
        paras = [p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 80]
        body = "\n\n".join(paras)

        return {"url": url, "date": date, "speaker": speaker, "title": title, "body": body}
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def load_fed_historical():
    s = requests.Session()
    s.headers.update(HEADERS)

    conn = sqlite3.connect(str(DB_PATH), timeout=120)  # wait up to 2 min for BoJ loader to release lock
    existing = {r[0] for r in conn.execute("SELECT url FROM speeches WHERE central_bank='Federal Reserve'")}

    # Delete the old stub index-page rows (not real speeches)
    stubs = [f"{FED_BASE}/newsevents/speech/{y}speech.htm" for y in range(1996, 2006)]
    deleted = 0
    for stub in stubs:
        if stub in existing:
            conn.execute("DELETE FROM speeches WHERE url=?", (stub,))
            existing.discard(stub)
            deleted += 1
    conn.commit()
    print(f"Removed {deleted} stub index-page rows")

    grand_total = 0
    for year, snap in SNAPSHOT_YEARS.items():
        print(f"\n--- Fed {year} ---")
        speech_urls = get_wayback_listing(year, snap, s)
        print(f"  Found {len(speech_urls)} speech URLs from Wayback snapshot")

        if not speech_urls:
            # Fallback: try the live boarddocs URL if we got 0
            print(f"  Trying direct boarddocs enumeration ...")
            # Can't enumerate without a list — skip
            continue

        year_stored = 0
        for url in speech_urls:
            if url in existing:
                continue
            rec = fetch_speech(url, s)
            if rec:
                conn.execute(
                    "INSERT OR IGNORE INTO speeches "
                    "(url, date, speaker, title, body, central_bank, country) "
                    "VALUES (?, ?, ?, ?, ?, 'Federal Reserve', 'USA')",
                    (rec["url"], rec["date"], rec["speaker"], rec["title"], rec["body"]),
                )
                existing.add(url)
                year_stored += 1
                grand_total += 1
            time.sleep(0.5)  # Be polite to Wayback Machine

        conn.commit()
        print(f"  {year}: {year_stored} new speeches stored")
        time.sleep(2)  # Pause between years to avoid rate-limiting Wayback

    conn.close()
    print(f"\nFed historical load complete: {grand_total} total speeches stored")


if __name__ == "__main__":
    load_fed_historical()
