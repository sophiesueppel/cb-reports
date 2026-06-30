"""
Dedicated translation module for central bank speeches.

Translates non-English speeches to English using GPT-4.1 with a financial
translation-focused system prompt. Translated text is stored in body_en and
used by the rater so its calibrated English signal words apply correctly.
"""

import os
from openai import OpenAI

_LANG_NAMES = {
    "cs": "Czech",
    "sv": "Swedish",
    "ja": "Japanese",
    "pt": "Portuguese",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "es": "Spanish",
    "pl": "Polish",
    "hu": "Hungarian",
    "ro": "Romanian",
    "tr": "Turkish",
    "ko": "Korean",
    "zh": "Chinese",
}

_SYSTEM = """You are a professional financial translator specialising in central bank communications.
Produce a precise, complete English translation of the speech provided.

Rules:
- Preserve all economic and monetary policy terminology exactly — do not paraphrase signal language such as "restrictive", "gradual", "patient", "vigilant", "data-dependent"
- Keep speaker attribution language intact ("I believe...", "In my view...", "We consider...", "It seems to me...")
- Preserve paragraph structure and any section headings
- Translate completely — do not summarise or skip any passages
- Output ONLY the English translation — no preamble, no translator's notes, no comments"""


def translate_speech(text: str, language: str, title: str = "", speaker: str = "") -> str:
    """Translate a central bank speech to English.

    Returns the original text unchanged if language is 'en' or text is empty.
    Uses GPT-4.1 with a translation-only system prompt — no rating or analysis.
    """
    if language == "en" or not text or not text.strip():
        return text

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    lang_name = _LANG_NAMES.get(language, language.upper())

    header = ""
    if title:
        header += f'Title: "{title}"\n'
    if speaker:
        header += f"Speaker: {speaker}\n"
    if header:
        header += "\n"

    user_msg = (
        f"Translate this {lang_name} central bank speech to English.\n\n"
        f"{header}"
        f"--- Speech ---\n{text}"
    )

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def translate_title(title: str, language: str) -> str:
    """Translate a speech title to English. Lightweight — uses GPT-4.1-mini."""
    if language == "en" or not title or not title.strip():
        return title

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    lang_name = _LANG_NAMES.get(language, language.upper())

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "Translate the following central bank speech title to English. Output only the translated title, nothing else."},
            {"role": "user", "content": f"Translate this {lang_name} title to English:\n{title}"},
        ],
        temperature=0,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


# ── Language detection ────────────────────────────────────────────────────────

# Characters highly distinctive to each language
_CZECH_CHARS = set("řůěčšžýáíéóúůďťňŘŮĚČŠŽÝÁÍÉÓÚŮĎŤŇ")
_SWEDISH_CHARS = set("åäöÅÄÖ")
_POLISH_CHARS = set("ąęśźżćńłĄĘŚŹŻĆŃŁ")          # ł and ą are unique to Polish
_ROMANIAN_CHARS = set("ăâîșțĂÂÎȘȚ")              # ă and ș/ț are distinctive
_TURKISH_CHARS = set("şğıŞĞİ")                   # ş, ğ, and ı (dotless-i) unique to Turkish


def detect_language(text: str, title: str = "") -> str:
    """
    Detect the language of a speech from its text content.
    Returns an ISO 639-1 code: 'en', 'cs', 'sv', 'ja', 'pt', 'pl', 'ro', 'tr'.

    Uses character-frequency heuristics — no LLM call needed.
    Czech: ř and ů are essentially unique to Czech among major languages.
    Swedish: å is highly distinctive; ä/ö combined are strong.
    Polish: ł (barred l) and ą are unique to Polish.
    Romanian: ă, ș, ț are distinctive.
    Turkish: ş (s-cedilla), ğ (g-breve), ı (dotless i) are unique to Turkish.
    Japanese: any CJK character range hit.
    Default: 'en'.
    """
    sample = (title + " " + text[:1500])

    # Japanese / CJK: any character in the CJK Unified Ideographs or Hiragana/Katakana blocks
    if any(0x3000 <= ord(c) <= 0x9FFF for c in sample):
        return "ja"

    # Czech: ř and ů are essentially absent from every other European language
    czech_count = sum(1 for c in sample if c in _CZECH_CHARS)
    if czech_count >= 3:
        return "cs"

    # Polish: ł is unique to Polish; ą is also very distinctive
    polish_count = sum(1 for c in sample if c in _POLISH_CHARS)
    if polish_count >= 3:
        return "pl"

    # Turkish: ş, ğ, and ı are not found in other major European languages
    turkish_count = sum(1 for c in sample if c in _TURKISH_CHARS)
    if turkish_count >= 3:
        return "tr"

    # Romanian: ă and ș/ț are distinctive (ă is essentially absent from other Romance langs)
    romanian_count = sum(1 for c in sample if c in _ROMANIAN_CHARS)
    if romanian_count >= 3:
        return "ro"

    # Swedish: å is unique; ä/ö are shared with German/Finnish but together are strong
    swedish_count = sum(1 for c in sample if c in _SWEDISH_CHARS)
    if swedish_count >= 4:
        return "sv"

    return "en"
