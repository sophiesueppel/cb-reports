"""One-off: re-extract evidence_quotes for directional speeches in the last 5 years
using the improved extractor prompt (favours stance/intent over bare facts).

Resets the target rows' evidence_quotes to NULL, then runs backfill_quotes() which
re-extracts only NULL rows. Safe to re-run."""
import os, sqlite3, sys
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))
today = date.today()
cut5y = date(today.year - 5, today.month, today.day).isoformat()

conn = sqlite3.connect(str(DB))
n = conn.execute(
    "UPDATE speeches SET evidence_quotes=NULL "
    "WHERE ((score BETWEEN 1 AND 3) OR score>=7) AND body IS NOT NULL "
    "AND length(body)>500 AND date>=?", (cut5y,)
).rowcount
conn.commit()
conn.close()
print(f"Reset evidence_quotes for {n} directional speeches since {cut5y}. Re-extracting ...")

from backfill_evidence_quotes import backfill_quotes
done, kept = backfill_quotes()
print(f"Re-extraction complete: {done} speeches, {kept} quotes stored.")
