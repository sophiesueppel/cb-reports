import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv
load_dotenv()
from scraper_cnb import _fetch_listing_year, _fetch_speech_body, LISTING_URL
from rater import rate_speech
from playwright.sync_api import sync_playwright

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
print(f"Listing URL: {LISTING_URL}")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=_UA)
    page = ctx.new_page()
    items = _fetch_listing_year(page, 2024)
    print(f"Found {len(items)} items for 2024")
    for it in items[:5]:
        print(f"  date={it['date_raw']!r}  speaker={it['speaker_raw']!r}  title={it['title'][:50]}")
    browser.close()

if not items:
    print("No items found — Czech listing may use different selectors")
    raise SystemExit(1)

url = items[0]["url"]
body, date, speaker = _fetch_speech_body(url)
print(f"\nFirst speech: {url}")
print(f"  date={date}  speaker={speaker}  body={len(body)} chars")
print(f"  sample: {body[:200]}")

if len(body) >= 800:
    print("\nRating + translating...")
    r = rate_speech(items[0]["title"], speaker or "test", date or "2024-01-01", body, bank="CNB", language="cs")
    print(f"  score={r['score']}")
    print(f"  justification={r['justification']}")
    print(f"  body_en present: {'body_en' in r}")
    if "body_en" in r:
        print(f"  body_en sample: {r['body_en'][:200]}")
