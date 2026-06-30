import re
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime

BASE_URL = "https://www.federalreserve.gov"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

SPEECH_HREF_RE = re.compile(r"^/newsevents/speech/\w+\.htm$")
DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}"
)
SPEAKER_RE = re.compile(
    r"(First Vice President|Vice Chair for Supervision|Vice Chair|Governor|President|Chair)"
    r"\s+[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+"
)


@dataclass
class Speech:
    date: str       # YYYY-MM-DD
    speaker: str
    title: str
    url: str
    text: str


def _parse_date(s: str) -> str:
    try:
        return datetime.strptime(s.strip(), "%B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return s.strip()


URL_DATE_RE = re.compile(r"/[a-z]+(\d{8})[a-z]?\.htm$")


def date_from_url(url: str) -> datetime | None:
    """Extract the date embedded in a speech URL (e.g. cook20260624a.htm → 2026-06-24)."""
    m = URL_DATE_RE.search(url)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d")
        except ValueError:
            return None
    return None


def get_all_speech_urls(year: int) -> list[str]:
    """Return all speech URLs from the given year's listing page, deduplicated.
    Tries the modern format first, falls back to the pre-2011 format."""
    candidates = [
        f"{BASE_URL}/newsevents/{year}-speeches.htm",
        f"{BASE_URL}/newsevents/speech/{year}speech.htm",
    ]
    for listing_url in candidates:
        resp = requests.get(listing_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        seen: set[str] = set()
        urls: list[str] = []
        for link in soup.find_all("a", href=SPEECH_HREF_RE):
            full = BASE_URL + link["href"]
            if full not in seen:
                seen.add(full)
                urls.append(full)
        if urls:
            return urls
    return []


def get_latest_speech_url() -> str:
    """Return the URL of the most recent speech from the Fed listing page."""
    year = datetime.now().year
    for y in [year, year - 1]:
        listing_url = f"{BASE_URL}/newsevents/{y}-speeches.htm"
        resp = requests.get(listing_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        link = soup.find("a", href=SPEECH_HREF_RE)
        if link:
            return BASE_URL + link["href"]
    raise RuntimeError("Could not find any speeches on federalreserve.gov")


def get_speech(url: str) -> Speech:
    """Fetch and parse a single speech page."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = "utf-8"  # Fed pages are UTF-8; override any misdetected encoding
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Title: first <h3> or <h2> on the page
    title_el = soup.find("h3") or soup.find("h2")
    title = title_el.get_text(" ", strip=True) if title_el else "Unknown"

    # Date: search all text nodes for a date pattern
    date = "Unknown"
    for string in soup.find_all(string=DATE_RE):
        m = DATE_RE.search(string)
        if m:
            date = _parse_date(m.group(0))
            break

    # Speaker: try <p class="speaker"> first (present on all pages),
    # fall back to bio link text for older page layouts.
    speaker = "Unknown"
    el = soup.find("p", class_="speaker")
    if el:
        speaker = el.get_text(" ", strip=True)
    if speaker == "Unknown":
        for link in soup.find_all("a", href=re.compile(r"/aboutthefed/bios/")):
            text = link.get_text(" ", strip=True)
            if SPEAKER_RE.search(text):
                speaker = text
                break

    # Body: all <p> tags with substantial content (skip nav/footer noise)
    paragraphs = [
        p.get_text(" ", strip=True)
        for p in soup.find_all("p")
        if len(p.get_text(strip=True)) > 80
    ]
    text = "\n\n".join(paragraphs)

    return Speech(date=date, speaker=speaker, title=title, url=url, text=text)
