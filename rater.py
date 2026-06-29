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
                },
                "required": ["score", "justification"],
                "additionalProperties": False,
            },
        },
    }
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rate_at_date(bank: str, speech_date: str) -> str | None:
    """Return the policy rate in effect on speech_date for the given bank."""
    from meetings import FED_MEETINGS, BOE_MEETINGS, ECB_MEETINGS, BOJ_MEETINGS, COPOM_MEETINGS, RIKSBANK_MEETINGS, SARB_MEETINGS
    bank_map = {
        "Federal Reserve": FED_MEETINGS,
        "Bank of England": BOE_MEETINGS,
        "ECB": ECB_MEETINGS,
        "Bank of Japan": BOJ_MEETINGS,
        "BCB": COPOM_MEETINGS,
        "Riksbank": RIKSBANK_MEETINGS,
        "SARB": SARB_MEETINGS,
    }
    meetings = bank_map.get(bank, [])
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
) -> dict:
    """Rate a central bank speech on the 1–10 hawkish/dovish scale.

    bank and db_path are optional but improve accuracy by providing rate
    environment context and speaker baseline.
    """
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

    user_msg = (
        f'Speech: "{title}"\n'
        f"Speaker: {speaker}\n"
        f"Date: {date}\n"
        f"{context_block}"
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
    return json.loads(tool_call.function.arguments)
