import io
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from scraper import get_latest_speech_url, get_speech, get_all_speech_urls, date_from_url
from scraper_ecb import get_new_ecb_2026, get_unrated_ecb_historical, save_rating as ecb_save_rating
from scraper_boe import get_new_boe_2026, save_rating as boe_save_rating
from scraper_boj import get_new_boj_2026, save_rating as boj_save_rating
from scraper_bcb import get_new_bcb_2026, save_rating as bcb_save_rating
from scraper_riksbank import get_new_riksbank_speeches, save_rating as riksbank_save_rating
from scraper_sarb import get_new_sarb_speeches, save_rating as sarb_save_rating
from rater import rate_speech
from report_fed_filtered import generate_fed_filtered_report
from report_ecb_filtered import generate_ecb_filtered_report
from report_boe_filtered import generate_boe_filtered_report
from report_boj_filtered import generate_boj_filtered_report
from report_bcb_filtered import generate_bcb_filtered_report
from report_riksbank_filtered import generate_riksbank_filtered_report
from report_sarb_filtered import generate_sarb_filtered_report
from report_cnb_filtered import generate_cnb_filtered_report
from report_nbp_filtered import generate_nbp_filtered_report
from report_bnr_filtered import generate_bnr_filtered_report
from report_cbrt_filtered import generate_cbrt_filtered_report
from classify_relevance_llm import run_classification
from check_members import check_all as check_members

load_dotenv(Path(__file__).parent / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))
COLUMNS = ["url", "date", "speaker", "title", "score", "justification", "rated_at"]

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


GITHUB_PAGES_BASE = "https://sophiesueppel.github.io/cb-reports"
FED_REPORT_URL = f"{GITHUB_PAGES_BASE}/report_fed_filtered.html"
ECB_REPORT_URL = f"{GITHUB_PAGES_BASE}/report_ecb_filtered.html"
BOE_REPORT_URL = f"{GITHUB_PAGES_BASE}/report_boe_filtered.html"
BOJ_REPORT_URL = f"{GITHUB_PAGES_BASE}/report_boj_filtered.html"
BCB_REPORT_URL = f"{GITHUB_PAGES_BASE}/report_bcb_filtered.html"
RIKSBANK_REPORT_URL = f"{GITHUB_PAGES_BASE}/report_riksbank_filtered.html"
SARB_REPORT_URL = f"{GITHUB_PAGES_BASE}/report_sarb_filtered.html"
CNB_REPORT_URL  = f"{GITHUB_PAGES_BASE}/report_cnb_filtered.html"
NBP_REPORT_URL  = f"{GITHUB_PAGES_BASE}/report_nbp_filtered.html"
BNR_REPORT_URL  = f"{GITHUB_PAGES_BASE}/report_bnr_filtered.html"
CBRT_REPORT_URL = f"{GITHUB_PAGES_BASE}/report_cbrt_filtered.html"

# Keep old name as alias for backward compat
REPORT_URL = FED_REPORT_URL


