"""Fetch body text for BoJ JP speeches that were stored with empty body."""
import os, sys, time, sqlite3
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import requests
from bs4 import BeautifulSoup
from scraper_boj import _extract_pdf_text, _pdf_url_ja, DB_PATH

BOJ_BASE = "https://www.boj.or.jp"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ja,en;q=0.9",
})

conn = sqlite3.connect(str(DB_PATH), timeout=30)
conn.execute("PRAGMA journal_mode=WAL")

rows = conn.execute("""
    SELECT url, date, speaker, title FROM speeches
    WHERE central_bank='Bank of Japan' AND language='ja'
      AND (body IS NULL OR body = '')
    ORDER BY date DESC
""").fetchall()
print(f"{len(rows)} JP speeches with empty body\n")

fixed = 0
for url, date, speaker, title in rows:
    print(f"  {date}  {speaker}  {title[:50]}")

    # Try PDF first
    pdf_url = _pdf_url_ja(url)
    body = _extract_pdf_text(pdf_url, session)

    # Fall back to speech page HTML
    if not body:
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or "utf-8"
                soup = BeautifulSoup(r.text, "html.parser")
                # BoJ speech pages wrap content in <div class="outline"> or <article>
                for sel in ["div.outline", "article", "div#main", "div.body"]:
                    el = soup.select_one(sel)
                    if el:
                        body = el.get_text(separator="\n", strip=True)
                        if len(body) > 500:
                            break
        except Exception as e:
            print(f"    HTML fetch error: {e}")

    if body and len(body) > 200:
        conn.execute("UPDATE speeches SET body=? WHERE url=?", (body, url))
        conn.commit()
        fixed += 1
        print(f"    OK — {len(body):,} chars")
    else:
        print(f"    SKIP — no text found (pdf={len(body) if body else 0} chars)")
    time.sleep(0.5)

conn.close()
print(f"\nFixed {fixed}/{len(rows)} speeches")
