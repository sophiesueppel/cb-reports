"""BCB filtered sentiment report. Run: python report_bcb_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_bcb_filtered_report() -> None:
    from meetings import get_meetings
    from members_seed import is_member, current_members

    generate_filtered_report(
        bank_db_name="BCB",
        bank_label="Banco Central do Brasil (BCB)",
        accent_color="#009B3A",  # Brazilian green
        output_path=Path("report_bcb_filtered.html"),
        meetings=get_meetings("BCB"),
        member_filter=lambda speaker, date: is_member("bcb", speaker, date),
        active_members=current_members("bcb"),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_bcb_filtered_report()
