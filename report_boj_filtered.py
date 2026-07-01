"""BoJ filtered sentiment report. Run: python report_boj_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_boj_filtered_report() -> None:
    from meetings import get_meetings
    from scraper_boj import BOJ_POLICY_BOARD

    generate_filtered_report(
        bank_db_name="Bank of Japan",
        bank_label="Bank of Japan",
        accent_color="#BC002D",
        output_path=Path("report_boj_filtered.html"),
        meetings=get_meetings("Bank of Japan"),
        member_filter=None,
        active_members=list(BOJ_POLICY_BOARD),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_boj_filtered_report()
