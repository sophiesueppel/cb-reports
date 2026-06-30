"""
Build keyword themes for the central bank speech tracker.

Produces data/themes.json with two sections:
  - watchlist:   15 geopolitical/event topics, same for every bank
  - structural:  ~15 shared policy-structural topics, same for every bank

Both sections use LLM-generated keyword lists (GPT-4.1-mini).
The old per-bank TF-IDF approach has been replaced by this shared set,
enabling cross-bank comparison on the same topics.

Usage:
  python build_themes.py              # rebuild structural + watchlist keywords
  python build_themes.py --force      # force rebuild even if built today
  python build_themes.py --dry-run    # show prompts, skip API calls + save
  python build_themes.py --watchlist-only   # only refresh watchlist keywords
  python build_themes.py --structural-only  # only refresh structural keywords
"""

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

THEMES_PATH = Path("data/themes.json")

# ---------------------------------------------------------------------------
# Watchlist topics (geopolitical / macro events)
# These are shown for every bank.  Names are fixed; keywords are LLM-expanded.
# ---------------------------------------------------------------------------
WATCHLIST_TOPICS = [
    ("Middle East",       "conflicts, instability, and oil supply risks centred on the Middle East including Iran, Israel, Gaza and the Gulf states"),
    ("Russia / Ukraine",  "the Russia-Ukraine war, Western sanctions on Russia, energy disruption in Europe, and reconstruction financing"),
    ("China",             "China's economic slowdown, property crisis, trade tensions with the West, capital controls, and RMB dynamics"),
    ("Taiwan",            "Taiwan Strait tensions, semiconductor supply risk, and geopolitical flashpoint scenarios"),
    ("Oil & Gas",         "crude oil prices, natural gas markets, OPEC production decisions, and energy supply shocks"),
    ("Food & Agriculture","global food prices, grain supply disruptions, agricultural commodity markets, and food inflation"),
    ("Energy Transition", "the shift to renewables, green energy investment, net zero commitments, and carbon pricing"),
    ("Tariffs",           "import tariffs, trade wars, protectionism, and the economic impact of trade barriers"),
    ("Fiscal Policy",     "government spending, budget deficits, fiscal stimulus, public debt sustainability, and sovereign risk"),
    ("Neutral Rate",      "the neutral or natural rate of interest, r-star estimates, and their implications for the rate path"),
    ("QT / Balance Sheet","quantitative tightening, balance sheet runoff, quantitative easing, and central bank asset purchases"),
    ("Yield Curve",       "the yield curve shape, term premium, curve inversion, and long-end rate dynamics"),
    ("AI & Productivity", "artificial intelligence, machine learning, automation, and their impact on productivity and the labour market"),
    ("Housing",           "housing markets, mortgage rates, house prices, residential construction, and housing affordability"),
    ("Dollar / FX",       "the US dollar, exchange rates, reserve currency status, and currency depreciation or appreciation"),
]

# ---------------------------------------------------------------------------
# Structural themes (policy-structural, shared across all banks)
# Shown as the second chart on every bank report.
# ---------------------------------------------------------------------------
STRUCTURAL_TOPICS = [
    ("Labour Market",     "employment conditions, unemployment, wage growth, job creation, and labour supply and demand dynamics"),
    ("Credit Conditions", "bank lending standards, credit growth, loan demand, household and corporate credit, and financial conditions indices"),
    ("Banking Stress",    "bank failures, systemic financial risk, capital adequacy, contagion, and financial sector vulnerabilities"),
    ("Supply Chains",     "global supply chain disruptions, logistics bottlenecks, inventory shortages, and reshoring trends"),
    ("Forward Guidance",  "central bank communication about the future policy path, rate guidance, meeting-by-meeting approach, and conditional commitments"),
    ("Digital Currency",  "central bank digital currencies (CBDC), stablecoins, cryptocurrency, and digital payment innovation"),
    ("Climate Finance",   "climate-related financial risk, green bonds, transition finance, carbon pricing, and climate stress testing"),
    ("Global Trade",      "trade flows, export and import dynamics, current account balances, and multilateral trade frameworks"),
    ("Bank Regulation",   "bank supervision, capital requirements, Basel standards, macroprudential tools, and stress testing"),
    ("Commodity Prices",  "energy prices, food commodity prices, raw material costs, and their pass-through to consumer inflation"),
    ("Pandemic Legacy",   "the lasting economic effects of COVID-19 — scarring, supply-side damage, and post-pandemic normalisation"),
    ("Emerging Markets",  "capital flows to and from emerging markets, EM vulnerabilities, contagion risk, and external debt"),
    ("Fintech",           "financial technology innovation, open banking, digital payments infrastructure, and non-bank financial intermediation"),
    ("Debt Sustainability","public and private debt levels, debt servicing costs, debt dynamics, and sustainability concerns"),
    ("Inequality",        "income and wealth inequality, distributional effects of monetary policy, financial inclusion, and access to credit"),
]


