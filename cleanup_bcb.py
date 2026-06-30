"""
BCB speech cleanup: deduplicate PT/EN pairs, translate Portuguese bodies to English,
rate any unrated speeches.

Rules:
  - True duplicates (same date + speaker, body lengths within 15%):
      keep the longer body (translated to EN if needed), use its score, delete the other
  - False duplicates / PT-only speeches:
      translate body in place, keep existing score
  - Exact EN duplicates: delete one
  - After all PT bodies are translated: rate any still-unrated speeches

Usage:
  python cleanup_bcb.py              # full run
  python cleanup_bcb.py --dry-run   # preview only, no DB writes
"""

import os
import re
import sys
import time
import json
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env")

DB_PATH = Path("data/speeches.db")
DRY_RUN = "--dry-run" in sys.argv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def detect_lang(body: str) -> str:
    """Return 'PT' or 'EN' based on word frequency heuristic."""
    snippet = (body or "")[:400]
    pt = len(re.findall(r"\b(de|do|da|em|para|que|com|por|se|no|na|os|as)\b", snippet))
    en = len(re.findall(r"\b(the|of|and|to|in|that|is|for|on|with|we|are)\b", snippet, re.I))
    return "PT" if pt > en else "EN"


def translate_body(client: OpenAI, body: str) -> str:
    """Translate Portuguese body text to English using GPT-4.1-mini."""
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional translator. Translate the following Brazilian Portuguese "
                    "central bank speech text to English. Preserve all formatting, paragraph breaks, "
                    "and technical terminology. Output only the translated text, nothing else."
                ),
            },
            {"role": "user", "content": body},
        ],
    )
    return resp.choices[0].message.content.strip()


def rate_speech_simple(client: OpenAI, title: str, speaker: str, date: str, body: str) -> dict:
    """Rate a speech using the rater module."""
    from rater import rate_speech
    return rate_speech(title=title, speaker=speaker, date=date, text=body, bank="BCB", db_path=str(DB_PATH))


