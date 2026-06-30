"""BCB filtered sentiment report. Run: python report_bcb_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_bcb_filtered_report() -> None:
    from meetings import COPOM_MEETINGS
    from scraper_bcb import ALL_COPOM

    generate_filtered_report(
        bank_db_name="BCB",
        bank_label="Banco Central do Brasil (BCB)",
        accent_color="#009B3A",  # Brazilian green
        output_path=Path("report_bcb_filtered.html"),
        meetings=COPOM_MEETINGS,
        member_filter=lambda speaker, date: speaker in ALL_COPOM,
        active_members=list(ALL_COPOM),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_bcb_filtered_report()
