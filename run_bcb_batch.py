"""Run BCB historical batch scrape+rate from Portuguese discursos API."""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from main import run_bcb_batch

start_year = int(sys.argv[1]) if len(sys.argv) > 1 else 2021
run_bcb_batch(start_year=start_year)