def run():
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Ensure body_language column exists
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    has_lang_col = "body_language" in cols
    if not has_lang_col and not DRY_RUN:
        conn.execute("ALTER TABLE speeches ADD COLUMN body_language TEXT")
        conn.commit()
        has_lang_col = True
        print("Added body_language column to DB.")

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    body_lang_sel = "body_language" if has_lang_col else "NULL as body_language"
    all_bcb = conn.execute(
        f"SELECT url, date, speaker, title, score, justification, body, {body_lang_sel} "
        "FROM speeches WHERE central_bank='BCB' ORDER BY date, speaker"
    ).fetchall()

    # -------------------------------------------------------------------------
    # Phase 1: Group by (date, speaker) to find duplicates
    # -------------------------------------------------------------------------
    from collections import defaultdict
    groups = defaultdict(list)
    for row in all_bcb:
        key = (row["date"], row["speaker"])
        groups[key].append(dict(row))

    to_delete = set()      # urls to delete
    to_translate = []      # (url, body, title) speeches whose body needs translating
    to_rerate = []         # (url, title, speaker, date, body) speeches to re-rate after body update

    print("\n=== PHASE 1: DEDUPLICATION ===")
    for (date, speaker), speeches in groups.items():
        if len(speeches) == 1:
            continue

        # Detect language for each
        for s in speeches:
            s["_lang"] = detect_lang(s["body"] or "")
            s["_len"] = len(s["body"] or "")

        langs = [s["_lang"] for s in speeches]

        # Exact EN duplicates (identical body length)
        en_speeches = [s for s in speeches if s["_lang"] == "EN"]
        if len(en_speeches) > 1:
            seen_lens = {}
            for s in en_speeches:
                if s["_len"] in seen_lens:
                    # Exact duplicate — delete the second one
                    print(f"  EXACT DUP  {date} | {speaker[:35]} — deleting duplicate EN (url: {s['url'][-60:]})")
                    to_delete.add(s["url"])
                else:
                    seen_lens[s["_len"]] = s["url"]

        pt_speeches = [s for s in speeches if s["_lang"] == "PT" and s["url"] not in to_delete]
        en_speeches = [s for s in speeches if s["_lang"] == "EN" and s["url"] not in to_delete]

        if not pt_speeches:
            continue

        for pt in pt_speeches:
            # Find a matching EN speech (within 15% body length)
            match = None
            for en in en_speeches:
                if en["url"] in to_delete:
                    continue
                ratio = pt["_len"] / en["_len"] if en["_len"] else 0
                if 0.85 <= ratio <= 1.15:
                    match = en
                    break

            if match:
                # True duplicate — keep the longer one's content and score
                if pt["_len"] > match["_len"]:
                    # PT has more content: translate it, replace EN body + score, delete PT
                    print(f"  TRUE DUP (PT longer)  {date} | {speaker[:35]}")
                    print(f"    PT len={pt['_len']}, EN len={match['_len']} — will translate PT, update EN row, delete PT")
                    to_translate.append({
                        "url": pt["url"],
                        "update_url": match["url"],
                        "body": pt["body"],
                        "title": pt["title"],
                        "speaker": pt["speaker"],
                        "date": pt["date"],
                        "score": pt["score"],
                        "justification": pt["justification"],
                        "action": "replace_en",
                    })
                    to_delete.add(pt["url"])
                else:
                    # EN has more content: just delete PT
                    print(f"  TRUE DUP (EN longer)  {date} | {speaker[:35]}")
                    print(f"    EN len={match['_len']}, PT len={pt['_len']} — deleting PT, keeping EN")
                    to_delete.add(pt["url"])
            else:
                # Different speech (no close EN match) — translate PT in place
                print(f"  PT ONLY  {date} | {speaker[:35]} | len={pt['_len']} — will translate in place")
                to_translate.append({
                    "url": pt["url"],
                    "update_url": None,
                    "body": pt["body"],
                    "title": pt["title"],
                    "speaker": pt["speaker"],
                    "date": pt["date"],
                    "score": pt["score"],
                    "justification": pt["justification"],
                    "action": "translate_in_place",
                })
                to_delete.add(pt["url"])  # Will be deleted after translation saved elsewhere

    # Also collect all remaining PT-only speeches (groups with only one PT speech)
    for (date, speaker), speeches in groups.items():
        for s in speeches:
            s["_lang"] = detect_lang(s["body"] or "")
        if all(s["_lang"] == "PT" for s in speeches) and len(speeches) == 1:
            s = speeches[0]
            if s["url"] not in to_delete:
                to_translate.append({
                    "url": s["url"],
                    "update_url": None,
                    "body": s["body"],
                    "title": s["title"],
                    "speaker": s["speaker"],
                    "date": s["date"],
                    "score": s["score"],
                    "justification": s["justification"],
                    "action": "translate_in_place",
                })

    print(f"\nSummary:")
    print(f"  Speeches to delete: {len(to_delete)}")
    print(f"  Speeches to translate: {len(to_translate)}")
    print(f"    - replace EN with longer PT content: {sum(1 for t in to_translate if t['action']=='replace_en')}")
    print(f"    - translate PT in place: {sum(1 for t in to_translate if t['action']=='translate_in_place')}")

    if DRY_RUN:
        print("\n[DRY RUN] No changes written.")
        conn.close()
        return

    # -------------------------------------------------------------------------
    # Phase 2: Translate
    # -------------------------------------------------------------------------
    print("\n=== PHASE 2: TRANSLATION ===")
    translated = 0
    errors = 0

    for i, item in enumerate(to_translate, 1):
        label = f"[{i}/{len(to_translate)}] {item['date']} | {(item['speaker'] or '')[:35]}"
        print(f"  Translating {label} ...")
        try:
            translated_body = translate_body(client, item["body"] or "")
            translated += 1

            if item["action"] == "replace_en":
                # Update the EN speech row with translated PT body + PT score
                conn.execute(
                    "UPDATE speeches SET body=?, body_language='pt_translated', score=?, justification=? WHERE url=?",
                    (translated_body, item["score"], item["justification"], item["update_url"]),
                )
                # If EN speech needs re-rating (score was based on shorter EN body), mark it
                if item["score"] is None:
                    to_rerate.append({
                        "url": item["update_url"],
                        "title": item["title"],
                        "speaker": item["speaker"],
                        "date": item["date"],
                        "body": translated_body,
                    })
            else:
                # Translate in place: update existing row
                conn.execute(
                    "UPDATE speeches SET body=?, body_language='pt_translated' WHERE url=?",
                    (translated_body, item["url"]),
                )
                # Remove from to_delete since we're updating in place, not deleting
                to_delete.discard(item["url"])

            conn.commit()
            print(f"    OK ({len(translated_body)} chars)")
        except Exception as e:
            print(f"    ERROR: {e}")
            errors += 1
            to_delete.discard(item["url"])  # Don't delete if translation failed

        time.sleep(0.3)

    print(f"\nTranslation done: {translated} translated, {errors} errors.")

    # -------------------------------------------------------------------------
    # Phase 3: Delete PT duplicates
    # -------------------------------------------------------------------------
    print(f"\n=== PHASE 3: DELETING {len(to_delete)} DUPLICATE/REPLACED PT SPEECHES ===")
    for url in to_delete:
        conn.execute("DELETE FROM speeches WHERE url=?", (url,))
    conn.commit()
    print(f"  Deleted {len(to_delete)} speeches.")

    # -------------------------------------------------------------------------
    # Phase 4: Rate unrated speeches
    # -------------------------------------------------------------------------
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body FROM speeches "
        "WHERE central_bank='BCB' AND score IS NULL AND body IS NOT NULL AND body != ''"
    ).fetchall()

    print(f"\n=== PHASE 4: RATING {len(unrated)} UNRATED BCB SPEECHES ===")
    rated = 0
    for i, row in enumerate(unrated, 1):
        url, date, speaker, title, body = row
        label = f"[{i}/{len(unrated)}] {date} | {(speaker or '')[:35]}"
        print(f"  Rating {label} ...")
        try:
            result = rate_speech_simple(client, title or "", speaker or "", date or "", body or "")
            conn.execute(
                "UPDATE speeches SET score=?, justification=? WHERE url=?",
                (result["score"], result["justification"], url),
            )
            conn.commit()
            print(f"    Score: {result['score']} — {(result['justification'] or '')[:80]}")
            rated += 1
        except Exception as e:
            print(f"    ERROR: {e}")
        time.sleep(0.3)

    # -------------------------------------------------------------------------
    # Final stats
    # -------------------------------------------------------------------------
    total = conn.execute("SELECT COUNT(*) FROM speeches WHERE central_bank='BCB'").fetchone()[0]
    pt_remaining = sum(
        1 for (body,) in conn.execute("SELECT body FROM speeches WHERE central_bank='BCB' AND body IS NOT NULL").fetchall()
        if detect_lang(body) == "PT"
    )
    print(f"\n=== DONE ===")
    print(f"  BCB speeches remaining in DB: {total}")
    print(f"  Still in Portuguese: {pt_remaining}")
    print(f"  Translated: {translated}, Deleted: {len(to_delete)}, Rated: {rated}")

    conn.close()


if __name__ == "__main__":
    print(f"BCB cleanup {'[DRY RUN] ' if DRY_RUN else ''}starting...")
    run()
