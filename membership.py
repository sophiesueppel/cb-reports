"""
Shared membership history for all three banks.
Reads from data/members_history.json, which is updated automatically by check_members.py
whenever the daily run detects a membership change.

Usage:
    from membership import was_member
    was_member("boe", "Andrew Bailey", "2022-03-15")  -> True
    was_member("fed", "Jerome Powell", "2022-03-15")  -> True
    was_member("ecb", "Isabel Schnabel", "2022-03-15") -> True
"""

import json
import re
from pathlib import Path

HISTORY_PATH = Path("data/members_history.json")

# ---------------------------------------------------------------------------
# Hardcoded fallback (used only if members_history.json doesn't exist yet)
# ---------------------------------------------------------------------------

_FALLBACK: dict[str, dict[str, list]] = {
    "boe": {
        # Governors
        "Andrew Bailey":             [["2020-03-16", None]],
        "Mervyn King":               [["2003-06-01", "2013-06-30"]],
        "Edward George":             [["1993-07-01", "2003-06-30"]],
        "Sir Edward George":         [["1993-07-01", "2003-06-30"]],
        "Mark Carney":               [["2013-07-01", "2020-03-15"]],
        # Deputy Governors
        "Dave Ramsden":              [["2017-09-04", None]],
        "Ben Broadbent":             [["2011-05-01", "2024-06-30"]],
        "Sarah Breeden":             [["2023-11-01", None]],
        "Jon Cunliffe":              [["2013-11-01", "2023-10-31"]],
        "Sir Jon Cunliffe":          [["2013-11-01", "2023-10-31"]],
        "Rachel Lomax":              [["2003-07-01", "2008-06-30"]],
        "John Gieve":                [["2006-01-01", "2009-03-31"]],
        "Charles Bean":              [["2000-10-01", "2014-06-30"]],
        "Charlie Bean":              [["2000-10-01", "2014-06-30"]],
        "Paul Tucker":               [["2002-06-01", "2013-10-31"]],
        "Minouche Shafik":           [["2014-08-01", "2017-02-28"]],
        # Chief Economists
        "Andrew Haldane":            [["2014-07-01", "2021-06-30"]],
        "Andy Haldane":              [["2014-07-01", "2021-06-30"]],
        "Huw Pill":                  [["2021-09-06", None]],
        "Spencer Dale":              [["2008-06-01", "2014-06-30"]],
        # External members
        "Silvana Tenreyro":          [["2017-07-01", "2023-07-31"]],
        "Gertjan Vlieghe":           [["2015-09-01", "2021-08-31"]],
        "Michael Saunders":          [["2016-08-01", "2022-08-31"]],
        "Jonathan Haskel":           [["2018-09-01", "2024-08-31"]],
        "Catherine Mann":            [["2021-09-01", None]],
        "Catherine L. Mann":         [["2021-09-01", None]],
        "Catherine L Mann":          [["2021-09-01", None]],
        "Megan Greene":              [["2023-07-01", None]],
        "Swati Dhingra":             [["2022-08-01", None]],
        "Clare Lombardelli":         [["2024-07-01", None]],
        "Alan Taylor":               [["2024-09-01", None]],
        "Carolyn Wilkins":           [["2021-01-01", "2023-12-31"]],
        "Carolyn A Wilkins":         [["2021-01-01", "2023-12-31"]],
        "Randall Kroszner":          [["2018-09-01", "2023-08-31"]],
        "Randy Kroszner":            [["2018-09-01", "2023-08-31"]],
        "Anil Kashyap":              [["2016-09-01", "2020-08-31"]],
        "Donald Kohn":               [["2014-07-01", "2018-05-31"]],
        "Don Kohn":                  [["2014-07-01", "2018-05-31"]],
        "Kristin Forbes":            [["2014-07-01", "2017-06-30"]],
        "Ian McCafferty":            [["2012-09-01", "2018-08-31"]],
        "Martin Weale":              [["2010-08-01", "2016-07-31"]],
        "Paul Fisher":               [["2009-03-01", "2014-06-30"]],
        "Adam Posen":                [["2009-09-01", "2012-08-31"]],
        "Adam S. Posen":             [["2009-09-01", "2012-08-31"]],
        "David Miles":               [["2009-06-01", "2015-07-31"]],
        "David Blanchflower":        [["2006-06-01", "2009-05-31"]],
        "Timothy Besley":            [["2006-06-01", "2009-05-31"]],
        "Tim Besley":                [["2006-06-01", "2009-05-31"]],
        "Andrew Sentance":           [["2006-10-01", "2011-05-31"]],
        "Andrew Sentence":           [["2006-10-01", "2011-05-31"]],
        "Richard Lambert":           [["2003-06-01", "2006-05-31"]],
        "Kate Barker":               [["2001-06-01", "2010-05-31"]],
        "Stephen Nickell":           [["2000-06-01", "2006-05-31"]],
        "Professor Stephen Nickell": [["2000-06-01", "2006-05-31"]],
        "Christopher Allsopp":       [["2000-06-01", "2003-05-31"]],
        "David Walton":              [["2005-07-01", "2006-06-23"]],
        "Marian Bell":               [["2002-06-01", "2005-05-31"]],
        "DeAnne Julius":             [["1997-06-01", "2001-05-31"]],
        "Sushil Wadhwani":           [["1999-06-01", "2002-05-31"]],
        "Charles Goodhart":          [["1997-06-01", "2000-05-31"]],
        "Martin Taylor":             [["1998-06-01", "1999-05-31"]],
        "Willem Buiter":             [["1997-06-01", "2000-05-31"]],
        "Willem H. Buiter":          [["1997-06-01", "2000-05-31"]],
    },
    "fed": {
        # Current governors (seated)
        "Jerome Powell":             [["2018-02-05", None]],
        "Philip Jefferson":          [["2022-05-23", None]],
        "Michelle Bowman":           [["2018-11-26", None]],
        "Lisa Cook":                 [["2022-05-23", None]],
        "Adriana Kugler":            [["2023-09-13", None]],
        "Christopher Waller":        [["2020-12-18", None]],
        "Kevin Warsh":               [["2026-02-01", None]],
        # Recent departed
        "Michael Barr":              [["2022-07-19", "2025-02-28"]],
        "Lael Brainard":             [["2014-06-16", "2023-02-13"]],
        "Randal Quarles":            [["2017-10-13", "2021-12-31"]],
        "Richard Clarida":           [["2018-09-17", "2022-01-14"]],
        "Jay Powell":                [["2018-02-05", None]],
    },
    "boj": {
        # Governor
        "Kazuo Ueda":                [["2023-04-09", None]],
        "Haruhiko Kuroda":           [["2013-03-20", "2023-04-08"]],
        # Deputy Governors
        "Ryozo Himino":              [["2023-03-20", None]],
        "Shinichi Uchida":           [["2023-03-20", None]],
        "Masayoshi Amamiya":         [["2018-03-20", "2023-03-19"]],
        "Masazumi Wakatabe":         [["2018-03-20", "2023-03-19"]],
        # Policy Board Members
        "Naoki Tamura":              [["2022-07-01", None]],
        "Hajime Takata":             [["2022-03-01", None]],
        "Junko Nakagawa":            [["2022-07-01", None]],
        "Asahi Noguchi":             [["2022-07-01", None]],
        "Toyoaki Nakamura":          [["2022-07-01", "2025-06-30"]],
        "Seiji Adachi":              [["2021-07-01", "2026-06-30"]],
        "Hitoshi Suzuki":            [["2021-07-01", "2026-06-30"]],
        "Kazuyuki Masu":             [["2024-07-01", None]],
        "Junko Koeda":               [["2025-07-01", None]],
        "Toichiro Asada":            [["2025-07-01", None]],
    },
    "ecb": {
        # Current Executive Board
        "Christine Lagarde":         [["2019-11-01", None]],
        "Luis de Guindos":           [["2018-06-01", None]],
        "Philip R. Lane":            [["2019-06-01", None]],
        "Philip Lane":               [["2019-06-01", None]],
        "Isabel Schnabel":           [["2020-01-01", None]],
        "Frank Elderson":            [["2020-12-15", None]],
        "Piero Cipollone":           [["2023-10-01", None]],
        # Recent departed
        "Luis de Guindos":           [["2018-06-01", None]],
        "Fabio Panetta":             [["2019-01-01", "2023-10-31"]],
        "Andrea Enria":              [["2018-01-01", "2023-12-31"]],
        "Yves Mersch":               [["2012-12-15", "2020-12-14"]],
        "Benoit Coeure":             [["2012-01-01", "2019-12-31"]],
        "Peter Praet":               [["2011-06-01", "2019-05-31"]],
        "Sabine Lautenschlager":     [["2014-01-27", "2019-10-31"]],
        "Luis de Guindos":           [["2018-06-01", None]],
        "Vitor Constancio":          [["2010-06-01", "2018-05-31"]],
        "Mario Draghi":              [["2011-11-01", "2019-10-31"]],
    },
}


