"""Extract central-bank rate decisions from each bank's OFFICIAL website via LLM.

Fetches a bank's official monetary-policy decisions page, strips it to text, and asks
the OpenAI model (same client/pattern as rater.py) to return structured decisions as
JSON. main.refresh_meetings() feeds the results to meetings_store.upsert_meeting().

Per-bank source URLs live in SOURCES. They are the best-known official decision pages;
confirm/adjust against the live site if a bank stops extracting. Some official pages are
JS-rendered (SARB/CNB/Riksbank use Playwright in their speech scrapers) and may return
little via plain requests — refresh_meetings treats a per-bank failure as non-fatal.

Dry-run one bank:
    .venv\\Scripts\\python.exe meetings_extractor.py "Bank of Japan"
"""
import json
import os
import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

MODEL = os.environ.get("CB_MEETINGS_MODEL", "gpt-4.1-mini")
_UA = {"User-Agent": "Mozilla/5.0 (cb-reports meetings extractor)"}
_MAX_CHARS = 16000


@dataclass
class BankSource:
    bank: str
    urls: list[str]
    language: str = "en"
    rate_kind: str = "single"        # 'single' | 'range' (Fed) | 'deposit' (ECB)
    publishes_votes: bool = True     # False for ECB / BoJ (no individual counts)
    rate_name: str = "the policy rate"


SOURCES: dict[str, BankSource] = {
    "Federal Reserve": BankSource(
        "Federal Reserve",
        ["https://www.federalreserve.gov/monetarypolicy/openmarket.htm"],
        rate_kind="range", rate_name="the federal funds target range"),
    "ECB": BankSource(
        "ECB",
        ["https://www.ecb.europa.eu/press/govcdec/mopo/html/index.en.html"],
        rate_kind="deposit", publishes_votes=False,
        rate_name="the deposit facility rate"),
    "Bank of England": BankSource(
        "Bank of England",
        ["https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/"],
        rate_name="Bank Rate"),
    "Bank of Japan": BankSource(
        "Bank of Japan",
        ["https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2026/index.htm",
         "https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2025/index.htm"],
        publishes_votes=False,
        rate_name="the short-term policy interest rate"),
    "BCB": BankSource(
        "BCB",
        ["https://www.bcb.gov.br/en/monetarypolicy/copomresolutions"],
        rate_name="the Selic target rate"),
    "Riksbank": BankSource(
        "Riksbank",
        ["https://www.riksbank.se/en-gb/monetary-policy/the-policy-rate-and-financial-conditions/the-policy-rate/"],
        rate_name="the policy rate"),
    "SARB": BankSource(
        "SARB",
        ["https://www.resbank.co.za/en/home/what-we-do/monetary-policy/monetary-policy-decisions"],
        rate_name="the repo rate"),
    "CNB": BankSource(
        "CNB",
        ["https://www.cnb.cz/en/monetary-policy/bank-board-decisions/"],
        rate_name="the 2-week repo rate"),
    "NBP": BankSource(
        "NBP",
        ["https://nbp.pl/en/monetary-policy/decisions-of-the-monetary-policy-council/"],
        language="pl", rate_name="the reference rate"),
    "BNR": BankSource(
        "BNR",
        ["https://www.bnr.ro/Monetary-Policy--3318.aspx"],
        language="ro", rate_name="the monetary policy rate"),
    "CBRT": BankSource(
        "CBRT",
        ["https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/Press+Releases"],
        language="tr", rate_name="the one-week repo rate"),
}


_EXTRACT_TOOL = [{
    "type": "function",
    "function": {
        "name": "extract_decisions",
        "description": "Return the central bank's monetary-policy rate decisions found on the page.",
        "parameters": {
            "type": "object",
            "properties": {
                "meetings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string",
                                     "description": "Decision announcement date, ISO YYYY-MM-DD."},
                            "decision": {"type": "string", "enum": ["hike", "cut", "hold"],
                                         "description": "hold if the rate was left unchanged."},
                            "rate": {"type": "string",
                                     "description": "Resulting policy rate after the decision, e.g. '1.00%' or Fed range '3.50–3.75%' (use an en-dash for ranges). Empty string if unknown."},
                            "bp_change": {"type": "integer",
                                          "description": "Signed change in basis points: +25 hike, -50 cut, 0 hold."},
                            "vote": {"type": "string",
                                     "description": "Vote split 'majority-minority' e.g. '7-1', or '' if the bank does not publish counts."},
                            "note": {"type": "string",
                                     "description": "Optional one-line English note (dissents, context). Empty string if none."},
                        },
                        "required": ["date", "decision", "rate", "bp_change", "vote", "note"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["meetings"],
            "additionalProperties": False,
        },
    },
}]


