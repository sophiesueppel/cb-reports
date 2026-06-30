"""
LLM-based relevance classifier for neutral-scored central bank speeches.

Adds two columns to the DB if not present:
  relevant_to_mp        INTEGER  — 1=relevant, 0=off-topic
  relevant_to_mp_source TEXT     — 'keyword', 'llm', or 'manual'

Run once to classify all neutral Fed speeches:
  python classify_relevance_llm.py

Options:
  --bank    ECB | "Bank of England" | "Federal Reserve"  (default: Federal Reserve)
  --reset   Re-run LLM on keyword-classified speeches too (not manual ones)
  --dry-run Print what would be classified without writing to DB
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env")

DB_PATH = Path("data/speeches.db")

SYSTEM = """You are a monetary policy analyst. Decide whether a central bank speech contains
a DIRECT signal about monetary policy STANCE.

RELEVANT — mark yes if the speech contains any direct, explicit statement about:
- Current or expected interest rate path (e.g. rates need to rise/fall/stay on hold)
- Inflation assessment: whether inflation is too high, too low, or on track
- Labour market tightness or slack in the context of rate decisions
- Economic growth or recession outlook explicitly linked to policy decisions
- Balance sheet policy (QE / QT)
- The balance of risks bearing on near-term rate decisions
NOTE: a speech can be NEUTRAL on stance (data-dependent, balanced) and still be RELEVANT.
"We are watching the data and could go either way" is relevant — it just has no directional lean.
The signal can be brief — one sentence from a Governor is enough. But the speaker must STATE it directly.

KEY RULE: The link to monetary policy must be DIRECT and STATED by the speaker, not inferred.
- "Inflation is too high and we may need further tightening" in any speech → RELEVANT
- "We raised rates 25bp and growth remains weak" in any speech → RELEVANT
- "Strong supervision supports financial stability, which supports policy transmission" → NOT RELEVANT (indirect chain you constructed)
- "Capital requirements affect credit supply which could affect inflation" → NOT RELEVANT (indirect chain)
- "Climate risks could affect long-run growth" → NOT RELEVANT unless speaker explicitly links to rate decisions
- "A time of rising interest rates may constrain credit" → NOT RELEVANT (contextual mention, not a policy signal)

NOT RELEVANT — mark no if the speech contains no direct monetary policy signal, even if it touches:
- Bank supervision, capital rules, stress tests, resolution (unless paired with explicit rate/inflation commentary)
- Financial stability, macroprudential policy (unless speaker explicitly links to rate path)
- Payments, CBDCs, fintech, digital assets, tokenisation (unless speaker explicitly discusses MP transmission effects)
- Climate, biodiversity, sustainability (unless speaker explicitly links to near-term rate decisions)
- Community development, financial inclusion, ceremonial remarks, career guidance
- Historical or academic analysis with no current policy signal

When uncertain, lean NOT RELEVANT if the only connection is a structural chain you constructed.
Lean RELEVANT if the speaker uses explicit economic or policy language."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_classification",
            "description": "Submit the monetary policy relevance classification",
            "parameters": {
                "type": "object",
                "properties": {
                    "relevant": {
                        "type": "boolean",
                        "description": "True if the speech is relevant to monetary policy stance",
                    },
                    "reason": {
                        "type": "string",
                        "description": "One sentence explaining the classification decision. ALWAYS write in English, even if the speech was in another language.",
                    },
                },
                "required": ["relevant", "reason"],
                "additionalProperties": False,
            },
        },
    }
]


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    if "relevant_to_mp" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN relevant_to_mp INTEGER")
    if "relevant_to_mp_source" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN relevant_to_mp_source TEXT")
    if "relevant_to_mp_reason" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN relevant_to_mp_reason TEXT")
    if "original_score" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN original_score INTEGER")
    conn.commit()


def _classify_one(client: OpenAI, title: str, speaker: str, date: str, body: str) -> dict:
    """Call the LLM and return {relevant: bool, reason: str}."""
    body_text = (body or "").strip()
    user_msg = (
        f'Title: "{title}"\n'
        f"Speaker: {speaker}\n"
        f"Date: {date}\n\n"
        f"--- Speech ---\n{body_text}"
    )
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        tools=TOOLS,
        tool_choice={"type": "function", "function": {"name": "submit_classification"}},
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )
    tool_call = response.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)


def run_classification(bank: str = "Federal Reserve", reset: bool = False, dry_run: bool = False) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")

    conn = sqlite3.connect(str(DB_PATH))
    _ensure_columns(conn)

    # Target: neutral speeches (score 4-6) AND ALL off-topic speeches (score=0) regardless of original_score
    # Always skip 'manual' source
    if reset:
        rows = conn.execute(
            "SELECT url, date, speaker, title, body, relevant_to_mp_source, score, original_score "
            "FROM speeches "
            "WHERE central_bank=? "
            "AND (score BETWEEN 4 AND 6 OR score=0) "
            "AND (relevant_to_mp_source IS NULL OR relevant_to_mp_source != 'manual') "
            "ORDER BY date DESC",
            (bank,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT url, date, speaker, title, body, relevant_to_mp_source, score, original_score "
            "FROM speeches "
            "WHERE central_bank=? "
            "AND (score BETWEEN 4 AND 6 OR score=0) "
            "AND relevant_to_mp_source IS NULL "
            "ORDER BY date DESC",
            (bank,),
        ).fetchall()

    print(f"  {len(rows)} neutral {bank} speeches to classify")
    if not rows:
        print("  Nothing to do.")
        conn.close()
        return

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    done, errors = 0, 0

    for i, (url, date, speaker, title, body, _source, cur_score, orig_score) in enumerate(rows, 1):
        label = f"[{i}/{len(rows)}] {date} | {(title or '')[:55]}"
        if dry_run:
            print(f"  DRY RUN {label}")
            continue

        try:
            result = _classify_one(client, title or "", speaker or "", date or "", body or "")
            relevant_val = 1 if result["relevant"] else 0
            reason = result.get("reason", "")

            if result["relevant"]:
                # Restore original score if we had set it to 0
                restore_score = orig_score if orig_score is not None else (cur_score if cur_score != 0 else 5)
                conn.execute(
                    "UPDATE speeches SET relevant_to_mp=1, relevant_to_mp_source='llm', "
                    "relevant_to_mp_reason=?, score=?, original_score=NULL WHERE url=?",
                    (reason, restore_score, url),
                )
            else:
                # Mark off-topic: save original score, set score=0
                save_orig = orig_score if orig_score is not None else cur_score
                conn.execute(
                    "UPDATE speeches SET relevant_to_mp=0, relevant_to_mp_source='llm', "
                    "relevant_to_mp_reason=?, score=0, original_score=? WHERE url=?",
                    (reason, save_orig, url),
                )
            conn.commit()

            tag = "RELEVANT" if result["relevant"] else "OFF-TOPIC"
            print(f"  {tag}  {label}")
            print(f"         {reason}")
            done += 1
        except Exception as e:
            print(f"  ERROR   {label}: {e}")
            errors += 1

        time.sleep(0.2)

    conn.close()
    print(f"\nDone. {done} classified, {errors} errors.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    bank = "Federal Reserve"
    reset = "--reset" in sys.argv
    dry_run = "--dry-run" in sys.argv

    for arg in sys.argv[1:]:
        if arg.startswith("--bank="):
            bank = arg.split("=", 1)[1]

    print(f"LLM relevance classifier — {bank}{' [RESET]' if reset else ''}{' [DRY RUN]' if dry_run else ''}")
    run_classification(bank=bank, reset=reset, dry_run=dry_run)
