"""
Run Riksbank, BoJ and BCB backfill steps in parallel.

Safe to run alongside rebuild_db.py while it is still processing CNB —
each script only touches its own bank's rows so there is no data conflict.
SQLite WAL mode handles concurrent write serialisation.

Usage (new terminal, from project root):
    python run_parallel_backfill.py
"""
import os
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

DEST = Path("data/speeches_rebuild.db")
if not DEST.exists():
    sys.exit(f"Error: {DEST} not found. Run from the project root directory.")

ENV = {**os.environ, "CB_DB_PATH": str(DEST)}

# Ensure WAL mode is on before any parallel writers open the file
_db = sqlite3.connect(str(DEST), timeout=30)
_db.execute("PRAGMA journal_mode=WAL")
_db.execute("PRAGMA busy_timeout=30000")
_db.close()
print(f"WAL mode confirmed on {DEST}")


def run(cmd_args, label):
    start = datetime.now()
    print(f"\n[START] {label}")
    result = subprocess.run([sys.executable] + cmd_args, env=ENV)
    elapsed = datetime.now() - start
    status = "OK" if result.returncode == 0 else f"exit {result.returncode}"
    print(f"[DONE ] {label} — {status} in {elapsed}")
    return result.returncode


# ── Phase 1: Riksbank and BoJ in parallel ────────────────────────────────────
riksbank_thread = threading.Thread(
    target=run,
    args=(["run_riksbank_batch.py", "2016"], "Riksbank 2016–present"),
    daemon=True,
)
boj_thread = threading.Thread(
    target=run,
    args=(["run_boj_batch.py"], "BoJ (EN + JP indexes)"),
    daemon=True,
)

print("\nPhase 1: Riksbank + BoJ in parallel ...")
riksbank_thread.start()
boj_thread.start()
riksbank_thread.join()
boj_thread.join()
print("\nPhase 1 complete.")

# ── Phase 2: BCB (sequential — language fix is instant, then translations) ───
print("\nPhase 2: BCB ...")
run(["backfill_translations.py", "--fix-lang", "--bank=BCB"],
    "BCB language detection")
run(["backfill_translations.py", "--skip-fix", "--bank=BCB"],
    "BCB Portuguese→EN translation")

print("\nAll done. rebuild_db.py will swap the file when its CNB step finishes.")
