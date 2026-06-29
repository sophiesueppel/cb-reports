"""
Seed 2024-2025 SARB speech URLs discovered via web search.
"""
import sys, os, sqlite3, time
sys.path.insert(0, os.path.dirname(__file__))
from pathlib import Path
from datetime import datetime, timezone, date as _date
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scraper_sarb import get_all_sarb_speeches_from_urls, ALL_SARB, save_rating
from rater import rate_speech
from classify_relevance_llm import run_classification
from report_sarb_filtered import generate_sarb_filtered_report

DB = Path("data/speeches.db")

URLS_2024 = [
    # Known page URLs
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2024/Speech-by-Lesetja-Kganyago-Governor-of-the-South-African-Reserve-Bank-at-the-launch-of-the-Corporation-for-Deposit-Insurance",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2024/keynote-address-by-deputy-governor-rashaad-cassim-at-the-2024-ma",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2024/sarb-governor-lesetja-kganyago-stellenbosch-university-special-guest-lecture",
    # Derived from PDF slugs (may or may not have a page)
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2024/kganyago-agm-2024",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2024/kganyago-fsca-2024",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2024/kganyago-payments-2024",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2024/kganyago-inca-2024",
]

URLS_2025 = [
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2025/kganyago-techsprint",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2025/kganyago-rates-tariffs",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2025/kganyago-g20-challenges",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2025/address-by-lesetja-kganyago-governor-of-the-sarb-at-alter-sisulu-university-komani-campus",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2025/cassim-mpg-jibar",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2025/tshazibana-financial-climate-policy",
    # Derived from PDF slugs
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2025/kganyago-price-stability",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2025/kganyago-brookings-2025-4",
    "https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2025/cassim-fmd-cocktail",
]

all_urls = URLS_2024 + URLS_2025
print(f"Seeding {len(all_urls)} candidate URLs (2024-2025) ...")
new_speeches = get_all_sarb_speeches_from_urls(all_urls)

today = _date.today()
cutoff = _date(today.year - 5, today.month, today.day).isoformat()
to_rate = [s for s in new_speeches if s.get("date", "") >= cutoff]

print(f"\n{len(to_rate)} speeches in 5-year window to rate ...")
errors = 0
for i, sp in enumerate(to_rate, 1):
    print(f"[{i}/{len(to_rate)}] {sp['speaker']} | {sp['date']} | {sp['title'][:55]}")
    if not sp.get("body"):
        print("  Skipped — no text")
        continue
    try:
        r = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                        bank="SARB", db_path=str(DB))
        now = datetime.now(timezone.utc).isoformat()
        save_rating(sp["url"], r["score"], r["justification"], now)
        print(f"  {r['score']}/10 -- {r['justification'][:70]}...")
    except Exception as e:
        print(f"  Error: {e}")
        errors += 1
    time.sleep(0.3)

print(f"\nDone. {len(to_rate)-errors} rated, {errors} errors.")
print("\nRunning classifier ...")
run_classification(bank="SARB")

print("\nGenerating report ...")
generate_sarb_filtered_report()
print("Done.")
