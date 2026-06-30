"""Riksbank filtered sentiment report. Run: python report_riksbank_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_riksbank_filtered_report() -> None:
    from meetings import RIKSBANK_MEETINGS
    from scraper_riksbank import ALL_RIKSBANK

    generate_filtered_report(
        bank_db_name="Riksbank",
        bank_label="Sveriges Riksbank",
        accent_color="#006AA7",  # Swedish blue
        output_path=Path("report_riksbank_filtered.html"),
        meetings=RIKSBANK_MEETINGS,
        member_filter=lambda speaker, date: speaker in ALL_RIKSBANK,
        active_members=list(ALL_RIKSBANK),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_riksbank_filtered_report()
