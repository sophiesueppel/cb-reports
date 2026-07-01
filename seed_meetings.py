"""One-shot: load the hardcoded meetings.py lists into the SQLite `meetings` table.

Idempotent — safe to re-run (uses upsert_meeting, which skips locked rows and only
updates real diffs). Run once after correcting meetings.py:

    .venv\\Scripts\\python.exe seed_meetings.py

After seeding, main.refresh_meetings() keeps the table current from official sites.
"""
import os
import re
import sys

os.environ.setdefault("CB_MEETINGS_NO_DB", "1")  # read raw seed lists, not the DB

import meetings
from meetings_store import BANK_VARS, upsert_meeting, count_meetings, lock_meeting

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_BP_RE = re.compile(r"([\d.]+)\s*bp", re.I)
_VOTE_RE = re.compile(r"·\s*(\d+)\s*[–-]\s*(\d+)")

# Meetings that were hand-corrected against official sources and must not be
# clobbered by a future mis-extraction.
_LOCK = {
    "Bank of Japan": {"2025-12-19", "2026-01-23", "2026-03-19", "2026-04-28", "2026-06-16"},
}


def _bp_from(entry: dict) -> int | None:
    """Signed basis-point change inferred from label + decision."""
    dec = entry.get("decision")
    if dec in ("hold", "upcoming"):
        return 0 if dec == "hold" else None
    m = _BP_RE.search(entry.get("label", ""))
    if not m:
        return None
    mag = int(round(float(m.group(1))))
    return -mag if dec == "cut" else mag


def _vote_from(entry: dict) -> str | None:
    m = _VOTE_RE.search(entry.get("label", ""))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def main() -> None:
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped-locked": 0}
    for bank, var in BANK_VARS.items():
        rows = getattr(meetings, var, [])
        for e in rows:
            result = upsert_meeting(
                bank, e["date"], e["decision"],
                rate=e.get("rate"),
                bp_change=_bp_from(e),
                vote=_vote_from(e),
                label=e.get("label"),
                note=e.get("note"),
                source="seed",
            )
            counts[result] = counts.get(result, 0) + 1
        print(f"  {bank}: {len(rows)} seed rows")

    # Lock the hand-verified corrections.
    for bank, dates in _LOCK.items():
        for d in dates:
            lock_meeting(bank, d, True)
        print(f"  locked {len(dates)} {bank} rows")

    print(f"\nSeed complete: {counts}")
    print(f"Total rows in meetings table: {count_meetings()}")


if __name__ == "__main__":
    main()