def slack_notify_combined(
    fed_speeches: list[dict],
    ecb_speeches: list[dict],
    boe_speeches: list[dict] = None,
    boj_speeches: list[dict] = None,
    bcb_speeches: list[dict] = None,
    riksbank_speeches: list[dict] = None,
    sarb_speeches: list[dict] = None,
    nbp_speeches: list[dict] = None,
    bnr_speeches: list[dict] = None,
    cbrt_speeches: list[dict] = None,
) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        return

    boe_speeches = boe_speeches or []
    boj_speeches = boj_speeches or []
    bcb_speeches = bcb_speeches or []
    riksbank_speeches = riksbank_speeches or []
    sarb_speeches = sarb_speeches or []
    nbp_speeches = nbp_speeches or []
    bnr_speeches = bnr_speeches or []
    cbrt_speeches = cbrt_speeches or []
    total = (len(fed_speeches) + len(ecb_speeches) + len(boe_speeches) + len(boj_speeches) +
             len(bcb_speeches) + len(riksbank_speeches) + len(sarb_speeches) +
             len(nbp_speeches) + len(bnr_speeches) + len(cbrt_speeches))
    if total == 0:
        return

    _tone = lambda s: "Off-topic" if s == 0 else "Dovish" if s <= 3 else "Neutral" if s <= 6 else "Hawkish"
    _emoji = lambda s: ":white_circle:" if s == 0 else ":large_blue_circle:" if s <= 3 else ":white_circle:" if s <= 6 else ":red_circle:"

    blocks = [{"type": "header", "text": {"type": "plain_text",
        "text": f"Central Bank Tracker — {total} new speech{'es' if total != 1 else ''} rated"}}]

    if fed_speeches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*\U0001f1fa\U0001f1f8 Federal Reserve*"}})
        for sp in fed_speeches:
            t, e = _tone(sp["score"]), _emoji(sp["score"])
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": f"{e} *{sp['score']}/10 — {t}*\n*<{sp['url']}|{sp['title']}>*\n{sp['speaker']} · {sp['date']}\n_{sp['justification']}_"}})
            blocks.append({"type": "divider"})

    if ecb_speeches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*\U0001f1ea\U0001f1fa European Central Bank*"}})
        for sp in ecb_speeches:
            t, e = _tone(sp["score"]), _emoji(sp["score"])
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": f"{e} *{sp['score']}/10 — {t}*\n*{sp['title']}*\n{sp['speaker']} · {sp['date']}\n_{sp['justification']}_"}})
            blocks.append({"type": "divider"})

    if boe_speeches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*\U0001f1ec\U0001f1e7 Bank of England*"}})
        for sp in boe_speeches:
            t, e = _tone(sp["score"]), _emoji(sp["score"])
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": f"{e} *{sp['score']}/10 — {t}*\n*<{sp['url']}|{sp['title']}>*\n{sp['speaker']} · {sp['date']}\n_{sp['justification']}_"}})
            blocks.append({"type": "divider"})

    if boj_speeches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*\U0001f1ef\U0001f1f5 Bank of Japan*"}})
        for sp in boj_speeches:
            t, e = _tone(sp["score"]), _emoji(sp["score"])
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": f"{e} *{sp['score']}/10 — {t}*\n*<{sp['url']}|{sp['title']}>*\n{sp['speaker']} · {sp['date']}\n_{sp['justification']}_"}})
            blocks.append({"type": "divider"})

    if bcb_speeches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*\U0001f1e7\U0001f1f7 Banco Central do Brasil*"}})
        for sp in bcb_speeches:
            t, e = _tone(sp["score"]), _emoji(sp["score"])
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": f"{e} *{sp['score']}/10 — {t}*\n*{sp['title']}*\n{sp['speaker']} · {sp['date']}\n_{sp['justification']}_"}})
            blocks.append({"type": "divider"})

    if riksbank_speeches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*\U0001f1f8\U0001f1ea Sveriges Riksbank*"}})
        for sp in riksbank_speeches:
            t, e = _tone(sp["score"]), _emoji(sp["score"])
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": f"{e} *{sp['score']}/10 — {t}*\n*<{sp['url']}|{sp['title']}>*\n{sp['speaker']} · {sp['date']}\n_{sp['justification']}_"}})
            blocks.append({"type": "divider"})

    if sarb_speeches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*\U0001f1ff\U0001f1e6 South African Reserve Bank*"}})
        for sp in sarb_speeches:
            t, e = _tone(sp["score"]), _emoji(sp["score"])
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": f"{e} *{sp['score']}/10 — {t}*\n*<{sp['url']}|{sp['title']}>*\n{sp['speaker']} · {sp['date']}\n_{sp['justification']}_"}})
            blocks.append({"type": "divider"})

    if nbp_speeches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*\U0001f1f5\U0001f1f1 Narodowy Bank Polski*"}})
        for sp in nbp_speeches:
            t, e = _tone(sp["score"]), _emoji(sp["score"])
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": f"{e} *{sp['score']}/10 — {t}*\n*<{sp['url']}|{sp['title']}>*\n{sp['speaker']} · {sp['date']}\n_{sp['justification']}_"}})
            blocks.append({"type": "divider"})

    if bnr_speeches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*\U0001f1f7\U0001f1f4 Banca Națională a României*"}})
        for sp in bnr_speeches:
            t, e = _tone(sp["score"]), _emoji(sp["score"])
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": f"{e} *{sp['score']}/10 — {t}*\n*<{sp['url']}|{sp['title']}>*\n{sp['speaker']} · {sp['date']}\n_{sp['justification']}_"}})
            blocks.append({"type": "divider"})

    if cbrt_speeches:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*\U0001f1f9\U0001f1f7 Central Bank of Turkey*"}})
        for sp in cbrt_speeches:
            t, e = _tone(sp["score"]), _emoji(sp["score"])
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                "text": f"{e} *{sp['score']}/10 — {t}*\n*<{sp['url']}|{sp['title']}>*\n{sp['speaker']} · {sp['date']}\n_{sp['justification']}_"}})
            blocks.append({"type": "divider"})

    buttons = [{"type": "button", "text": {"type": "plain_text", "text": "Fed Report"},
                "url": FED_REPORT_URL, "style": "primary"}]
    if ECB_REPORT_URL:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "ECB Report"},
                        "url": ECB_REPORT_URL})
    if BOE_REPORT_URL:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "BoE Report"},
                        "url": BOE_REPORT_URL})
    if BOJ_REPORT_URL:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "BoJ Report"},
                        "url": BOJ_REPORT_URL})
    if BCB_REPORT_URL:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "BCB Report"},
                        "url": BCB_REPORT_URL})
    if RIKSBANK_REPORT_URL:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "Riksbank Report"},
                        "url": RIKSBANK_REPORT_URL})
    if SARB_REPORT_URL:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "SARB Report"},
                        "url": SARB_REPORT_URL})
    if NBP_REPORT_URL:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "NBP Report"},
                        "url": NBP_REPORT_URL})
    if BNR_REPORT_URL:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "BNR Report"},
                        "url": BNR_REPORT_URL})
    if CBRT_REPORT_URL:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": "CBRT Report"},
                        "url": CBRT_REPORT_URL})
    blocks.append({"type": "actions", "elements": buttons})

    payload = json.dumps({"blocks": blocks}).encode()
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  Slack notify failed: {e}")


