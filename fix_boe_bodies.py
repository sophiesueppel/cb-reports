"""
Re-scrape BoE speeches whose body text is too short (<500 chars) — these were
stored with only the HTML summary instead of the full transcript.

Updates the body in place. For speeches that were already rated on bad data,
clears the score so they get re-rated on the next run.
"""
import sqlite3
import sys
import time
from pathlib import Path

from scraper_boe import scrape_speech, _session, DB_PATH

MIN_BODY = 500
RATED_REQUEUE_THRESHOLD = 2000  # if rated AND body < this, clear score for re-rating


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT url, speaker, date, length(body), score "
        "FROM speeches "
        "WHERE central_bank='Bank of England' AND length(body) < ? "
        "ORDER BY date DESC",
        (MIN_BODY,),
    ).fetchall()

    print(f"Found {len(rows)} BoE speeches with body < {MIN_BODY} chars")
    rated_short = [(u, s, d, l, sc) for u, s, d, l, sc in rows if sc is not None]
    print(f"  Of those, {len(rated_short)} were already rated (scores will be cleared after re-scrape)")
    print()

    session = _session()
    updated = 0
    cleared = 0
    failed = 0

    for i, (url, speaker, date, old_len, score) in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {date} | {speaker[:30]} | old len={old_len}", flush=True)
        rec = scrape_speech(url, session)

        if rec and len(rec.get("body", "")) >= MIN_BODY:
            new_body = rec["body"]
            if score is not None and old_len < RATED_REQUEUE_THRESHOLD:
                conn.execute(
                    "UPDATE speeches SET body=?, score=NULL, justification=NULL, rated_at=NULL WHERE url=?",
                    (new_body, url),
                )
                print(f"  Updated ({len(new_body)} chars) + cleared score for re-rating", flush=True)
                cleared += 1
            else:
                conn.execute("UPDATE speeches SET body=? WHERE url=?", (new_body, url))
                print(f"  Updated ({len(new_body)} chars)", flush=True)
            updated += 1
        else:
            new_len = len(rec.get("body", "")) if rec else 0
            print(f"  SKIP — still short ({new_len} chars) or no PDF found", flush=True)
            failed += 1

        if i % 20 == 0:
            conn.commit()
            print(f"  --- committed ({updated} updated so far) ---", flush=True)
        time.sleep(0.5)

    conn.commit()
    conn.close()
    print(f"\nDone. {updated} updated, {cleared} cleared for re-rating, {failed} still short/failed.")


if __name__ == "__main__":
    main()
