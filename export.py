"""Export speeches database to a compact JSON file for LLM use (no body text)."""
import json
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/speeches.db")
OUT_PATH = Path("data/speeches_export.json")


def export() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT central_bank, country, date, speaker, title, score, justification, url
        FROM speeches
        ORDER BY date DESC
    """).fetchall()
    conn.close()

    records = [dict(r) for r in rows]

    output = {
        "exported_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_speeches": len(records),
        "schema": {
            "central_bank": "Name of the central bank",
            "country":      "Country of the central bank",
            "date":         "Speech date (YYYY-MM-DD)",
            "speaker":      "Full name and title of the speaker",
            "title":        "Title of the speech",
            "score":        "Hawkishness score 1-10 (1=most dovish, 10=most hawkish)",
            "justification":"GPT-4.1 explanation of the score",
            "url":          "Source URL",
        },
        "speeches": records,
    }

    OUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(records)} speeches to {OUT_PATH.resolve()}")
    print(f"File size: {OUT_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    export()
