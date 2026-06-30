"""
Parse speaker names from BoE speech titles where speaker='Unknown',
update the DB, then rate the newly identified MPC member speeches.
"""
import os
import re
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from scraper_boe import was_mpc_member, save_rating, DB_PATH
from rater import rate_speech

# ---------------------------------------------------------------------------
# Name extraction
# ---------------------------------------------------------------------------

# Lazy: capture everything from "by " up to a preposition/punctuation/end
_BY_RE = re.compile(
    r"\bby\s+(.+?)(?:\s+(?:at|for|in|on|to|of|during|about|regarding|and)\b|[,:]\s|\s*$)",
    re.UNICODE | re.IGNORECASE,
)
_FROM_RE = re.compile(
    r"\bfrom\s+(.+?)(?:'s\b|\s+(?:at|for|in|on)\b|\s*$)",
    re.UNICODE,
)
# Em-dash/en-dash/hyphen then a name at the very end
_DASH_RE = re.compile(
    r"[–\-−]\s*((?:[A-Z][a-zA-Zé\-]+\s+){1,3}[A-Z][a-zA-Zé\-]+)\s*$",
    re.UNICODE,
)


def _is_name(s: str) -> bool:
    """Return True if s looks like a person's name (2–5 words, each starting capital)."""
    words = s.strip().split()
    if len(words) < 2 or len(words) > 5:
        return False
    for w in words:
        # Each word must start with a capital letter
        if not w[0].isupper():
            return False
    # Last word must be a real word, not a single letter
    if len(words[-1]) < 2:
        return False
    return True


def extract_speaker(title: str) -> str | None:
    # 1. "... by Name" — stop at prepositions, commas, colons, or end
    m = _BY_RE.search(title)
    if m:
        candidate = m.group(1).strip().rstrip(",.:;")
        if _is_name(candidate):
            return candidate

    # 2. "from Name's ..." (e.g. "slides from Huw Pill's fireside chat")
    m = _FROM_RE.search(title)
    if m:
        candidate = m.group(1).strip()
        if _is_name(candidate):
            return candidate

    # 3. "− Name" or "- Name" at end (e.g. "Lecture − Andrew Bailey")
    m = _DASH_RE.search(title)
    if m:
        candidate = m.group(1).strip()
        if _is_name(candidate):
            return candidate

    return None


# ---------------------------------------------------------------------------
# Step 1: Update speaker field for ALL Unknown speeches
# ---------------------------------------------------------------------------

conn = sqlite3.connect(str(DB_PATH))
rows = conn.execute(
    "SELECT url, title FROM speeches WHERE central_bank='Bank of England' AND speaker='Unknown'"
).fetchall()

print(f"Found {len(rows)} Unknown-speaker BoE speeches")
updated = 0
no_match = []

for url, title in rows:
    name = extract_speaker(title)
    if name:
        conn.execute("UPDATE speeches SET speaker=? WHERE url=?", (name, url))
        updated += 1
    else:
        no_match.append(title)

conn.commit()
print(f"Updated {updated} speaker fields")
if no_match:
    print(f"\nCould not parse speaker from {len(no_match)} titles:")
    for t in no_match:
        print(f"  {t}", flush=True)

# ---------------------------------------------------------------------------
# Step 2: Rate newly identified MPC speeches (last 5yr, has body, no score)
# ---------------------------------------------------------------------------

if not os.environ.get("OPENAI_API_KEY"):
    sys.exit("\nError: OPENAI_API_KEY not set — can't rate speeches.")

today = date.today()
cutoff = date(today.year - 5, today.month, today.day).isoformat()

to_rate = conn.execute(
    "SELECT url, speaker, date, title, body FROM speeches "
    "WHERE central_bank='Bank of England' "
    "  AND score IS NULL "
    "  AND date >= ? "
    "  AND length(body) >= 500 "
    "ORDER BY date DESC",
    (cutoff,),
).fetchall()
conn.close()

# Filter to actual MPC members on the date of the speech
mpc_rows = [r for r in to_rate if was_mpc_member(r[1], r[2])]
print(f"\nSpeeches now eligible for rating: {len(mpc_rows)} (of {len(to_rate)} unrated with text)")
print()

rated = errors = 0
for i, (url, speaker, speech_date, title, body) in enumerate(mpc_rows, 1):
    print(f"[{i}/{len(mpc_rows)}] {speech_date} | {speaker} | {title[:55]}", flush=True)
    try:
        result = rate_speech(title, speaker, speech_date, body,
                             bank="Bank of England", db_path=str(DB_PATH))
        save_rating(url, result["score"], result["justification"],
                    time.strftime("%Y-%m-%dT%H:%M:%S"))
        print(f"  Score: {result['score']}/10 — {result['justification'][:80]}", flush=True)
        rated += 1
    except Exception as e:
        print(f"  ERROR: {e}", flush=True)
        errors += 1
    time.sleep(0.3)

print(f"\nDone. {rated} rated, {errors} errors.")