def slack_notify(speeches: list[dict]) -> None:
    slack_notify_combined(speeches, [])


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def save_topic_scores(url: str, topic_scores: dict | None) -> None:
    """Persist topic_scores JSON for a speech. Adds the column if missing."""
    if not topic_scores:
        return
    conn = _conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    if "topic_scores" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN topic_scores TEXT")
        conn.commit()
    conn.execute(
        "UPDATE speeches SET topic_scores=? WHERE url=?",
        (json.dumps(topic_scores), url),
    )
    conn.commit()
    conn.close()


def load_data() -> pd.DataFrame:
    conn = _conn()
    df = pd.read_sql("SELECT * FROM speeches", conn)
    conn.close()
    return df


def save_row(row: dict) -> None:
    conn = _conn()
    # Migrate: add body column if it doesn't exist yet
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    if "body" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN body TEXT")
        conn.commit()
    conn.execute(
        "INSERT OR REPLACE INTO speeches "
        "(url, date, speaker, title, score, justification, rated_at, body, central_bank, country) "
        "VALUES (:url, :date, :speaker, :title, :score, :justification, :rated_at, :body, :central_bank, :country)",
        row,
    )
    conn.commit()
    conn.close()


def already_rated_urls() -> set[str]:
    conn = _conn()
    urls = {row[0] for row in conn.execute("SELECT url FROM speeches")}
    conn.close()
    return urls


