import io
import sqlite3
from pathlib import Path

import requests
import pandas as pd

ECB_CSV_URL = (
    "https://www.ecb.europa.eu/press/key/shared/data/all_ECB_speeches.csv"
    "?b817ea0464300d26845bc915c07dfb17"
)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
DB_PATH = Path("data/speeches.db")

def _load_exec_board() -> set[str]:
    import json
    from pathlib import Path as _Path
    p = _Path("data/members.json")
    if p.exists():
        return set(json.loads(p.read_text(encoding="utf-8")).get("ecb_exec_board", []))
    return {
        "Christine Lagarde", "Luis de Guindos", "Philip R. Lane",
        "Isabel Schnabel", "Frank Elderson", "Piero Cipollone",
    }

EXEC_BOARD = _load_exec_board()

# All exec board members active at any point in the last 5 years (for historical backfill)
ALL_ECB_BOARD_5Y = EXEC_BOARD | {
    "Fabio Panetta",       # 2020–2023
}

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS speeches (
        url           TEXT PRIMARY KEY,
        date          TEXT,
        speaker       TEXT,
        title         TEXT,
        score         INTEGER,
        justification TEXT,
        rated_at      TEXT,
        body          TEXT,
        central_bank  TEXT,
        country       TEXT
    )
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(_CREATE_TABLE)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    for col in ("body", "central_bank", "country"):
        if col not in cols:
            conn.execute(f"ALTER TABLE speeches ADD COLUMN {col} TEXT")
    conn.commit()
    return conn


def ecb_url_key(date: str, title: str) -> str:
    return f"ecb::{date}::{title[:100]}"


def fetch_ecb_csv() -> pd.DataFrame:
    r = requests.get(ECB_CSV_URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.content.decode("utf-8", errors="replace")), sep="|")
    df["speakers"] = df["speakers"].fillna("Unknown").astype(str)
    df["title"] = df["title"].fillna("").astype(str)
    df["subtitle"] = df["subtitle"].fillna("").astype(str)
    df["contents"] = df["contents"].fillna("").astype(str)
    df["date"] = df["date"].fillna("").astype(str)
    return df


def store_all_ecb(df: pd.DataFrame) -> list[dict]:
    """Store all ECB speeches (unrated). Returns new 2026 Exec Board rows to rate."""
    conn = _conn()
    existing = {
        row[0]
        for row in conn.execute("SELECT url FROM speeches WHERE central_bank='ECB'")
    }

    new_2026 = []
    for _, row in df.iterrows():
        key = ecb_url_key(row["date"], row["title"])
        if key in existing:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO speeches "
            "(url, date, speaker, title, body, central_bank, country) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, row["date"], row["speakers"], row["title"],
             row["contents"], "ECB", "EUR"),
        )
        if row["date"] >= "2026-01-01" and row["speakers"] in EXEC_BOARD:
            new_2026.append({
                "url":     key,
                "date":    row["date"],
                "speaker": row["speakers"],
                "title":   row["title"],
                "body":    row["contents"],
            })

    conn.commit()
    conn.close()
    return new_2026


def save_rating(url_key: str, score: int, justification: str, rated_at: str) -> None:
    conn = _conn()
    conn.execute(
        "UPDATE speeches SET score=?, justification=?, rated_at=? WHERE url=?",
        (score, justification, rated_at, url_key),
    )
    conn.commit()
    conn.close()


def get_unrated_ecb_historical(cutoff: str) -> list[dict]:
    """Return all unrated speeches from ALL_ECB_BOARD_5Y on or after cutoff date."""
    conn = _conn()
    rows = conn.execute(
        "SELECT url, date, speaker, title, body FROM speeches "
        "WHERE central_bank='ECB' AND score IS NULL AND date >= ?",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [
        {"url": r[0], "date": r[1], "speaker": r[2], "title": r[3], "body": r[4]}
        for r in rows
        if r[2] in ALL_ECB_BOARD_5Y
    ]


def get_new_ecb_2026() -> list[dict]:
    """Download CSV, store all, return unrated 2026 Exec Board speeches."""
    print("Downloading ECB speeches CSV ...")
    df = fetch_ecb_csv()
    print(f"  {len(df)} total ECB speeches in CSV")
    new = store_all_ecb(df)
    print(f"  {len(new)} new 2026 Executive Board speeches to rate")
    return new
