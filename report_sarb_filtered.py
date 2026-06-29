"""SARB filtered sentiment report. Run: python report_sarb_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_sarb_filtered_report() -> None:
    from meetings import SARB_MEETINGS
    from scraper_sarb import ALL_SARB, _SARB_CURRENT

    generate_filtered_report(
        bank_db_name="SARB",
        bank_label="South African Reserve Bank",
        accent_color="#006B3F",  # SARB green
        output_path=Path("report_sarb_filtered.html"),
        meetings=SARB_MEETINGS,
        member_filter=lambda speaker, date: speaker in ALL_SARB,
        active_members=list(_SARB_CURRENT),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_sarb_filtered_report()
