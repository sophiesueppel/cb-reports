"""
Scrapes each central bank's official committee page, compares to the stored
member list in data/members.json, and returns any changes.

Called at the start of every daily run. If members have changed:
  - data/members.json is updated automatically
  - The caller is responsible for sending a Slack alert
"""

import json
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

MEMBERS_PATH = Path("data/members.json")
HISTORY_PATH = Path("data/members_history.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

# Fallback hardcoded lists used when members.json doesn't exist yet
_BOE_MPC_DEFAULT = [
    "Andrew Bailey", "Sarah Breeden", "Clare Lombardelli", "Dave Ramsden",
    "Swati Dhingra", "Megan Greene", "Alan Taylor", "Catherine Mann",
    "Huw Pill",
]
_ECB_BOARD_DEFAULT = [
    "Christine Lagarde", "Luis de Guindos", "Philip R. Lane",
    "Isabel Schnabel", "Frank Elderson", "Piero Cipollone",
]
_FED_GOVERNORS_DEFAULT = [
    "Jerome Powell", "Philip Jefferson", "Michael Barr", "Michelle Bowman",
    "Lisa Cook", "Adriana Kugler", "Christopher Waller",
]
_BOJ_BOARD_DEFAULT = [
    "Kazuo Ueda", "Ryozo Himino", "Shinichi Uchida",
    "Naoki Tamura", "Hajime Takata", "Junko Nakagawa",
    "Junko Koeda", "Kazuyuki Masu", "Toichiro Asada",
]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _load() -> dict:
    if MEMBERS_PATH.exists():
        return json.loads(MEMBERS_PATH.read_text(encoding="utf-8"))
    return {
        "boe_mpc":          _BOE_MPC_DEFAULT,
        "ecb_exec_board":   _ECB_BOARD_DEFAULT,
        "fed_governors":    _FED_GOVERNORS_DEFAULT,
        "boj_policy_board": _BOJ_BOARD_DEFAULT,
    }


def _save(data: dict) -> None:
    MEMBERS_PATH.parent.mkdir(exist_ok=True)
    MEMBERS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_boe_mpc() -> set[str]:
    return set(_load().get("boe_mpc", _BOE_MPC_DEFAULT))


def load_ecb_board() -> set[str]:
    return set(_load().get("ecb_exec_board", _ECB_BOARD_DEFAULT))


def load_fed_governors() -> set[str]:
    return set(_load().get("fed_governors", _FED_GOVERNORS_DEFAULT))


# ---------------------------------------------------------------------------
# Scrapers
# ---------------------------------------------------------------------------

def _soup(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [members] Fetch failed ({url}): {e}")
        return None


def _scrape_boe_mpc() -> set[str] | None:
    soup = _soup("https://www.bankofengland.co.uk/monetary-policy-committee")
    if not soup:
        return None

    names: set[str] = set()

    # Try known selectors for the BoE people listing
    for sel in [
        "h2.heading-5", "h3.heading-5", ".people-listing h3",
        ".person__name", "h2.people-listing__name", "h3",
    ]:
        for el in soup.select(sel):
            text = el.get_text(strip=True)
            # Name-like: 2–4 words, starts with capital, no numbers
            if re.match(r"^[A-Z][a-z]+([\s\-][A-Z][a-z]+){1,3}$", text):
                names.add(text)

    # BoE MPC has 9 members; if we found at least 5, trust it
    return names if len(names) >= 5 else None


def _scrape_ecb_board() -> set[str] | None:
    soup = _soup(
        "https://www.ecb.europa.eu/ecb/orga/decisions/eb/html/index.en.html"
    )
    if not soup:
        return None

    names: set[str] = set()
    for sel in [
        ".person-name", ".ecb-personLinkHook", "h3.person",
        ".people-list__item h3", "h3", "h2",
    ]:
        for el in soup.select(sel):
            text = el.get_text(strip=True)
            # Strip titles like "Dr", "Prof" etc.
            text = re.sub(r"^(Dr\.?|Prof\.?|Mr\.?|Ms\.?)\s+", "", text)
            if re.match(r"^[A-Z][a-záéíóúàèìòùäöü\-]+([\s][A-Z][a-záéíóúàèìòùäöü\.\-]+){1,3}$", text):
                names.add(text)

    # ECB Exec Board has 6 members
    return names if len(names) >= 4 else None


def _scrape_boj_board() -> set[str] | None:
    """Scrape BoJ Policy Board members from the About page."""
    from scraper_boj import _normalize_name
    # Try the current BoJ site structure
    for url in [
        "https://www.boj.or.jp/en/about/people/pb_intro.htm",
        "https://www.boj.or.jp/en/about/people/index.htm",
        "https://www.boj.or.jp/en/about/organization/pb/index.htm",
    ]:
        soup = _soup(url)
        if soup is None:
            continue
        names: set[str] = set()
        for el in soup.find_all(["h2", "h3", "td", "li"]):
            text = el.get_text(strip=True)
            # BoJ names appear as "FAMILY Given" (family in caps)
            m = re.match(r"^([A-Z]{2,})\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)$", text)
            if m:
                names.add(_normalize_name(text))
        if len(names) >= 5:
            return names
    return None


def _scrape_fed_governors() -> set[str] | None:
    soup = _soup("https://www.federalreserve.gov/aboutthefed/bios/board/default.htm")
    if not soup:
        return None

    names: set[str] = set()
    for sel in [".card-title", "h2.card-title", "h3", ".bio-name", "h2"]:
        for el in soup.select(sel):
            text = el.get_text(strip=True)
            text = re.sub(r"^(Chair|Vice Chair|Governor),?\s*", "", text).strip()
            if re.match(r"^[A-Z][a-z]+([\s][A-Z][a-z\.]+){1,3}$", text) and len(text) > 6:
                names.add(text)

    # Board of Governors has 7 members (some seats may be vacant)
    return names if len(names) >= 4 else None


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _diff(stored: set[str], scraped: set[str]) -> dict:
    added = scraped - stored
    removed = stored - scraped
    return {"added": sorted(added), "removed": sorted(removed)}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_all() -> dict[str, dict]:
    """
    Check all three banks. Returns a dict of bank → {added, removed} for any
    bank where membership changed. Empty dict means no changes.
    Updates data/members.json if changes are found.
    """
    data = _load()
    changes: dict[str, dict] = {}

    checks = [
        ("BoE MPC",             "boe_mpc",          _BOE_MPC_DEFAULT,       _scrape_boe_mpc),
        ("ECB Executive Board", "ecb_exec_board",   _ECB_BOARD_DEFAULT,     _scrape_ecb_board),
        ("Fed Governors",       "fed_governors",    _FED_GOVERNORS_DEFAULT, _scrape_fed_governors),
        ("BoJ Policy Board",    "boj_policy_board", _BOJ_BOARD_DEFAULT,     _scrape_boj_board),
    ]

    for label, key, default, scrape_fn in checks:
        print(f"  Checking {label} membership ...")
        stored = set(data.get(key, default))
        scraped = scrape_fn()

        if scraped is None:
            print(f"    Could not scrape {label} page — skipping check")
            continue

        diff = _diff(stored, scraped)
        if diff["added"] or diff["removed"]:
            print(f"    *** {label} CHANGED ***")
            if diff["added"]:
                print(f"      New:     {', '.join(diff['added'])}")
            if diff["removed"]:
                print(f"      Removed: {', '.join(diff['removed'])}")
            changes[label] = diff
            # Update the stored list
            data[key] = sorted(scraped)
        else:
            print(f"    {label}: no changes ({len(stored)} members)")

    if changes:
        _save(data)
        print("  data/members.json updated")
        _update_history(changes)

    return changes


# ---------------------------------------------------------------------------
# Membership history (data/members_history.json)
# ---------------------------------------------------------------------------

_BANK_KEY_MAP = {
    "BoE MPC":              "boe",
    "ECB Executive Board":  "ecb",
    "Fed Governors":        "fed",
    "BoJ Policy Board":     "boj",
}


def _update_history(changes: dict[str, dict]) -> None:
    """
    When membership changes are detected, update members_history.json:
    - New member: add entry with start_date = today, end = None
    - Departed member: set end_date = today on their most recent open period
    """
    if not HISTORY_PATH.exists():
        return

    today = date.today().isoformat()
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    modified = False

    for label, diff in changes.items():
        bank = _BANK_KEY_MAP.get(label)
        if not bank:
            continue

        bank_data = history.setdefault(bank, {})

        for name in diff.get("added", []):
            if name not in bank_data:
                bank_data[name] = [[today, None]]
                print(f"  [history] Added {name} to {bank} from {today}")
            else:
                # Re-joining after a gap — add a new period
                periods = bank_data[name]
                if periods and periods[-1][1] is not None:
                    periods.append([today, None])
                    print(f"  [history] {name} re-joined {bank} from {today}")
            modified = True

        for name in diff.get("removed", []):
            if name in bank_data:
                periods = bank_data[name]
                if periods and periods[-1][1] is None:
                    periods[-1][1] = today
                    print(f"  [history] Closed {name} in {bank} on {today}")
                    modified = True

    if modified:
        HISTORY_PATH.write_text(
            json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print("  data/members_history.json updated")