def _load_history() -> dict[str, dict[str, list]]:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    return _FALLBACK


def was_member(bank: str, name: str, speech_date: str) -> bool:
    """
    Return True if `name` was a voting committee member of `bank` on `speech_date`.
    bank: 'boe', 'fed', or 'ecb'
    speech_date: 'YYYY-MM-DD'
    """
    history = _load_history()
    lookup_name = _normalise(bank, name)
    periods = history.get(bank, {}).get(lookup_name)
    if not periods:
        return False
    for start, end in periods:
        if speech_date >= start and (end is None or speech_date <= end):
            return True
    return False


_FED_TITLE_RE = re.compile(
    r"^(?:Chair(?:man)?(?:\s+Pro\s+Tempore)?|Vice\s+Chair(?:man)?(?:\s+for\s+Supervision)?|Governor)\s+",
    re.IGNORECASE,
)


def _normalise(bank: str, name: str) -> str:
    """Normalise a speaker name as stored in the DB to match members_history.json."""
    if bank not in ("fed",):
        return name
    # Strip title prefix (Chair, Governor, Vice Chair for Supervision, etc.)
    name = _FED_TITLE_RE.sub("", name).strip()
    # Strip middle initials: "Jerome H. Powell" → "Jerome Powell"
    name = re.sub(r"\s+[A-Z]\.\s+", " ", name).strip()
    # Strip trailing dots on last name abbreviations
    name = re.sub(r"\s+[A-Z]\.$", "", name).strip()
    return name


def current_members(bank: str) -> set[str]:
    """Return names of all currently serving members for a bank."""
    from datetime import date
    today = date.today().isoformat()
    history = _load_history()
    return {
        name for name, periods in history.get(bank, {}).items()
        if any(start <= today and end is None for start, end in periods)
    }
