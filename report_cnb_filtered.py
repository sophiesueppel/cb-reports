"""CNB (Czech National Bank) filtered sentiment report. Run: python report_cnb_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_cnb_filtered_report() -> None:
    from meetings import CNB_MEETINGS
    from scraper_cnb import ALL_CNB

    generate_filtered_report(
        bank_db_name="CNB",
        bank_label="Czech National Bank",
        accent_color="#D7141A",  # Czech flag red
        output_path=Path("report_cnb_filtered.html"),
        meetings=CNB_MEETINGS,
        member_filter=lambda speaker, date: speaker in ALL_CNB,
        active_members=list(ALL_CNB),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_cnb_filtered_report()
