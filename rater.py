import os
import json
import sqlite3
from pathlib import Path
from openai import OpenAI

SYSTEM = """You are an expert monetary policy analyst rating central bank speeches on a hawkish-to-dovish scale.

SCALE:
0    Off-topic          — use ONLY when the speech is primarily about structural topics with NO monetary policy signal: crypto/digital assets, AI, climate change, financial stability/macroprudential regulation (with no rate signal), international finance architecture, payment systems, bank supervision, community development, or ceremonial remarks. NOTE: speeches about central bank independence, price stability mandate, inflation expectations, or QT/QE ARE relevant — do not score these 0.
1-2  Extremely dovish   — explicitly advocates rate cuts or warns of deflation/severe slack
3-4  Dovish             — accommodative lean: "patient", "gradual", downplays inflation, emphasises growth risks
5    Neutral            — use ONLY when the speech IS about monetary policy but has genuinely balanced signals that fully offset each other, or takes a truly data-dependent stance with no directional lean
6    Slight hawkish lean — cautious or slightly hawkish framing without explicit tightening commitment
7-8  Hawkish            — tightening lean: inflation concern prominent, "restrictive for longer", "vigilant", "ready to act", upside inflation risks flagged
9-10 Extremely hawkish  — rate hikes explicitly signalled, inflation emergency framing

HAWKISH SIGNAL WORDS (score 7+ if these dominate): "vigilant", "inflation remains elevated", "above target", "restrictive", "ready to act", "second-round effects", "upside risks to inflation", "further tightening", "remain tight"
DOVISH SIGNAL WORDS (score 4- if these dominate): "gradual", "patient", "downside risks", "below target", "weak demand", "labour market softening", "easing conditions", "rate cuts"

CRITICAL INSTRUCTION: First decide if the speech is off-topic (score 0). If it has any monetary policy signal, score 1–10. If the speech contains recognisable hawkish OR dovish signal language, commit to a score outside 5-6. Reserve 5 exclusively for speeches with equal and fully offsetting signals or a genuinely data-dependent stance. A slight lean means 4 or 6; clear directional language means 3 or 7+.

ASSESS (in order of importance):
1. Explicit rate path language or forward guidance
2. Inflation characterisation — transitory vs persistent, above/below target
3. Labour market — tight vs slack
4. Risk assessment framing — upside/downside inflation risks
5. Balance sheet stance and overall tone

SPEECH TYPE: Weight formal MPC/FOMC/Governing Council speeches and Mansion House / Jackson Hole addresses most heavily for policy signals. Academic research speeches and conference panels carry less direct policy weight — focus on any explicit forward guidance they contain rather than the broader analytical framework."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_rating",
            "description": "Submit the hawkish/dovish rating for a central bank speech",
            "parameters": {
                "type": "object",
                "properties": {
                    "score": {
                        "type": "integer",
                        "description": "Rating: 0 (off-topic, no monetary policy signal) or 1 (extremely dovish) to 10 (extremely hawkish)",
                    },
                    "justification": {
                        "type": "string",
                        "description": "1-2 sentences citing specific language or themes that drove the rating. ALWAYS write in English, even if the speech was in another language.",
                    },
                    "translation": {
                        "type": "string",
                        "description": "Full English translation of the speech. Required ONLY when the speech is not in English — omit this field entirely for English speeches.",
                    },
                },
                "required": ["score", "justification"],
                "additionalProperties": False,
            },
        },
    }
]


# ---------------------------------------------------------------------------
# Topic scoring
# ---------------------------------------------------------------------------

def score_topics(text: str, title: str = "", bank: str = "") -> dict:
    """Score a speech against the 15 watchlist topics using gpt-4.1-mini.

    Returns {topic_name: 0-3} for each topic.
    0 = not mentioned
    1 = passing mention (brief reference, single sentence)
    2 = substantive discussion (a paragraph or meaningful coverage)
    3 = central/major theme (significant portion of the speech devoted to it)
    Text is truncated to 8,000 chars — sufficient for topic detection.
    """
    from topics import WATCHLIST_TOPICS, WATCHLIST_NAMES

    properties = {
        name: {
            "type": "integer",
            "minimum": 0,
            "maximum": 3,
            "description": (
                f"Prominence of this topic in the speech: {desc}. "
                "0 = not mentioned. "
                "1 = passing mention (brief reference, single sentence). "
                "2 = substantive discussion (a paragraph or meaningful coverage). "
                "3 = central/major theme (significant portion of the speech devoted to it)."
            ),
        }
        for name, desc in WATCHLIST_TOPICS
    }

    tool = [{
        "type": "function",
        "function": {
            "name": "submit_topic_scores",
            "description": "Submit prominence scores for macro/geopolitical topics in this central bank speech",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": WATCHLIST_NAMES,
                "additionalProperties": False,
            },
        },
    }]

    system_msg = (
        "You are analysing a central bank speech to score how prominently it covers each macro/geopolitical topic.\n\n"
        "Use this scale:\n"
        "  0 = not mentioned at all\n"
        "  1 = passing mention — a brief reference, a single sentence, or an item in a list\n"
        "  2 = substantive discussion — a paragraph or more of meaningful coverage\n"
        "  3 = central/major theme — a significant portion of the speech is devoted to this topic\n\n"
        "Most topics will score 0. A typical speech has 1–3 topics scoring 2 or higher."
    )

    user_msg = (
        f'Title: "{title}"\n'
        f"Bank: {bank or 'Unknown'}\n\n"
        f"---\n\n{text}"
    )

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0,
        tools=tool,
        tool_choice={"type": "function", "function": {"name": "submit_topic_scores"}},
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
    )
    tool_call = response.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rate_at_date(bank: str, speech_date: str) -> str | None:
    """Return the policy rate in effect on speech_date for the given bank."""
    from meetings import get_meetings
    meetings = get_meetings(bank)
    # Find the most recent meeting on or before the speech date
    past = [m for m in meetings if m.get("rate") and m["date"] <= speech_date]
    if not past:
        return None
    latest = max(past, key=lambda m: m["date"])
    decision = latest.get("decision", "hold")
    action = {"hike": "after a rate hike", "cut": "after a rate cut", "hold": "rates held at"}.get(decision, "")
    return f"{latest['rate']} ({action} {latest['date']})"


def _speaker_baseline(speaker: str, speech_date: str, db_path: str) -> str | None:
    """Return a short description of the speaker's recent scoring history."""
    if not db_path or not Path(db_path).exists():
        return None
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT score, date FROM speeches "
        "WHERE speaker=? AND score IS NOT NULL AND date < ? "
        "ORDER BY date DESC LIMIT 5",
        (speaker, speech_date),
    ).fetchall()
    conn.close()
    if not rows:
        return None
    scores = [r[0] for r in rows]
    avg = sum(scores) / len(scores)
    tone = "dovish" if avg <= 4 else "neutral" if avg <= 6 else "hawkish"
    score_str = ", ".join(str(s) for s in scores)
    return f"Prior {len(scores)} speeches scored: {score_str} (avg {avg:.1f} — {tone} lean)"


