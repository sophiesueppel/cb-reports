"""SQLite-backed store for central-bank rate-decision data.

Owns the `meetings` table. Meeting outcomes used to live only as hand-typed lists
in meetings.py; that data is now seeded into this table and refreshed from official
sources on the daily run (see meetings_extractor.py + main.refresh_meetings).

The `meetings.py` lists remain as the seed/offline fallback. Consumers read through
`meetings.get_meetings(bank)`, which prefers this table.

Meeting dict shape returned to consumers (matches the old meetings.py entries):
    {"date": "YYYY-MM-DD", "decision": "hike|cut|hold|upcoming",
     "rate": "...", "label": "...", "note": "..."}
where rate/label/note are only present when non-empty.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))

# Canonical bank name -> the list variable exported by meetings.py (used for seeding
# and fallback). These bank names are the same ones rater._rate_at_date and the report
# generators pass in.
BANK_VARS = {
    "Federal Reserve": "FED_MEETINGS",
    "ECB":             "ECB_MEETINGS",
    "Bank of England": "BOE_MEETINGS",
    "Bank of Japan":   "BOJ_MEETINGS",
    "BCB":             "COPOM_MEETINGS",
    "Riksbank":        "RIKSBANK_MEETINGS",
    "SARB":            "SARB_MEETINGS",
    "CNB":             "CNB_MEETINGS",
    "NBP":             "NBP_MEETINGS",
    "BNR":             "BNR_MEETINGS",
    "CBRT":            "CBRT_MEETINGS",
}

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS meetings (
        bank        TEXT NOT NULL,
        date        TEXT NOT NULL,
        decision    TEXT NOT NULL,
        rate        TEXT,
        bp_change   INTEGER,
        vote        TEXT,
        label       TEXT,
        note        TEXT,
        source      TEXT,
        source_url  TEXT,
        raw_extract TEXT,
        locked      INTEGER DEFAULT 0,
        checked_at  TEXT,
        updated_at  TEXT,
        PRIMARY KEY (bank, date)
    )
"""

# Columns that make up the consumer-facing dict (everything else is provenance).
_PROJECT_OPTIONAL = ("rate", "label", "note")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(_CREATE_TABLE)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_meetings_bank_date ON meetings(bank, date)"
    )
    conn.commit()
    return conn


def upsert_meeting(
    bank: str,
    date: str,
    decision: str,
    *,
    rate: str | None = None,
    bp_change: int | None = None,
    vote: str | None = None,
    label: str | None = None,
    note: str | None = None,
    source: str = "llm",
    source_url: str | None = None,
    raw_extract=None,
) -> str:
    """Insert or reconcile one meeting row. Returns one of:
    'inserted' | 'updated' | 'skipped-locked' | 'unchanged'.

    Reconcile rules:
      - no existing row            -> INSERT
      - existing row is locked=1   -> skip (only touch checked_at)  -> 'skipped-locked'
      - values differ              -> UPDATE changed fields, log old->new -> 'updated'
      - identical                  -> touch checked_at only          -> 'unchanged'
    Rows are never deleted; an 'upcoming' row that becomes decided is updated in place.
    """
    raw_json = json.dumps(raw_extract, ensure_ascii=False) if raw_extract is not None else None
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT decision, rate, bp_change, vote, label, note, locked "
            "FROM meetings WHERE bank=? AND date=?",
            (bank, date),
        ).fetchone()

        if row is None:
            conn.execute(
                "INSERT INTO meetings "
                "(bank, date, decision, rate, bp_change, vote, label, note, "
                " source, source_url, raw_extract, locked, checked_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
                (bank, date, decision, rate, bp_change, vote, label, note,
                 source, source_url, raw_json, _now(), _now()),
            )
            conn.commit()
            return "inserted"

        old_decision, old_rate, old_bp, old_vote, old_label, old_note, locked = row

        if locked:
            conn.execute(
                "UPDATE meetings SET checked_at=? WHERE bank=? AND date=?",
                (_now(), bank, date),
            )
            conn.commit()
            return "skipped-locked"

        new_vals = (decision, rate, bp_change, vote, label, note)
        old_vals = (old_decision, old_rate, old_bp, old_vote, old_label, old_note)
        if new_vals == old_vals:
            conn.execute(
                "UPDATE meetings SET checked_at=? WHERE bank=? AND date=?",
                (_now(), bank, date),
            )
            conn.commit()
            return "unchanged"

        print(f"  [meetings] {bank} {date}: "
              f"{old_decision}/{old_rate} -> {decision}/{rate}")
        conn.execute(
            "UPDATE meetings SET decision=?, rate=?, bp_change=?, vote=?, label=?, "
            "note=?, source=?, source_url=?, raw_extract=?, checked_at=?, updated_at=? "
            "WHERE bank=? AND date=?",
            (decision, rate, bp_change, vote, label, note, source, source_url,
             raw_json, _now(), _now(), bank, date),
        )
        conn.commit()
        return "updated"
    finally:
        conn.close()


def load_bank_meetings(bank: str) -> list[dict]:
    """Return one bank's meetings as the consumer dict list, ordered by date."""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT date, decision, rate, label, note FROM meetings "
            "WHERE bank=? ORDER BY date",
            (bank,),
        ).fetchall()
    finally:
        conn.close()

    out: list[dict] = []
    for date, decision, rate, label, note in rows:
        d = {"date": date, "decision": decision}
        if rate:
            d["rate"] = rate
        if label:
            d["label"] = label
        if note:
            d["note"] = note
        out.append(d)
    return out


def load_all_meetings() -> dict[str, list[dict]]:
    """Return {bank: [meeting dict, ...]} for every bank that has rows."""
    return {bank: load_bank_meetings(bank) for bank in BANK_VARS}


def latest_decided_date(bank: str) -> str | None:
    """Most recent date for which this bank has a DECIDED (non-upcoming) meeting.

    refresh_meetings uses this to append only genuinely new decisions and avoid
    re-touching historical rows (whose seed dates can differ by a day from the
    effective dates on official pages, which would otherwise duplicate vlines)."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT MAX(date) FROM meetings WHERE bank=? AND decision != 'upcoming'",
            (bank,),
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row and row[0] else None


def count_meetings(bank: str | None = None) -> int:
    conn = _conn()
    try:
        if bank is None:
            return conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM meetings WHERE bank=?", (bank,)
        ).fetchone()[0]
    finally:
        conn.close()


def lock_meeting(bank: str, date: str, locked: bool = True) -> None:
    """Mark a meeting as manually corrected so re-verification won't clobber it."""
    conn = _conn()
    try:
        conn.execute(
            "UPDATE meetings SET locked=? WHERE bank=? AND date=?",
            (1 if locked else 0, bank, date),
        )
        conn.commit()
    finally:
        conn.close()
