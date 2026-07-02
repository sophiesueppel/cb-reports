"""
Staleness monitor — the tracker's smoke detector.

A daily tracker is only trustworthy if it shouts when it STOPS getting new data.
This checks each bank's freshness across the data types that matter to a macro
desk and returns alerts, so a silent scraper failure (e.g. CBRT rate decisions
frozen since June 2025) is caught in days, not months — never hidden behind a
stale hardcoded seed.

Two checks per bank:
  • DECISIONS — most recent *actual* rate decision. If older than DECISION_STALE_DAYS
    a meeting has almost certainly happened that we failed to record → CRITICAL.
    Also counts past meeting dates still marked 'upcoming' (decisions we missed).
  • SPEECHES — most recent rated speech. If older than SPEECH_STALE_DAYS the speech
    scraper for that bank has probably broken → WARN (some banks are genuinely quiet,
    hence lower severity).

Importable: run_staleness_check() -> list[alert dicts]. CLI prints a table and exits
non-zero if any CRITICAL alert (so cron / the daily pipeline can act on it).

Run:  python check_staleness.py
"""
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))

DECISION_STALE_DAYS = 60   # every tracked bank meets at least ~every 6-8 weeks
SPEECH_STALE_DAYS = 45     # generous; below this even quiet banks usually speak


def _age_days(iso: str, today: str) -> int | None:
    if not iso:
        return None
    return (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(iso, "%Y-%m-%d")).days


def run_staleness_check(db_path=DB_PATH, decision_days=DECISION_STALE_DAYS,
                        speech_days=SPEECH_STALE_DAYS) -> list:
    """Return a list of alert dicts: {severity, bank, kind, detail}."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    today = date.today().isoformat()
    has_meetings = bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='meetings'").fetchone())

    banks = [r[0] for r in conn.execute(
        "SELECT DISTINCT central_bank FROM speeches WHERE central_bank IS NOT NULL ORDER BY 1")]

    alerts = []
    for b in banks:
        # --- Speeches ---
        newest = conn.execute(
            "SELECT MAX(date) FROM speeches WHERE central_bank=? AND score IS NOT NULL", (b,)
        ).fetchone()[0]
        sage = _age_days(newest, today)
        if sage is not None and sage > speech_days:
            alerts.append({"severity": "WARN", "bank": b, "kind": "speeches",
                           "detail": f"newest rated speech is {sage}d old ({newest}) — scraper may be stalled"})

        # --- Rate decisions ---
        if has_meetings:
            last_dec = conn.execute(
                "SELECT MAX(date) FROM meetings WHERE bank=? AND decision!='upcoming'", (b,)
            ).fetchone()[0]
            dage = _age_days(last_dec, today)
            missed = conn.execute(
                "SELECT COUNT(*), MIN(date) FROM meetings WHERE bank=? AND decision='upcoming' AND date<?",
                (b, today)).fetchone()
            n_missed, oldest_missed = missed[0], missed[1]
            if dage is not None and dage > decision_days:
                alerts.append({"severity": "CRITICAL", "bank": b, "kind": "decisions",
                               "detail": f"last recorded rate decision is {dage}d old ({last_dec}); "
                                         f"{n_missed} past meeting(s) unrecorded (since {oldest_missed})"})
            elif n_missed > 0:
                alerts.append({"severity": "WARN", "bank": b, "kind": "decisions",
                               "detail": f"{n_missed} past meeting(s) still marked 'upcoming' "
                                         f"(oldest {oldest_missed}); latest recorded {last_dec}"})
    conn.close()
    return alerts


def _summary_table(db_path=DB_PATH) -> str:
    conn = sqlite3.connect(str(db_path), timeout=30)
    today = date.today().isoformat()
    has_m = bool(conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meetings'").fetchone())
    banks = [r[0] for r in conn.execute("SELECT DISTINCT central_bank FROM speeches ORDER BY 1")]
    lines = [f"{'bank':16} {'newest speech':13} {'age':>4} | {'last decision':13} {'age':>4} {'missed':>7}"]
    for b in banks:
        ns = conn.execute("SELECT MAX(date) FROM speeches WHERE central_bank=? AND score IS NOT NULL", (b,)).fetchone()[0]
        ld = conn.execute("SELECT MAX(date) FROM meetings WHERE bank=? AND decision!='upcoming'", (b,)).fetchone()[0] if has_m else None
        mi = conn.execute("SELECT COUNT(*) FROM meetings WHERE bank=? AND decision='upcoming' AND date<?", (b, today)).fetchone()[0] if has_m else 0
        lines.append(f"{b:16} {str(ns):13} {str(_age_days(ns,today)):>4} | {str(ld):13} {str(_age_days(ld,today)):>4} {mi:>7}")
    conn.close()
    return "\n".join(lines)


def main():
    print(_summary_table())
    print()
    alerts = run_staleness_check()
    crit = [a for a in alerts if a["severity"] == "CRITICAL"]
    warn = [a for a in alerts if a["severity"] == "WARN"]
    if not alerts:
        print("OK — all banks fresh.")
        return
    for a in crit + warn:
        print(f"  [{a['severity']:8}] {a['bank']} / {a['kind']}: {a['detail']}")
    print(f"\n{len(crit)} critical, {len(warn)} warning.")
    if crit:
        sys.exit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