# ---------------------------------------------------------------------------
# Main rating function
# ---------------------------------------------------------------------------

def rate_speech(
    title: str,
    speaker: str,
    date: str,
    text: str,
    bank: str | None = None,
    db_path: str | None = None,
    language: str = "en",
    body_en: str | None = None,
) -> dict:
    """Rate a central bank speech on the 1–10 hawkish/dovish scale.

    bank and db_path are optional but improve accuracy by providing rate
    environment context and speaker baseline.
    language: ISO 639-1 code of the speech text ('en', 'cs', 'sv', etc.).
    body_en: pre-translated English version. When provided for a non-English
             speech, the rater scores this English text directly (no in-call
             translation) so the calibrated English signal words apply exactly.
             When absent for non-English speeches the rater translates inline
             as before (legacy path).
    """
    # If a pre-translated English version exists, rate that — it's higher quality
    # because the rater's signal word list is calibrated for English phrasing.
    if body_en and body_en.strip() and language != "en":
        text = body_en
        language = "en"

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Build context block
    context_lines = []
    if bank:
        rate = _rate_at_date(bank, date)
        if rate:
            context_lines.append(f"Policy rate at time of speech: {rate}")
    if db_path:
        baseline = _speaker_baseline(speaker, date, db_path)
        if baseline:
            context_lines.append(f"Speaker history: {baseline}")

    context_block = ""
    if context_lines:
        context_block = "\nCONTEXT:\n" + "\n".join(f"- {l}" for l in context_lines) + "\n"

    lang_note = ""
    if language != "en":
        lang_note = (
            f"\nNOTE: This speech is in {language.upper()}. "
            "Rate it based on its monetary policy content. "
            "You MUST provide a full English translation in the 'translation' field.\n"
        )

    user_msg = (
        f'Speech: "{title}"\n'
        f"Speaker: {speaker}\n"
        f"Date: {date}\n"
        f"{context_block}"
        f"{lang_note}"
        f"\n---\n\n"
        f"{text}"  # full text, no truncation
    )

    response = client.chat.completions.create(
        model="gpt-4.1",
        tools=TOOLS,
        tool_choice={"type": "function", "function": {"name": "submit_rating"}},
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
    )

    tool_call = response.choices[0].message.tool_calls[0]
    result = json.loads(tool_call.function.arguments)
    # Rename 'translation' → 'body_en' for consistency with DB column
    if "translation" in result:
        result["body_en"] = result.pop("translation")

    # Score watchlist topics (separate cheap call — failure doesn't affect rating)
    try:
        result["topic_scores"] = score_topics(text, title=title, bank=bank or "")
    except Exception:
        result["topic_scores"] = None

    return result
