"""CBRT (Central Bank of the Republic of Turkey) filtered sentiment report. Run: python report_cbrt_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_cbrt_filtered_report() -> None:
    from meetings import get_meetings
    from scraper_cbrt import ALL_CBRT

    generate_filtered_report(
        bank_db_name="CBRT",
        bank_label="Central Bank of Turkey",
        accent_color="#E30A17",  # Turkish flag red
        output_path=Path("report_cbrt_filtered.html"),
        meetings=get_meetings("CBRT"),
        member_filter=lambda speaker, date: speaker in ALL_CBRT,
        active_members=list(ALL_CBRT),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_cbrt_filtered_report()
