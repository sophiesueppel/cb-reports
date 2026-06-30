import sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://www.riksbank.se"
LISTING_BASE = f"{BASE}/en-gb/press-and-published/speeches-and-presentations/"

from playwright.sync_api import sync_playwright

_TITLE_RE = re.compile(
    r"^(?:Governor|First\s+Deputy\s+Governor|Deputy\s+Governor|Chief\s+Economist|Adviser|Director|Professor)\s+",
    re.IGNORECASE,
)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_context(user_agent="Mozilla/5.0").new_page()

    # Check just page 1 of 2021
    page.goto(f"{LISTING_BASE}?year=2021&page=1", timeout=30000, wait_until="networkidle")
    links = page.query_selector_all("a.listing-item--speach")
    print(f"Page 1 of year=2021: {len(links)} links")
    for i, a in enumerate(links[:5]):
        raw = a.inner_text().strip()
        spk_match = re.search(r"Speaker:\s*\n?\s*(.+?)(?:\n|Place:|$)", raw)
        date_match = re.search(r"Date:\s*\n?\s*(\d{2}/\d{2}/\d{4})", raw)
        speaker_raw = spk_match.group(1).strip() if spk_match else ""
        date_raw = date_match.group(1) if date_match else ""
        name = _TITLE_RE.sub("", speaker_raw).strip()
        print(f"  [{i}] speaker_raw={repr(speaker_raw)} -> cleaned={repr(name)} | date={date_raw}")
        print(f"       raw[:120]={repr(raw[:120])}")

    # Check page 2 to see if it's different speeches
    page.goto(f"{LISTING_BASE}?year=2021&page=2", timeout=30000, wait_until="networkidle")
    links2 = page.query_selector_all("a.listing-item--speach")
    print(f"\nPage 2 of year=2021: {len(links2)} links")
    for a in links2[:3]:
        raw = a.inner_text().strip()
        date_match = re.search(r"Date:\s*\n?\s*(\d{2}/\d{2}/\d{4})", raw)
        spk_match = re.search(r"Speaker:\s*\n?\s*(.+?)(?:\n|Place:|$)", raw)
        speaker_raw = spk_match.group(1).strip() if spk_match else ""
        date_raw = date_match.group(1) if date_match else ""
        print(f"  speaker_raw={repr(speaker_raw)} | date={date_raw}")

    browser.close()