def run_boe_daily() -> list[dict]:
    """Check for new BoE 2026 MPC speeches, rate them, regenerate BoE report."""
    print("\n--- Bank of England ---")
    new_speeches = get_new_boe_2026()
    rated_rows = []

    for sp in new_speeches:
        print(f"  Rating: {sp['speaker']} | {sp['title'][:60]}")
        try:
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="Bank of England", db_path=str(DB_PATH))
            now = datetime.now(timezone.utc).isoformat()
            boe_save_rating(sp["url"], rating["score"], rating["justification"], now)
            save_topic_scores(sp["url"], rating.get("topic_scores"))
            sp["score"] = rating["score"]
            sp["justification"] = rating["justification"]
            rated_rows.append(sp)
            print(f"    Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"    Error rating {sp['url']}: {e}")
        time.sleep(0.3)

    run_classification(bank="Bank of England")
    generate_boe_filtered_report()
    return rated_rows


def run_boj_daily() -> list[dict]:
    """Check for new BoJ 2026 Policy Board speeches, rate them, regenerate BoJ report."""
    print("\n--- Bank of Japan ---")
    new_speeches = get_new_boj_2026()
    rated_rows = []

    for sp in new_speeches:
        print(f"  Rating: {sp['speaker']} | {sp['title'][:60]}")
        try:
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="Bank of Japan", db_path=str(DB_PATH))
            now = datetime.now(timezone.utc).isoformat()
            boj_save_rating(sp["url"], rating["score"], rating["justification"], now)
            save_topic_scores(sp["url"], rating.get("topic_scores"))
            sp["score"] = rating["score"]
            sp["justification"] = rating["justification"]
            rated_rows.append(sp)
            print(f"    Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"    Error rating {sp['url']}: {e}")
        time.sleep(0.3)

    run_classification(bank="Bank of Japan")
    generate_boj_filtered_report()
    return rated_rows


def run_bcb_daily() -> list[dict]:
    """Check for new BCB Copom speeches, rate them, regenerate BCB report."""
    print("\n--- Banco Central do Brasil (BCB) ---")
    new_speeches = get_new_bcb_2026()
    rated_rows = []

    for sp in new_speeches:
        print(f"  Rating: {sp['speaker']} | {sp['title'][:60]}")
        try:
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="BCB", db_path=str(DB_PATH))
            now = datetime.now(timezone.utc).isoformat()
            bcb_save_rating(sp["url"], rating["score"], rating["justification"], now)
            save_topic_scores(sp["url"], rating.get("topic_scores"))
            sp["score"] = rating["score"]
            sp["justification"] = rating["justification"]
            rated_rows.append(sp)
            print(f"    Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"    Error rating {sp['url']}: {e}")
        time.sleep(0.3)

    run_classification(bank="BCB")
    generate_bcb_filtered_report()
    return rated_rows


def run_riksbank_daily() -> list[dict]:
    """Check for new Riksbank Executive Board speeches, rate them, regenerate report."""
    print("\n--- Sveriges Riksbank ---")
    new_speeches = get_new_riksbank_speeches()
    rated_rows = []

    for sp in new_speeches:
        print(f"  Rating: {sp['speaker']} | {sp['title'][:60]}")
        try:
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="Riksbank", db_path=str(DB_PATH))
            now = datetime.now(timezone.utc).isoformat()
            riksbank_save_rating(sp["url"], rating["score"], rating["justification"], now)
            save_topic_scores(sp["url"], rating.get("topic_scores"))
            sp["score"] = rating["score"]
            sp["justification"] = rating["justification"]
            rated_rows.append(sp)
            print(f"    Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"    Error rating {sp['url']}: {e}")
        time.sleep(0.3)

    run_classification(bank="Riksbank")
    generate_riksbank_filtered_report()
    return rated_rows


def run_nbp_daily() -> list[dict]:
    """Check for new NBP speeches via BIS, rate them, regenerate NBP report."""
    from scraper_nbp import get_new_nbp_speeches, save_rating as nbp_save_rating
    print("\n--- Narodowy Bank Polski (NBP) ---")
    new_speeches = get_new_nbp_speeches()
    rated_rows = []

    for sp in new_speeches:
        print(f"  Rating: {sp['speaker']} | {sp['title'][:60]}")
        try:
            lang = sp.get("language", "en")
            body_en = sp.get("body_en") or ""
            if lang != "en" and not body_en:
                from translator import translate_speech
                print(f"    Translating ({lang}) ...")
                body_en = translate_speech(sp["body"], lang, title=sp["title"], speaker=sp["speaker"])
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="NBP", db_path=str(DB_PATH),
                                 language=lang, body_en=body_en)
            now = datetime.now(timezone.utc).isoformat()
            nbp_save_rating(sp["url"], rating["score"], rating["justification"], now,
                            body_en=body_en if body_en else None)
            save_topic_scores(sp["url"], rating.get("topic_scores"))
            sp["score"] = rating["score"]
            sp["justification"] = rating["justification"]
            rated_rows.append(sp)
            print(f"    Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"    Error rating {sp['url']}: {e}")
        time.sleep(0.3)

    run_classification(bank="NBP")
    generate_nbp_filtered_report()
    return rated_rows


def run_bnr_daily() -> list[dict]:
    """Check for new BNR speeches via BIS, rate them, regenerate BNR report."""
    from scraper_bnr import get_new_bnr_speeches, save_rating as bnr_save_rating
    print("\n--- Banca Națională a României (BNR) ---")
    new_speeches = get_new_bnr_speeches()
    rated_rows = []

    for sp in new_speeches:
        print(f"  Rating: {sp['speaker']} | {sp['title'][:60]}")
        try:
            lang = sp.get("language", "en")
            body_en = sp.get("body_en") or ""
            if lang != "en" and not body_en:
                from translator import translate_speech
                print(f"    Translating ({lang}) ...")
                body_en = translate_speech(sp["body"], lang, title=sp["title"], speaker=sp["speaker"])
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="BNR", db_path=str(DB_PATH),
                                 language=lang, body_en=body_en)
            now = datetime.now(timezone.utc).isoformat()
            bnr_save_rating(sp["url"], rating["score"], rating["justification"], now,
                            body_en=body_en if body_en else None)
            save_topic_scores(sp["url"], rating.get("topic_scores"))
            sp["score"] = rating["score"]
            sp["justification"] = rating["justification"]
            rated_rows.append(sp)
            print(f"    Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"    Error rating {sp['url']}: {e}")
        time.sleep(0.3)

    run_classification(bank="BNR")
    generate_bnr_filtered_report()
    return rated_rows


def run_cbrt_daily() -> list[dict]:
    """Check for new CBRT speeches via BIS, rate them, regenerate CBRT report."""
    from scraper_cbrt import get_new_cbrt_speeches, save_rating as cbrt_save_rating
    print("\n--- Central Bank of Turkey (CBRT) ---")
    new_speeches = get_new_cbrt_speeches()
    rated_rows = []

    for sp in new_speeches:
        print(f"  Rating: {sp['speaker']} | {sp['title'][:60]}")
        try:
            lang = sp.get("language", "en")
            body_en = sp.get("body_en") or ""
            if lang != "en" and not body_en:
                from translator import translate_speech
                print(f"    Translating ({lang}) ...")
                body_en = translate_speech(sp["body"], lang, title=sp["title"], speaker=sp["speaker"])
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="CBRT", db_path=str(DB_PATH),
                                 language=lang, body_en=body_en)
            now = datetime.now(timezone.utc).isoformat()
            cbrt_save_rating(sp["url"], rating["score"], rating["justification"], now,
                             body_en=body_en if body_en else None)
            save_topic_scores(sp["url"], rating.get("topic_scores"))
            sp["score"] = rating["score"]
            sp["justification"] = rating["justification"]
            rated_rows.append(sp)
            print(f"    Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"    Error rating {sp['url']}: {e}")
        time.sleep(0.3)

    run_classification(bank="CBRT")
    generate_cbrt_filtered_report()
    return rated_rows


def run_cnb_daily() -> list[dict]:
    """Check for new CNB Bank Board speeches, rate them, regenerate CNB report."""
    from scraper_cnb import get_new_cnb_speeches, save_rating as cnb_save_rating
    print("\n--- Czech National Bank ---")
    new_speeches = get_new_cnb_speeches()
    rated_rows = []

    for sp in new_speeches:
        print(f"  Rating: {sp['speaker']} | {sp['title'][:60]}")
        try:
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="CNB", db_path=str(DB_PATH))
            now = datetime.now(timezone.utc).isoformat()
            cnb_save_rating(sp["url"], rating["score"], rating["justification"], now)
            save_topic_scores(sp["url"], rating.get("topic_scores"))
            sp["score"] = rating["score"]
            sp["justification"] = rating["justification"]
            rated_rows.append(sp)
            print(f"    Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"    Error rating {sp['url']}: {e}")
        time.sleep(0.3)

    run_classification(bank="CNB")
    generate_cnb_filtered_report()
    return rated_rows


def run_sarb_daily() -> list[dict]:
    """Check for new SARB MPC speeches, rate them, regenerate SARB report."""
    print("\n--- South African Reserve Bank ---")
    new_speeches = get_new_sarb_speeches()
    rated_rows = []

    for sp in new_speeches:
        print(f"  Rating: {sp['speaker']} | {sp['title'][:60]}")
        try:
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="SARB", db_path=str(DB_PATH))
            now = datetime.now(timezone.utc).isoformat()
            sarb_save_rating(sp["url"], rating["score"], rating["justification"], now)
            save_topic_scores(sp["url"], rating.get("topic_scores"))
            sp["score"] = rating["score"]
            sp["justification"] = rating["justification"]
            rated_rows.append(sp)
            print(f"    Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"    Error rating {sp['url']}: {e}")
        time.sleep(0.3)

    run_classification(bank="SARB")
    generate_sarb_filtered_report()
    return rated_rows


def run_ecb_daily() -> list[dict]:
    """Check for new ECB 2026 speeches, rate them, regenerate ECB report."""
    print("\n--- ECB ---")
    new_speeches = get_new_ecb_2026()
    rated_rows = []

    for sp in new_speeches:
        print(f"  Rating: {sp['speaker']} | {sp['title'][:60]}")
        try:
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="ECB", db_path=str(DB_PATH))
            now = datetime.now(timezone.utc).isoformat()
            ecb_save_rating(sp["url"], rating["score"], rating["justification"], now)
            sp["score"] = rating["score"]
            sp["justification"] = rating["justification"]
            rated_rows.append(sp)
            print(f"    Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"    Error rating {sp['url']}: {e}")
        time.sleep(0.3)

    run_classification(bank="ECB")
    generate_ecb_filtered_report()
    return rated_rows


def slack_notify_member_changes(changes: dict) -> None:
    """Send a Slack alert when committee membership changes are detected."""
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook or not changes:
        return

    lines = [":warning: *Committee membership changes detected — member lists updated*\n"]
    for bank, diff in changes.items():
        if diff.get("added"):
            lines.append(f"*{bank}* — new: {', '.join(diff['added'])}")
        if diff.get("removed"):
            lines.append(f"*{bank}* — departed: {', '.join(diff['removed'])}")
    lines.append("\n_`data/members.json` has been updated. Verify `MPC_MEMBERSHIP` dates in `scraper_boe.py` if BoE changed._")

    payload = json.dumps({"text": "\n".join(lines)}).encode()
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  Slack member-change notify failed: {e}")


def push_reports_to_github() -> None:
    """Commit updated report HTMLs and push to GitHub Pages."""
    reports = [
        "index.html",
        "report_fed_filtered.html",
        "report_ecb_filtered.html",
        "report_boe_filtered.html",
        "report_boj_filtered.html",
        "report_bcb_filtered.html",
        "report_riksbank_filtered.html",
        "report_sarb_filtered.html",
        "report_cnb_filtered.html",
        "report_nbp_filtered.html",
        "report_bnr_filtered.html",
        "report_cbrt_filtered.html",
        "report_global_themes.html",
    ]
    try:
        subprocess.run(["git", "add"] + reports, check=True, capture_output=True)
        today = datetime.now().strftime("%Y-%m-%d")
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
        )
        if result.returncode == 0:
            print("  GitHub Pages: no changes to push.")
            return
        subprocess.run(
            ["git", "commit", "-m", f"Daily update {today}"],
            check=True, capture_output=True,
        )
        subprocess.run(["git", "push"], check=True, capture_output=True)
        print(f"  GitHub Pages updated: {GITHUB_PAGES_BASE}")
    except subprocess.CalledProcessError as e:
        print(f"  GitHub Pages push failed: {e}")


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set. Copy .env.example to .env and fill in your key.")

    # --- Membership check (all banks) ---
    print("Checking committee membership ...")
    member_changes = check_members()
    if member_changes:
        slack_notify_member_changes(member_changes)

    # --- Federal Reserve ---
    print("Fetching latest speech from federalreserve.gov ...")
    url = get_latest_speech_url()
    print(f"  {url}")

    fed_new = []
    rated = already_rated_urls()
    if url in rated:
        df = load_data()
        row = df[df["url"] == url].iloc[0]
        print(f"Already rated on {row['rated_at'][:10]}:")
        print(f"  {row['date']} | {row['speaker']}")
        print(f"  Score: {row['score']}/10 — {row['justification']}")
        generate_fed_filtered_report()
    else:
        print("Fetching speech text ...")
        speech = get_speech(url)
        print(f"  Title:   {speech.title}")
        print(f"  Speaker: {speech.speaker}")
        print(f"  Date:    {speech.date}")
        print(f"  Length:  {len(speech.text):,} chars")

        if not speech.text:
            sys.exit("Error: speech text is empty — the page structure may have changed.")

        print("Rating speech ...")
        rating = rate_speech(speech.title, speech.speaker, speech.date, speech.text,
                             bank="Federal Reserve", db_path=str(DB_PATH))

        row = {
            "url":           speech.url,
            "date":          speech.date,
            "speaker":       speech.speaker,
            "title":         speech.title,
            "score":         rating["score"],
            "justification": rating["justification"],
            "rated_at":      datetime.now(timezone.utc).isoformat(),
            "body":          speech.text,
            "central_bank":  "Federal Reserve",
            "country":       "USA",
        }
        save_row(row)
        save_topic_scores(speech.url, rating.get("topic_scores"))
        fed_new = [row]

        print(f"\nResult:")
        print(f"  Score:         {rating['score']}/10")
        print(f"  Justification: {rating['justification']}")
        print(f"\nSaved to {DB_PATH}")
        run_classification(bank="Federal Reserve")
        generate_fed_filtered_report()

    # --- ECB ---
    ecb_new = run_ecb_daily()

    # --- Bank of England ---
    boe_new = run_boe_daily()

    # --- Bank of Japan ---
    boj_new = run_boj_daily()

    # --- BCB ---
    bcb_new = run_bcb_daily()

    # --- Riksbank ---
    riksbank_new = run_riksbank_daily()

    # --- SARB ---
    sarb_new = run_sarb_daily()

    # --- CNB ---
    cnb_new = run_cnb_daily()

    # --- NBP ---
    nbp_new = run_nbp_daily()

    # --- BNR ---
    bnr_new = run_bnr_daily()

    # --- CBRT ---
    cbrt_new = run_cbrt_daily()

    # --- Global overview ---
    print("\nRegenerating global themes overview ...")
    from report_global_themes import generate_global_themes_report
    generate_global_themes_report()

    # --- Emerging topics scan ---
    all_new = (fed_new + ecb_new + boe_new + boj_new + bcb_new +
               riksbank_new + sarb_new + cnb_new + nbp_new + bnr_new + cbrt_new)
    if all_new:
        from detect_emerging_topics import run_emerging_scan
        run_emerging_scan(all_new)

    # --- Push updated reports to GitHub Pages ---
    print("\nPushing reports to GitHub Pages ...")
    push_reports_to_github()


