"""
Backfill translations for all non-English speeches in the database.

Pass 1 — language detection fix:
  For speeches stored with language='cs' (CNB default bug) that are actually
  English, update the language column to 'en'. No translation needed.

Pass 2 — translation:
  For speeches with language != 'en' and body_en IS NULL, translate body to
  English using the dedicated translation module and store in body_en.

Options:
  --bank      Limit to one bank (e.g. --bank=CNB)
  --dry-run   Print what would happen without writing to DB
  --fix-lang  Only run Pass 1 (language detection fix), skip translation
  --skip-fix  Skip Pass 1, only run translation
"""

import os
import sqlite3
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from translator import translate_speech, detect_language, translate_title

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def fix_language_tags(bank: str = None, dry_run: bool = False) -> int:
    """
    Pass 1: Detect/fix language tags.
    - Speeches tagged 'cs' that are actually English → re-tag 'en'
    - Speeches with language IS NULL → detect and tag appropriately
    Returns count of rows updated.
    """
    conn = _conn()
    updated = 0

    # Sub-pass A: re-detect 'cs'-tagged speeches (CNB bug)
    where_cs = "language='cs' AND body IS NOT NULL AND LENGTH(body) > 200"
    params_cs = []
    if bank:
        where_cs += " AND central_bank=?"
        params_cs.append(bank)

    rows_cs = conn.execute(
        f"SELECT url, title, body FROM speeches WHERE {where_cs}", params_cs
    ).fetchall()
    print(f"Pass 1a — Re-detect 'cs'-tagged speeches: {len(rows_cs)} to check")
    for url, title, body in rows_cs:
        detected = detect_language(body or "", title or "")
        if detected == "en":
            if not dry_run:
                conn.execute("UPDATE speeches SET language='en' WHERE url=?", (url,))
            updated += 1
            if updated <= 10 or updated % 50 == 0:
                print(f"  EN detected: {(title or '')[:70]}")

    # Sub-pass B: speeches with language IS NULL — detect and tag
    where_null = "language IS NULL AND body IS NOT NULL AND LENGTH(body) > 200"
    params_null = []
    if bank:
        where_null += " AND central_bank=?"
        params_null.append(bank)

    rows_null = conn.execute(
        f"SELECT url, title, body FROM speeches WHERE {where_null}", params_null
    ).fetchall()
    print(f"Pass 1b — Detect language for NULL-tagged speeches: {len(rows_null)} to check")
    null_fixed = 0
    for url, title, body in rows_null:
        detected = detect_language(body or "", title or "")
        if not dry_run:
            conn.execute("UPDATE speeches SET language=? WHERE url=?", (detected, url))
        null_fixed += 1
        if null_fixed <= 5 or null_fixed % 100 == 0:
            print(f"  [{detected}] {(title or '')[:70]}")
    updated += null_fixed

    if not dry_run:
        conn.commit()
    conn.close()
    print(f"  → {updated} speeches language-tagged{' (dry run)' if dry_run else ''}")
    return updated


def backfill_translations(bank: str = None, dry_run: bool = False) -> int:
    """
    Pass 2: Translate all non-English speeches with no body_en yet.
    Returns count of translations stored.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")

    conn = _conn()

    where = "language != 'en' AND language IS NOT NULL AND body_en IS NULL AND body IS NOT NULL AND LENGTH(body) > 200"
    params = []
    if bank:
        where += " AND central_bank=?"
        params.append(bank)

    rows = conn.execute(
        f"SELECT url, central_bank, date, speaker, title, body, language FROM speeches WHERE {where} ORDER BY date DESC",
        params,
    ).fetchall()

    print(f"\nPass 2 — Translation: {len(rows)} non-English speeches to translate")
    if not rows:
        print("  Nothing to do.")
        conn.close()
        return 0

    done, errors = 0, 0
    for i, (url, cb, date, speaker, title, body, lang) in enumerate(rows, 1):
        label = f"[{i}/{len(rows)}] {cb} | {date} | {(title or '')[:50]}"
        if dry_run:
            print(f"  DRY RUN {label} [{lang}]")
            continue
        try:
            body_en = translate_speech(body, lang, title=title or "", speaker=speaker or "")
            if body_en and body_en.strip():
                conn.execute("UPDATE speeches SET body_en=? WHERE url=?", (body_en, url))
                conn.commit()
                done += 1
                print(f"  OK  {label} [{lang}] → {len(body_en):,} chars EN")
            else:
                print(f"  EMPTY {label}")
                errors += 1
        except Exception as e:
            print(f"  ERR {label}: {e}")
            errors += 1
        time.sleep(0.4)

    conn.close()
    print(f"\nDone. {done} translated, {errors} errors.")
    return done


def backfill_title_translations(bank: str = None, dry_run: bool = False) -> int:
    """
    Pass 3: Add title_en column (if missing) and translate all non-English titles.
    Only translates titles where language != 'en' and title_en IS NULL.
    Returns count of titles translated.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")

    conn = _conn()

    # Add title_en column if not present
    cols = [r[1] for r in conn.execute("PRAGMA table_info(speeches)").fetchall()]
    if "title_en" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN title_en TEXT")
        conn.commit()
        print("Added title_en column to speeches table.")

    where = "language != 'en' AND language IS NOT NULL AND title_en IS NULL AND title IS NOT NULL AND title != ''"
    params = []
    if bank:
        where += " AND central_bank=?"
        params.append(bank)

    rows = conn.execute(
        f"SELECT url, central_bank, title, language FROM speeches WHERE {where} ORDER BY central_bank, date DESC",
        params,
    ).fetchall()

    print(f"\nPass 3 — Title translation: {len(rows)} non-English titles to translate")
    if not rows:
        print("  Nothing to do.")
        conn.close()
        return 0

    done, errors = 0, 0
    for i, (url, cb, title, lang) in enumerate(rows, 1):
        if dry_run:
            print(f"  DRY RUN [{i}/{len(rows)}] {cb} | {lang} | {title[:60]}")
            continue
        try:
            title_en = translate_title(title, lang)
            if title_en and title_en.strip():
                conn.execute("UPDATE speeches SET title_en=? WHERE url=?", (title_en, url))
                if i % 20 == 0:
                    conn.commit()
                done += 1
                if done <= 5 or done % 50 == 0:
                    print(f"  [{i}/{len(rows)}] {cb} | {title[:45]} → {title_en[:45]}")
            else:
                errors += 1
        except Exception as e:
            print(f"  ERR [{i}/{len(rows)}]: {e}")
            errors += 1
        time.sleep(0.15)

    conn.commit()
    conn.close()
    print(f"\nDone. {done} titles translated, {errors} errors.")
    return done


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    fix_only = "--fix-lang" in sys.argv
    skip_fix = "--skip-fix" in sys.argv
    titles_only = "--titles-only" in sys.argv

    bank = None
    for arg in sys.argv[1:]:
        if arg.startswith("--bank="):
            bank = arg.split("=", 1)[1]

    label = f"{'[DRY RUN] ' if dry_run else ''}{'bank=' + bank if bank else 'all banks'}"
    print(f"=== backfill_translations.py — {label} ===\n")

    if titles_only:
        backfill_title_translations(bank=bank, dry_run=dry_run)
    else:
        if not skip_fix:
            fix_language_tags(bank=bank, dry_run=dry_run)

        if not fix_only:
            backfill_translations(bank=bank, dry_run=dry_run)

        backfill_title_translations(bank=bank, dry_run=dry_run)
