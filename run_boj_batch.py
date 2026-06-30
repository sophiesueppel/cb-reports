"""Run the BoJ batch: load all speeches 2021-present, rate last 5 years, generate report."""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from main import run_boj_batch
run_boj_batch(start_year=2021)