def fetch_page(url: str, timeout: int = 60) -> str:
    """Fetch a URL and return readable text (nav/script/style stripped)."""
    resp = requests.get(url, headers=_UA, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
    return text.strip()[:_MAX_CHARS]


def normalize_rate(raw: str, rate_kind: str) -> str | None:
    """Tidy a rate string; convert hyphen ranges to en-dash for Fed."""
    if not raw:
        return None
    r = raw.strip()
    if rate_kind == "range":
        r = re.sub(r"\s*[-–—]\s*", "–", r)  # normalize any dash to en-dash
    return r


def build_label(decision: str, bp_change: int | None, vote: str | None) -> str:
    """Render the display chip, matching the house style in meetings.py."""
    if decision == "hold":
        base = "Rates held"
    else:
        sign = "+" if decision == "hike" else "−"  # U+2212 minus
        mag = abs(bp_change) if bp_change else 0
        base = f"{sign}{mag}bp {decision}"
    if vote:
        maj, _, mino = vote.partition("-")
        if maj and mino:
            base += f" · {maj}–{mino}"  # · and en-dash
    return base


def extract_meetings(bank: str, page_text: str, src: BankSource, today: str) -> list[dict]:
    """One OpenAI call → list of decision dicts (raw, as returned by the model)."""
    if not page_text.strip():
        return []
    lang_hint = "" if src.language == "en" else (
        f" The page is in {src.language}; translate the note to English and "
        "normalize dates to ISO format.")
    vote_hint = "" if src.publishes_votes else (
        " This bank does not publish individual vote counts — leave vote empty.")
    system_msg = (
        "You extract monetary-policy rate DECISIONS from an official central-bank page.\n"
        f"Bank: {bank}. Rate tracked: {src.rate_name}. Today is {today}.\n"
        "Rules:\n"
        "- Only include decisions that ALREADY happened (dated on or before today). "
        "NEVER include future/scheduled meetings.\n"
        "- 'decision' is hike/cut/hold based on the change vs the previous rate; hold if unchanged.\n"
        "- 'rate' is the resulting rate AFTER the decision.\n"
        + (" For the Fed, give the target range as 'low–high%' with an en-dash.\n"
           if src.rate_kind == "range" else "")
        + "- Use empty string / 0 when a value is genuinely unknown rather than guessing.\n"
        + lang_hint + vote_hint
    )
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        tools=_EXTRACT_TOOL,
        tool_choice={"type": "function", "function": {"name": "extract_decisions"}},
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": page_text},
        ],
    )
    tool_call = resp.choices[0].message.tool_calls[0]
    data = json.loads(tool_call.function.arguments)
    return data.get("meetings", [])


def fetch_and_extract(bank: str, today: str) -> list[dict]:
    """Fetch a bank's official page(s) and extract decisions. Raises on fetch error."""
    src = SOURCES[bank]
    text = "\n\n".join(fetch_page(u) for u in src.urls)
    return extract_meetings(bank, text, src, today)


if __name__ == "__main__":
    import sys
    from datetime import date
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    bank = sys.argv[1] if len(sys.argv) > 1 else "Bank of Japan"
    today = date.today().isoformat()
    rows = fetch_and_extract(bank, today)
    print(f"{bank}: {len(rows)} decisions extracted")
    for r in rows:
        lbl = build_label(r["decision"], r.get("bp_change"), r.get("vote"))
        print(f"  {r['date']}  {r['decision']:5}  {r.get('rate',''):>14}  {lbl}   {r.get('note','')}")
