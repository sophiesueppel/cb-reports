"""Rate stored-but-unrated CBRT speeches."""
import os, sys, time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.environ.get("OPENAI_API_KEY"):
    sys.exit("Error: OPENAI_API_KEY not set.")

import sqlite3
from scraper_cbrt import save_rating, DB_PATH
from rater import rate_speech
from translator import translate_speech, detect_language
from classify_relevance_llm import run_classification
from report_cbrt_filtered import generate_cbrt_filtered_report

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
cutoff = f"{datetime.now().year - 5}-01-01"
rows = conn.execute(
    "SELECT url, date, speaker, title, body, language, body_en FROM speeches "
    "WHERE central_bank='CBRT' AND score IS NULL AND date >= ? AND body IS NOT NULL "
    "ORDER BY date",
    (cutoff,),
).fetchall()
conn.close()

print(f"DB: {DB_PATH}")
print(f"5-year cutoff: {cutoff}")
print(f"{len(rows)} unrated CBRT speeches\n")

errors = 0
for i, row in enumerate(rows, 1):
    url, date, speaker, title, body, lang, body_en = (
        row["url"], row["date"], row["speaker"], row["title"],
        row["body"], row["language"], row["body_en"],
    )
    print(f"[{i}/{len(rows)}] {speaker} | {date} | {title[:55]}")
    try:
        lang = lang or detect_language(body, title)
        stored_en = body_en or None
        if lang != "en" and not stored_en:
            stored_en = translate_speech(body, lang, title=title, speaker=speaker)
            time.sleep(0.2)
        r = rate_speech(title, speaker, date, body,
                        bank="CBRT", db_path=str(DB_PATH),
                        language=lang, body_en=stored_en)
        stored_en = stored_en or r.get("body_en") or None
        now = datetime.now(timezone.utc).isoformat()
        save_rating(url, r["score"], r["justification"], now, body_en=stored_en)
        print(f"  {r['score']}/10 — {r['justification'][:70]}...")
    except Exception as e:
        print(f"  Error: {e}")
        errors += 1
    time.sleep(0.3)

print(f"\nDone. {len(rows) - errors} rated, {errors} errors.")
run_classification(bank="CBRT")
generate_cbrt_filtered_report()
