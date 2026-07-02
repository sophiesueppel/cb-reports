"""Riksbank filtered sentiment report. Run: python report_riksbank_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_riksbank_filtered_report() -> None:
    from meetings import get_meetings
    from members_seed import is_member, current_members

    generate_filtered_report(
        bank_db_name="Riksbank",
        bank_label="Sveriges Riksbank",
        accent_color="#006AA7",  # Swedish blue
        output_path=Path("report_riksbank_filtered.html"),
        meetings=get_meetings("Riksbank"),
        member_filter=lambda speaker, date: is_member("riksbank", speaker, date),
        active_members=current_members("riksbank"),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_riksbank_filtered_report()
