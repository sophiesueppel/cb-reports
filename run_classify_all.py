"""Run the LLM relevance classifier with --reset across all 4 banks, logging to files."""
import subprocess, sys, time
from pathlib import Path

BANKS = ["Federal Reserve", "ECB", "Bank of England", "Bank of Japan"]
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

for bank in BANKS:
    log_path = LOG_DIR / f"classify_{bank.lower().replace(' ', '_')}_reset.log"
    print(f"\n{'='*60}")
    print(f"Starting: {bank}")
    print(f"Log: {log_path}")
    print(f"{'='*60}")

    with open(log_path, "w", encoding="utf-8") as f:
        result = subprocess.run(
            [sys.executable, "classify_relevance_llm.py", f"--bank={bank}", "--reset"],
            stdout=f, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace",
        )

    # Print summary from log
    lines = log_path.read_text(encoding="utf-8").splitlines()
    for line in lines[-5:]:
        print(f"  {line}")

    print(f"Exit code: {result.returncode}")
    if result.returncode != 0:
        print(f"  !! FAILED — check {log_path}")
        break
    time.sleep(1)

print("\nAll banks done.")