def run_boj_batch(start_year: int = 2021) -> None:
    """Load all BoJ Policy Board speeches from start_year to present, rate them, generate report."""
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")

    from scraper_boj import get_all_boj_speeches
    from datetime import date as _date

    current_year = datetime.now().year
    today = _date.today().isoformat()
    cutoff = _date(current_year - 5, _date.today().month, _date.today().day).isoformat()

    print(f"\n--- Bank of Japan batch ({start_year}–{current_year}) ---")
    new_speeches = get_all_boj_speeches(start_year=start_year, end_year=current_year)

    from translator import translate_speech

    # Also pick up any previously stored but unrated speeches within the 5-year window
    conn = _conn()
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body, language, body_en FROM speeches "
        "WHERE central_bank='Bank of Japan' AND score IS NULL AND date >= ? AND body IS NOT NULL AND body != ''",
        (cutoff,),
    ).fetchall()
    conn.close()

    already = {s["url"] for s in new_speeches}
    from scraper_boj import ALL_BOJ_BOARD
    for row in unrated:
        url, date, speaker, title, body, lang, body_en = row
        if url not in already and speaker in ALL_BOJ_BOARD:
            new_speeches.append({"url": url, "date": date, "speaker": speaker, "title": title,
                                  "body": body, "language": lang or "en", "body_en": body_en or ""})

    # Filter to last 5 years for rating (no point burning API on older speeches that won't appear in report)
    to_rate = [s for s in new_speeches if s.get("date", "") >= cutoff]
    print(f"  {len(to_rate)} Policy Board speeches to rate (within last 5 years)")

    errors = 0
    for i, sp in enumerate(to_rate, 1):
        print(f"[{i}/{len(to_rate)}] {sp['speaker']} | {sp['date']} | {sp['title'][:55]}")
        if is_off_topic_by_title(sp["title"]):
            print(f"  Skipped — off-topic title filter")
            continue
        try:
            lang = sp.get("language", "en")
            body_en = sp.get("body_en") or ""
            if lang != "en" and not body_en:
                print(f"  Translating (ja) ...")
                body_en = translate_speech(sp["body"], lang, title=sp["title"], speaker=sp["speaker"])
                time.sleep(0.2)
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="Bank of Japan", db_path=str(DB_PATH),
                                 language=lang, body_en=body_en)
            now = datetime.now(timezone.utc).isoformat()
            boj_save_rating(sp["url"], rating["score"], rating["justification"], now,
                            body_en=body_en if body_en else None)
            print(f"  Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"  Error: {e}")
            errors += 1
        time.sleep(0.3)

    print(f"\nDone. {len(to_rate) - errors} rated, {errors} errors.")
    generate_boj_report()


def run_bcb_batch(start_year: int = 2021) -> None:
    """Load all BCB Copom speeches from start_year to present via Portuguese discursos API, rate, generate report."""
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")

    from scraper_bcb import get_all_bcb_speeches, ALL_COPOM
    from datetime import date as _date

    current_year = datetime.now().year
    cutoff = _date(current_year - 5, _date.today().month, _date.today().day).isoformat()

    print(f"\n--- Banco Central do Brasil batch ({start_year}–{current_year}) ---")
    print("  Loading discursos via Portuguese API (Playwright) ...")
    new_speeches = get_all_bcb_speeches(start_year=start_year, end_year=current_year)

    # Also pick up stored-but-unrated speeches for ALL historical members (same as other banks)
    conn = _conn()
    unrated = conn.execute(
        "SELECT url, date, speaker, title, body FROM speeches "
        "WHERE central_bank='BCB' AND score IS NULL AND date >= ? AND body IS NOT NULL AND body != ''",
        (cutoff,),
    ).fetchall()
    conn.close()

    already = {s["url"] for s in new_speeches}
    for row in unrated:
        url, date, speaker, title, body = row
        if url not in already and speaker in ALL_COPOM:
            new_speeches.append({"url": url, "date": date, "speaker": speaker, "title": title, "body": body})

    to_rate = [s for s in new_speeches if s.get("date", "") >= cutoff]
    print(f"  {len(to_rate)} Copom speeches to rate (within last 5 years)")

    errors = 0
    for i, sp in enumerate(to_rate, 1):
        print(f"[{i}/{len(to_rate)}] {sp['speaker']} | {sp['date']} | {sp['title'][:55]}")
        if not sp.get("body"):
            print("  Skipped — no text")
            continue
        try:
            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="BCB", db_path=str(DB_PATH))
            now = datetime.now(timezone.utc).isoformat()
            bcb_save_rating(sp["url"], rating["score"], rating["justification"], now)
            print(f"  Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"  Error: {e}")
            errors += 1
        time.sleep(0.3)

    print(f"\nScrape+rate done. {len(to_rate) - errors} rated, {errors} errors.")
    run_classification(bank="BCB")
    generate_bcb_filtered_report()


def run_ecb_batch() -> None:
    """Backfill ratings for all ECB exec board speeches in the last 5 years."""
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")
    from datetime import date as _date
    today = _date.today()
    cutoff = _date(today.year - 5, today.month, today.day).isoformat()

    print("Downloading ECB CSV for historical backfill ...")
    from scraper_ecb import fetch_ecb_csv, store_all_ecb
    df = fetch_ecb_csv()
    store_all_ecb(df)  # make sure all speeches are in the DB

    speeches = get_unrated_ecb_historical(cutoff)
    print(f"  {len(speeches)} unrated ECB board speeches since {cutoff}")
    if not speeches:
        print("  Nothing to rate.")
        generate_ecb_report()
        return

    errors = 0
    for i, sp in enumerate(speeches, 1):
        print(f"[{i}/{len(speeches)}] {sp['speaker']} | {sp['date']} | {sp['title'][:60]}")
        try:
            if not sp.get("body"):
                print("  Skipped — no text")
                continue

            rating = rate_speech(sp["title"], sp["speaker"], sp["date"], sp["body"],
                                 bank="ECB", db_path=str(DB_PATH))
            now = datetime.now(timezone.utc).isoformat()
            ecb_save_rating(sp["url"], rating["score"], rating["justification"], now)
            print(f"  Score: {rating['score']}/10 — {rating['justification'][:70]}...")
        except Exception as e:
            print(f"  Error: {e}")
            errors += 1
        time.sleep(0.3)

    print(f"\nDone. {len(speeches) - errors} rated, {errors} errors.")
    generate_ecb_report()


def run_batch(start_year: int = None, days: int = 365) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")

    since = datetime(start_year, 1, 1) if start_year else datetime.now() - timedelta(days=days)
    rated = already_rated_urls()

    current_year = datetime.now().year
    all_urls: list[str] = []
    for y in range(since.year, current_year + 1):
        batch = get_all_speech_urls(y)
        print(f"  {y}: {len(batch)} speeches found")
        all_urls.extend(batch)

    to_rate = [
        (url, d) for url in all_urls
        if url not in rated
        and (d := date_from_url(url)) is not None
        and d >= since
    ]
    to_rate.sort(key=lambda x: x[1])
    print(f"\n{len(to_rate)} unrated speeches. Starting ...\n")

    errors = 0
    for i, (url, _) in enumerate(to_rate, 1):
        print(f"[{i}/{len(to_rate)}] {url}")
        try:
            speech = get_speech(url)
            if not speech.text:
                print("  Skipped — no text extracted")
                continue
            print(f"  {speech.speaker} | {speech.title} | {speech.date}")

            rating = rate_speech(speech.title, speech.speaker, speech.date, speech.text,
                                 bank="Federal Reserve", db_path=str(DB_PATH))
            print(f"  Score: {rating['score']}/10 — {rating['justification'][:80]}...")
            save_row({
                "url":           url,
                "date":          speech.date,
                "speaker":       speech.speaker,
                "title":         speech.title,
                "score":         rating["score"],
                "justification": rating["justification"],
                "rated_at":      datetime.now(timezone.utc).isoformat(),
                "body":          speech.text,
                "central_bank":  "Federal Reserve",
                "country":       "USA",
            })
        except Exception as e:
            print(f"  Error: {e}")
            errors += 1
        time.sleep(0.5)

    generate_report()
    print(f"\nDone. {len(to_rate) - errors} rated, {errors} errors.")


if __name__ == "__main__":
    if "--all" in sys.argv:
        run_batch()
    elif "--covid" in sys.argv:
        run_batch(start_year=2020)
    else:
        main()
