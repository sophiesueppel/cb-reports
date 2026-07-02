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


def _speaker_baseline(speaker: str, speech_date: str, db_path: str,
                      bank: str | None = None) -> str | None:
    """Return a short description of the speaker's recent scoring history.

    Matches on the NORMALIZED speaker name, so title changes don't split one
    person's history (e.g. 'Governor Jerome H. Powell' vs 'Chair Jerome H. Powell',
    'Governor Lael Brainard' vs 'Vice Chair Lael Brainard')."""
    if not db_path or not Path(db_path).exists():
        return None
    conn = sqlite3.connect(db_path)
    all_rows = conn.execute(
        "SELECT score, date, speaker, central_bank FROM speeches "
        "WHERE score IS NOT NULL AND date < ? ORDER BY date DESC",
        (speech_date,),
    ).fetchall()
    conn.close()
    try:
        from speaker_norm import normalize_speaker
        target = normalize_speaker(speaker, bank or "")
        rows = [(s, d) for s, d, sp, b in all_rows
                if (bank is None or b == bank)
                and normalize_speaker(sp or "", b or "") == target][:5]
    except Exception:
        rows = [(s, d) for s, d, sp, _ in all_rows if sp == speaker][:5]
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
        baseline = _speaker_baseline(speaker, date, db_path, bank=bank)
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


# ---------------------------------------------------------------------------
# Evidence quotes — verbatim lines supporting the hawkish/dovish score
# ---------------------------------------------------------------------------

import re as _re
import unicodedata as _ud


def _normalize_for_match(s: str) -> str:
    """Fold trivial differences so a quote can be matched against the speech text:
    unify quotes/dashes, strip accents, collapse whitespace, lowercase."""
    if not s:
        return ""
    s = _ud.normalize("NFKD", s)
    s = "".join(c for c in s if not _ud.combining(c))
    trans = {
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "−": "-", " ": " ",
    }
    for a, b in trans.items():
        s = s.replace(a, b)
    s = _re.sub(r"\s+", " ", s)
    return s.strip().lower()


_QUOTE_CHAR_FOLD = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
})


def expand_quote_to_sentence(quote: str, text: str, max_len: int = 450) -> str:
    """If a quote is a mid-sentence fragment, expand it to the full sentence(s) that
    contain it, so it carries its own referent (e.g. 'we have not compromised on our
    resolve' → the sentence naming WHAT the resolve is about). Length-preserving
    character folding keeps indices aligned; expansion is skipped if the result would
    exceed max_len. Returns the (possibly) expanded quote, still verbatim text."""
    q = (quote or "").strip()
    if not q or not text:
        return quote
    needs_start = q[0].islower()
    needs_end = not q.rstrip().endswith((".", "!", "?", '"', "”", "'"))
    if not needs_start and not needs_end:
        return quote

    t2 = text.translate(_QUOTE_CHAR_FOLD)
    q2 = q.translate(_QUOTE_CHAR_FOLD)
    pat = r"\s+".join(_re.escape(tok) for tok in q2.split())
    m = _re.search(pat, t2, _re.IGNORECASE)
    if not m:
        return quote
    s, e = m.span()

    # backward to the start of the containing sentence
    start = 0
    for mm in _re.finditer(r"[.!?][\"')\]]?\s+|\n", t2[:s]):
        start = mm.end()
    # forward to the end of the containing sentence
    mm = _re.search(r"[.!?][\"')\]]?(?=\s|$)", t2[e - 1:])
    end = (e - 1 + mm.end()) if mm else len(t2)

    expanded = _re.sub(r"\s+", " ", text[start:end]).strip()
    if len(expanded) <= max_len and len(expanded) > len(q):
        return expanded
    return quote


