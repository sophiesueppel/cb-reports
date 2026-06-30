"""ECB filtered sentiment report. Run: python report_ecb_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_ecb_filtered_report() -> None:
    from meetings import ECB_MEETINGS
    from membership import was_member
    from scraper_ecb import EXEC_BOARD

    generate_filtered_report(
        bank_db_name="ECB",
        bank_label="European Central Bank",
        accent_color="#003087",
        output_path=Path("report_ecb_filtered.html"),
        meetings=ECB_MEETINGS,
        member_filter=lambda speaker, date: was_member("ecb", speaker, date),
        active_members=list(EXEC_BOARD),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_ecb_filtered_report()
