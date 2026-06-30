"""
Scan a batch of new speeches for significant macro/geopolitical topics
that are NOT on the current watchlist.

Called daily from main.py after all bank runners complete.
Results are appended to data/emerging_topics_log.json and printed to console.
"""
import json
import os
from datetime import date
from pathlib import Path

LOG_PATH = Path("data/emerging_topics_log.json")


def detect_emerging_topics(speeches: list[dict]) -> list[dict]:
    """Return [{topic, reason, speeches: [str]}] for topics not on watchlist.

    speeches: list of {title, bank, body, body_en}
    Returns empty list if nothing notable found.
    """
    from topics import WATCHLIST_NAMES
    from openai import OpenAI

    # Build per-speech blurbs — full text, body_en preferred
    blurbs = []
    for s in speeches:
        text = (s.get("body_en") or s.get("body") or "").strip()
        bank = s.get("bank") or s.get("central_bank", "Unknown")
        if text:
            blurbs.append(f'[{bank}] {s["title"]}\n{text}')

    if not blurbs:
        return []

    watchlist_str = "\n".join(f"- {n}" for n in WATCHLIST_NAMES)

    tool = [{
        "type": "function",
        "function": {
            "name": "submit_emerging_topics",
            "description": "Submit any significant topics found that are not on the watchlist",
            "parameters": {
                "type": "object",
                "properties": {
                    "topics": {
                        "type": "array",
                        "description": "List of emerging topics. Empty array if nothing notable found.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "topic": {
                                    "type": "string",
                                    "description": "Short name for the emerging topic (3-6 words)",
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "1-2 sentences explaining why this is significant and not covered by the watchlist",
                                },
                                "speeches": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Titles of speeches that discuss this topic",
                                },
                            },
                            "required": ["topic", "reason", "speeches"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["topics"],
                "additionalProperties": False,
            },
        },
    }]

    system_msg = (
        "You are scanning a batch of new central bank speeches to identify any significant "
        "macro or geopolitical topics that are NOT already covered by the current watchlist.\n\n"
        f"Current watchlist (do NOT flag these):\n{watchlist_str}\n\n"
        "Only flag topics that:\n"
        "  1. Are substantively discussed (not just a passing mention), AND\n"
        "  2. Are genuinely distinct from the watchlist items above\n\n"
        "If nothing new and significant appears, return an empty list. "
        "Prefer precision over recall — a false positive is worse than a miss."
    )

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0,
        tools=tool,
        tool_choice={"type": "function", "function": {"name": "submit_emerging_topics"}},
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": "\n\n---\n\n".join(blurbs)},
        ],
    )

    result = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
    return result.get("topics", [])


def run_emerging_scan(new_speeches: list[dict]) -> None:
    """Run the scan and append results to the log file. Prints to console."""
    if not new_speeches:
        return

    print(f"\nScanning {len(new_speeches)} new speech(es) for emerging topics ...")
    topics = detect_emerging_topics(new_speeches)

    if not topics:
        print("  No emerging topics detected.")
        return

    today = date.today().isoformat()
    print(f"  {len(topics)} emerging topic(s) flagged:")
    for t in topics:
        print(f"    [{t['topic']}] {t['reason']}")
        for s in t["speeches"]:
            print(f"      - {s}")

    # Append to rolling log
    log = []
    if LOG_PATH.exists():
        try:
            log = json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            log = []

    for t in topics:
        log.append({"date": today, **t})

    LOG_PATH.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Logged to {LOG_PATH}")
