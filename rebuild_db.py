"""
rebuild_db.py — Run all backfill steps on a copy of speeches.db.

Copies speeches.db → speeches_rebuild.db, runs the full backfill sequence
targeting the copy, then swaps the rebuild over the original.

Safe to run while speeches.db is in use for other work — the original is
never touched until the final swap.

Usage:
    python rebuild_db.py            # full run
    python rebuild_db.py --no-swap  # run but don't swap at the end
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SRC = Path("data/speeches.db")
DEST = Path("data/speeches_rebuild.db")
ENV = {**os.environ, "CB_DB_PATH": str(DEST)}
NO_SWAP = "--no-swap" in sys.argv


def run(cmd_args, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run([sys.executable] + cmd_args, env=ENV)
    if result.returncode != 0:
        print(f"\n[!] Step '{label}' exited {result.returncode} — continuing with next step.")
    return result.returncode


# ── 1. Copy the database ──────────────────────────────────────────────────────
print(f"\nCopying {SRC} → {DEST} ...")
if not SRC.exists():
    sys.exit(f"Error: {SRC} not found. Run from the project root directory.")
shutil.copy2(SRC, DEST)
size_mb = DEST.stat().st_size / 1024 / 1024
print(f"Copy done ({size_mb:.1f} MB)")

start = datetime.now()

# ── 2. Backfill steps (all target DEST via CB_DB_PATH env var) ────────────────

# Fix speeches incorrectly tagged language='cs' (fast, no API calls)
run(["backfill_translations.py", "--fix-lang", "--bank=CNB"],
    "Pass 1 — CNB language tag fix (no API cost)")

# Translate remaining CNB Czech speeches → body_en (~510 speeches, ~70 min)
run(["backfill_translations.py", "--skip-fix", "--bank=CNB"],
    "Pass 2 — CNB Czech→EN translation (~70 min)")

# Scrape both CNB listings (Czech + English, 2000–present) then rate 2021+ (~40 min)
run(["backfill_cnb.py"],
    "CNB — scrape all speeches + rate 2021–present (~40 min)")

# Riksbank: scrape from 2016, rate last 5 years (~25 min)
run(["run_riksbank_batch.py", "2016"],
    "Riksbank — scrape 2016–present + rate last 5 years (~25 min)")

# BoJ: scrape EN + JP indexes, translate Japanese, rate last 5 years (~15 min)
run(["run_boj_batch.py"],
    "BoJ — scrape + translate JP + rate last 5 years (~15 min)")

# BCB: detect language for NULL-tagged speeches, then translate Portuguese → EN
run(["backfill_translations.py", "--fix-lang", "--bank=BCB"],
    "BCB — detect language for existing speeches (no API cost)")
run(["backfill_translations.py", "--skip-fix", "--bank=BCB"],
    "BCB — translate Portuguese speeches → body_en (~427 speeches, ~30 min)")

# Titles: translate all non-English speech titles → title_en
run(["backfill_translations.py", "--titles-only"],
    "All banks — translate non-English titles → title_en")

elapsed = datetime.now() - start
print(f"\n{'='*60}")
print(f"  All steps complete in {elapsed}")
print(f"{'='*60}")

# ── 3. Swap rebuild over the original ────────────────────────────────────────
if NO_SWAP:
    print(f"\n--no-swap set. Rebuilt DB is at {DEST}.")
    print(f"To finish manually: rename {DEST} → {SRC}")
else:
    backup = Path("data/speeches_old.db")
    print(f"\nSwapping files:")
    print(f"  {SRC} → {backup}")
    print(f"  {DEST} → {SRC}")
    if backup.exists():
        backup.unlink()
    SRC.rename(backup)
    DEST.rename(SRC)
    print(f"\nDone. speeches.db is now the rebuilt version.")
    print(f"Previous database kept as {backup} — delete it once you've verified.")
