"""BNR (Banca Națională a României) filtered sentiment report. Run: python report_bnr_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_bnr_filtered_report() -> None:
    from meetings import get_meetings
    from members_seed import is_member, current_members

    generate_filtered_report(
        bank_db_name="BNR",
        bank_label="Banca Națională a României",
        accent_color="#002B7F",  # Romanian flag blue
        output_path=Path("report_bnr_filtered.html"),
        meetings=get_meetings("BNR"),
        member_filter=lambda speaker, date: is_member("bnr", speaker, date),
        active_members=current_members("bnr"),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_bnr_filtered_report()