# ---------------------------------------------------------------------------
# LLM keyword generation
# ---------------------------------------------------------------------------

def _generate_keywords(client, topic_name: str, description: str, n: int = 20) -> list[str]:
    """Ask GPT-4.1-mini for keyword/phrase matches for a given topic."""
    prompt = (
        f"You are a central bank speech analyst.\n\n"
        f"Generate {n} keywords and short phrases (1–3 words each) that a central banker would use "
        f"when discussing the following topic:\n\n"
        f"Topic: {topic_name}\n"
        f"Description: {description}\n\n"
        f"Rules:\n"
        f"- Include both technical terms and plain-language equivalents\n"
        f"- Include common abbreviations (e.g. QT, CBDC, EM)\n"
        f"- Do NOT include generic monetary-policy words like 'inflation', 'interest rate', "
        f"'monetary policy', 'central bank', 'economic growth' — these appear in every speech\n"
        f"- Each keyword/phrase should be specific enough to reliably signal this topic\n"
        f"- Return ONLY a JSON array of strings, nothing else\n\n"
        f"Example output: [\"keyword one\", \"keyword two\", ...]"
    )
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0,
        max_tokens=512,
        messages=[
            {"role": "system", "content": "Return only a valid JSON array of strings."},
            {"role": "user", "content": prompt},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_themes(
    force: bool = False,
    dry_run: bool = False,
    watchlist_only: bool = False,
    structural_only: bool = False,
) -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Error: OPENAI_API_KEY not set.")

    today = date.today()
    this_month = today.strftime("%Y-%m")

    existing = {}
    if THEMES_PATH.exists():
        try:
            existing = json.loads(THEMES_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    if not force and not dry_run and existing.get("built_at", "")[:7] == this_month:
        print(f"Themes already built this month ({this_month}). Use --force to rebuild.")
        return

    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    output = {
        "built_at": today.isoformat(),
        "watchlist": dict(existing.get("watchlist", {})),
        "structural": dict(existing.get("structural", {})),
        "banks": dict(existing.get("banks", {})),  # kept for backward compat
    }

    # ── Watchlist keywords ────────────────────────────────────────────────────
    if not structural_only:
        print("\n=== Watchlist keywords ===")
        for name, description in WATCHLIST_TOPICS:
            print(f"  {name} ...", end=" ", flush=True)
            if dry_run:
                print("[dry run]")
                continue
            try:
                keywords = _generate_keywords(client, name, description, n=20)
                output["watchlist"][name] = keywords
                print(f"{len(keywords)} keywords")
            except Exception as e:
                print(f"ERROR: {e}")
                # Keep existing keywords if generation fails
                if name not in output["watchlist"] and name in existing.get("watchlist", {}):
                    output["watchlist"][name] = existing["watchlist"][name]
            time.sleep(0.3)

    # ── Structural theme keywords ─────────────────────────────────────────────
    if not watchlist_only:
        print("\n=== Structural theme keywords ===")
        for name, description in STRUCTURAL_TOPICS:
            print(f"  {name} ...", end=" ", flush=True)
            if dry_run:
                print("[dry run]")
                continue
            try:
                keywords = _generate_keywords(client, name, description, n=20)
                output["structural"][name] = keywords
                print(f"{len(keywords)} keywords")
            except Exception as e:
                print(f"ERROR: {e}")
                if name not in output["structural"] and name in existing.get("structural", {}):
                    output["structural"][name] = existing["structural"][name]
            time.sleep(0.3)

    if dry_run:
        print("\n[DRY RUN] themes.json not written.")
        return

    THEMES_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nthemes.json written — built_at={today}")
    print(f"  watchlist: {len(output['watchlist'])} topics")
    print(f"  structural: {len(output['structural'])} topics")


if __name__ == "__main__":
    force           = "--force" in sys.argv
    dry_run         = "--dry-run" in sys.argv
    watchlist_only  = "--watchlist-only" in sys.argv
    structural_only = "--structural-only" in sys.argv
    build_themes(force=force, dry_run=dry_run,
                 watchlist_only=watchlist_only, structural_only=structural_only)
