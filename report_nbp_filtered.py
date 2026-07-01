"""NBP (Narodowy Bank Polski) filtered sentiment report. Run: python report_nbp_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_nbp_filtered_report() -> None:
    from meetings import get_meetings
    from scraper_nbp import ALL_NBP

    generate_filtered_report(
        bank_db_name="NBP",
        bank_label="Narodowy Bank Polski",
        accent_color="#DC143C",  # Polish flag red
        output_path=Path("report_nbp_filtered.html"),
        meetings=get_meetings("NBP"),
        member_filter=lambda speaker, date: speaker in ALL_NBP,
        active_members=list(ALL_NBP),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_nbp_filtered_report()