def extract_evidence_quotes(text: str, score: int, justification: str = "",
                            title: str = "", max_quotes: int = 4) -> list:
    """Pull 2–4 VERBATIM stance-revealing quotes from a directional speech, each labelled
    hawkish or dovish ON ITS OWN MERITS. Returns [{"quote": str, "lean": ...}].

    The extractor is NOT told the speech's score/lean, so it won't cherry-pick only
    confirming lines — it's instructed to surface opposing lines too when they exist.
    `score` is used only to GATE (directional speeches ≤3 or ≥7 get quotes; neutral/
    off-topic return []). Every quote is validated as a real substring of the speech
    (after normalising quotes/dashes/whitespace); hallucinated/paraphrased ones dropped."""
    if score is None:
        return []
    score = int(score)
    # Score is used ONLY to gate whether a quotes section is shown (directional
    # speeches only) — it is deliberately NOT revealed to the extractor below, so the
    # quote selection can't be biased toward confirming the score.
    if 4 <= score <= 6 or score == 0:
        return []

    system_msg = (
        "You extract VERBATIM quotes from a central bank speech that best reveal the "
        "speaker's monetary-policy stance. Copy sentences or clauses EXACTLY from the "
        "speech — word for word, same punctuation, no paraphrasing, no inserted ellipses, "
        "no square-bracket edits.\n\n"
        f"Choose 2 to {max_quotes} lines that most clearly reveal the speaker's VIEW or "
        "INTENT on the rate path, inflation, the labour market, or the balance of risks — "
        "their judgement, conviction, forward guidance, or how they frame risks. Judge each "
        "line ON ITS OWN MERITS and label it 'hawkish' (leaning toward tighter policy / "
        "inflation concern) or 'dovish' (leaning toward easier policy / growth or labour-"
        "market concern).\n"
        "IMPORTANT: do not assume the speech leans only one way. If it contains notable "
        "lines pulling in BOTH directions, include the strongest of EACH — surface a "
        "genuinely opposing line rather than omitting it. You are not deciding an overall "
        "score; just surface the most telling lines wherever they fall.\n"
        "PREFER lines that reveal VIEW/INTENT over bare factual statements of what was "
        "decided or what merely happened, unless the same sentence gives the reasoning "
        "behind it. Prefer punchy single sentences. Do not invent text.\n"
        "SELF-CONTAINED: each quote must make sense to a reader who has NOT read the "
        "speech. If a line's meaning hangs on an unstated referent (\"our resolve\", "
        "\"this approach\", \"that expectation\", \"these measures\"), either extend the "
        "quote to include the neighbouring words that name the subject, or choose a "
        "different line that states it explicitly."
    )
    user_msg = f'Title: "{title}"\n\n---\n\n{text}'

    tool = [{
        "type": "function",
        "function": {
            "name": "submit_quotes",
            "description": "Submit verbatim supporting quotes for the speech's rating.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "quote": {"type": "string",
                                          "description": "Verbatim text copied exactly from the speech."},
                                "lean": {"type": "string", "enum": ["hawkish", "dovish"]},
                            },
                            "required": ["quote", "lean"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["quotes"],
                "additionalProperties": False,
            },
        },
    }]

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0,
        tools=tool,
        tool_choice={"type": "function", "function": {"name": "submit_quotes"}},
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
    )
    raw = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
    quotes = raw.get("quotes") or []

    # Verbatim validation: keep only quotes that genuinely appear in the speech.
    norm_text = _normalize_for_match(text)
    seen = set()
    validated = []
    for q in quotes:
        qt = (q.get("quote") or "").strip().strip('"').strip()
        if len(qt) < 12:
            continue
        nq = _normalize_for_match(qt)
        q_lean = q.get("lean")
        if q_lean not in ("hawkish", "dovish"):
            q_lean = "hawkish" if int(score) >= 7 else "dovish"
        if nq and nq in norm_text and nq not in seen:
            seen.add(nq)
            # Fragments get expanded to their full sentence so the quote carries
            # its own referent when displayed out of context.
            validated.append({"quote": expand_quote_to_sentence(qt, text), "lean": q_lean})
        if len(validated) >= max_quotes:
            break
    return validated
