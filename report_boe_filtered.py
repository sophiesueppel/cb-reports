"""BoE filtered sentiment report. Run: python report_boe_filtered.py"""
import sys
from pathlib import Path
from report_filtered_base import generate_filtered_report


def generate_boe_filtered_report() -> None:
    from meetings import BOE_MEETINGS
    from scraper_boe import was_mpc_member, MPC_MEMBERS

    generate_filtered_report(
        bank_db_name="Bank of England",
        bank_label="Bank of England",
        accent_color="#C8102E",
        output_path=Path("report_boe_filtered.html"),
        meetings=BOE_MEETINGS,
        member_filter=lambda speaker, date: was_mpc_member(speaker, date),
        active_members=list(MPC_MEMBERS),
    )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_boe_filtered_report()
