import sys, time, requests
from bs4 import BeautifulSoup
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=_UA)
    page = ctx.new_page()
    page.goto("https://www.cnb.cz/cs/verejnost/servis-pro-media/vystoupeni-konference-seminare/prezentace-a-vystoupeni/?year=2008", timeout=30000, wait_until="networkidle")
    time.sleep(2)
    entries = page.query_selector_all(".list-entry")
    print(f"2008 entries: {len(entries)}")
    urls = []
    for e in entries[:6]:
        link = e.query_selector("h2 a")
        auth = e.query_selector(".author a")
        if link:
            href = link.get_attribute("href")
            speaker = auth.inner_text().strip() if auth else "?"
            title = link.inner_text().strip()[:70]
            print(f"  {speaker} | {href}")
            urls.append(href)
    browser.close()

# Now check one of those URLs
if urls:
    s = requests.Session()
    s.headers["User-Agent"] = _UA
    url = "https://www.cnb.cz" + urls[0] if urls[0].startswith("/") else urls[0]
    print(f"\nFetching: {url}")
    r = s.get(url, timeout=20)
    print(f"Status: {r.status_code}")
    soup = BeautifulSoup(r.text, "html.parser")
    pdfs = [a.get("href","") for a in soup.find_all("a", href=True) if a["href"].lower().endswith(".pdf")]
    print(f"PDF links: {pdfs[:3]}")
    main = soup.select_one("main") or soup.body
    if main:
        txt = main.get_text(" ", strip=True)
        print(f"Body chars: {len(txt)}")
        print(f"Sample: {txt[:300]}")
