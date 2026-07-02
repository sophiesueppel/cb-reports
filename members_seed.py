"""
STAGING seed of dated committee membership for the 7 banks that still use hardcoded
speaker lists (BCB, CBRT, Riksbank, SARB, CNB, NBP, BNR).

Purpose: migrate these banks off the frozen `ALL_X` sets in their scrapers onto the
same dynamic, date-aware system the Fed/ECB/BoE use (`membership.was_member`), and
give `check_members` a source page per bank to auto-detect changes going forward.

NOT yet wired in. Nothing here reads or writes the live DB or members_history.json.
Integration steps (do later): (1) reconcile these canonical names against the actual
speaker strings in the DB, (2) merge SEED into data/members_history.json, (3) switch
each report wrapper's member_filter to was_member(<key>, ...), (4) add per-bank
scrapers to check_members using SCRAPE_SOURCES.

Data compiled 2026-07-02 from official sources (see SCRAPE_SOURCES + agent research).
Dates: null end = still serving. Dates marked "~approx" in comments are best-known
(usually pre-2022/pre-2024 cohort START dates); END dates and departures are firm.
Committee = the full voting rate-setting body, NOT just the governor — that is the
whole point (a new deputy/member must be tracked or we silently drop their speeches).
"""

# key -> { canonical_name: [[start, end_or_None], ...] }
SEED = {
    # ── Banco Central do Brasil — Copom = President + 8 Directors (all 9 vote) ──
    "bcb": {
        "Gabriel Muricca Galípolo":            [["2023-07-01", "2024-12-31"], ["2025-01-01", None]],  # Dir. Mon. Policy → President
        "Diogo Abry Guillen":                  [["2022-04-27", None]],
        "Renato Dias de Brito Gomes":          [["2022-04-27", None]],
        "Ailton de Aquino Santos":             [["2023-07-12", None]],
        "Rodrigo Alves Teixeira":              [["2024-01-02", None]],
        "Paulo Picchetti":                     [["2024-01-02", None]],
        "Nilton José Schneider David":         [["2025-01-01", None]],
        "Gilneu Francisco Astolfi Vivan":      [["2025-01-01", None]],
        "Izabela Moreira Correa":              [["2025-01-01", None]],
        "Roberto de Oliveira Campos Neto":     [["2019-02-28", "2024-12-31"]],
        "Otávio Ribeiro Damaso":               [["2016-06-09", "2024-12-31"]],  # start ~approx
        "Carolina de Assis Barros":            [["2021-01-01", "2024-12-31"]],  # start ~approx
        "Maurício Costa de Moura":             [["2019-05-01", "2023-12-31"]],  # start ~approx
        "Fernanda Magalhães Rumenos Guardado": [["2021-01-01", "2023-12-31"]],  # start ~approx
        "Bruno Serra Fernandes":               [["2019-02-25", "2023-03-23"]],  # start ~approx
        "Fábio Kanczuk":                       [["2019-02-25", "2021-12-31"]],  # start ~approx
        "Paulo Sérgio Neves de Souza":         [["2019-03-01", "2023-07-11"]],  # Dir. de Fiscalização (Copom voter); both ~approx
    },
    # ── CBRT / TCMB — Monetary Policy Committee (PPK): Governor + Deputies + Board seat ──
    "cbrt": {
        "Fatih Karahan":            [["2023-07-28", "2024-02-02"], ["2024-02-03", None]],  # Dep.Gov → Governor
        "Hatice Karahan":           [["2023-07-28", None]],   # Deputy Governor (NOT the same person as Fatih)
        "Fatma Özkul":              [["2026-02-02", None]],   # Deputy Governor (prior PPK member seat before)
        "Gazi İshak Kara":          [["2026-02-02", None]],   # Deputy Governor (prior PPK member seat before)
        "Yusuf Emre Akgündüz":      [["2026-05-09", None]],   # Deputy Governor
        "Elif Haykır Hobikoğlu":    [["2023-05-01", None]],   # Board member on PPK; start ~approx
        "Murat Uysal":              [["2019-07-06", "2020-11-07"]],  # Governor
        "Naci Ağbal":               [["2020-11-07", "2021-03-20"]],  # Governor
        "Şahap Kavcıoğlu":          [["2021-03-20", "2023-06-08"]],  # Governor
        "Hafize Gaye Erkan":        [["2023-06-08", "2024-02-02"]],  # Governor
        "Osman Cevdet Akçay":       [["2023-07-28", "2026-04-30"]],  # Deputy Governor; end ~approx
    },
    # ── Sveriges Riksbank — Executive Board (5, all vote) ──
    "riksbank": {
        "Erik Thedéen":        [["2023-01-01", None]],   # Governor
        "Aino Bunge":          [["2022-12-01", None]],   # First Deputy Governor
        "Per Jansson":         [["2012-01-01", None]],   # Deputy Governor (continuous)
        "Anna Seim":           [["2024-05-22", None]],   # Deputy Governor
        "Göran Hjelm":         [["2026-03-02", None]],   # Deputy Governor
        "Stefan Ingves":       [["2006-01-01", "2022-12-31"]],  # Governor; start ~approx
        "Cecilia Skingsley":   [["2013-05-22", "2022-08-15"]],
        "Martin Flodén":       [["2013-05-22", "2024-05-21"]],  # end ~approx
        "Henry Ohlsson":       [["2015-01-12", "2023-06-30"]],
        "Anna Breman":         [["2019-12-01", "2025-11-30"]],
    },
    # ── South African Reserve Bank — Monetary Policy Committee (up to 7) ──
    "sarb": {
        "Lesetja Kganyago":    [["2014-11-09", None]],   # Governor & chair
        "Rashad Cassim":       [["2019-08-01", None]],   # Deputy Governor
        "Nomfundo Tshazibana": [["2019-08-01", None]],   # Deputy Governor (aka "Fundi")
        "Mampho Modise":       [["2024-04-01", None]],   # Deputy Governor
        "David Fowkes":        [["2024-01-12", None]],   # Adviser on MPC
        "Konstantin Makrelov": [["2026-01-01", None]],   # Chief Economist; start ~approx
        "Kuben Naidoo":        [["2015-11-01", "2023-12-31"]],  # both dates ~approx
        "Christopher Loewald": [["2011-01-01", "2026-02-28"]],  # both dates ~approx
    },
    # ── Czech National Bank — Bank Board (7, all vote) ──
    "cnb": {
        "Aleš Michl":        [["2018-12-01", None]],   # member 2018; Governor since 2022-07-01
        "Eva Zamrazilová":   [["2022-07-01", None]],   # Vice-Governor
        "Jan Frait":         [["2022-07-01", None]],   # Vice-Governor since 2023-02-13
        "Karina Kubelková":  [["2022-07-01", None]],
        "Jan Kubíček":       [["2023-02-13", None]],
        "Jan Procházka":     [["2023-02-13", None]],
        "Jakub Seidler":     [["2024-12-01", None]],
        "Jiří Rusnok":       [["2016-07-01", "2022-06-30"]],  # Governor; start ~approx
        "Vojtěch Benda":     [["2018-07-01", "2022-06-30"]],  # start ~approx
        "Tomáš Nidetzký":    [["2017-07-01", "2022-06-30"]],  # start ~approx
        "Marek Mora":        [["2017-12-01", "2023-02-12"]],  # start ~approx
        "Oldřich Dědek":     [["2017-02-13", "2023-02-12"]],  # start ~approx
        "Tomáš Holub":       [["2018-12-01", "2024-11-30"]],
    },
    # ── National Bank of Poland — Monetary Policy Council (RPP), 10 members ──
    "nbp": {
        "Adam Glapiński":       [["2016-06-21", None]],   # Chair / NBP President
        "Ireneusz Dąbrowski":   [["2022-02-18", None]],
        "Henryk Wnorowski":     [["2022-02-21", None]],
        "Marcin Zarzecki":      [["2025-12-22", None]],   # replaced Kochalski — PRESS-sourced, re-confirm
        "Wiesław Janczyk":      [["2022-02-09", None]],
        "Iwona Duda":           [["2022-10-07", None]],
        "Gabriela Masłowska":   [["2022-10-07", None]],
        "Ludwik Kotecki":       [["2022-01-26", None]],
        "Przemysław Litwiniuk": [["2022-01-26", None]],
        "Joanna Tyrowicz":      [["2022-09-07", None]],
        "Cezary Kochalski":     [["2019-12-21", "2025-12-20"]],
        "Rafał Sura":           [["2016-11-16", "2022-07-21"]],
        "Grażyna Ancyparowicz": [["2016-01-25", "2022-02-09"]],  # start ~approx
        "Eugeniusz Gatnar":     [["2016-01-25", "2022-01-25"]],  # start ~approx
        "Łukasz Hardt":         [["2016-02-17", "2022-02-17"]],  # start ~approx
        "Jerzy Kropiwnicki":    [["2016-01-25", "2022-01-25"]],  # start ~approx
        "Eryk Łon":             [["2016-02-09", "2022-02-09"]],  # start ~approx
        "Kamil Zubelewicz":     [["2016-02-17", "2022-02-17"]],  # start ~approx
        "Jerzy Żyżyński":       [["2016-03-30", "2022-03-30"]],  # start ~approx
    },
    # ── National Bank of Romania — Board of Directors (9, all vote) ──
    "bnr": {
        "Mugur Constantin Isărescu": [["2000-02-01", None]],   # Governor/chair (earlier tenure pre-window omitted)
        "Leonardo Badea":            [["2021-10-14", None]],   # First Deputy Governor; start ~approx
        "Florin Georgescu":          [["2009-10-12", None]],   # Deputy Governor; start ~approx
        "Cosmin-Ștefan Marinescu":   [["2024-10-11", None]],   # Deputy Governor
        "Csaba Bálint":              [["2019-10-11", None]],   # non-executive
        "Cristian Popa":             [["2019-10-11", None]],   # non-executive
        "Aura-Gabriela Socol":       [["2024-10-11", None]],   # non-executive
        "Roberta Alma Anastase":     [["2024-10-11", None]],   # non-executive
        "Alexandru Nazare":          [["2024-10-11", None]],   # non-exec; SELF-SUSPENDED ~2025-06 (Min. Finance)
        "Liviu Voinea":              [["2014-10-01", "2021-10-13"]],  # ~approx
        "Eugen Nicolăescu":          [["2019-10-11", "2024-10-10"]],
        "Gheorghe Gherghina":        [["2019-10-11", "2024-10-10"]],
        "Dan Radu Rușanu":           [["2019-10-11", "2024-10-10"]],
        "Virgil-Daniel Stoenescu":   [["2019-10-11", "2024-10-10"]],
    },
}

# Per-bank source page + how an auto-check should read it.
# render: "static" (plain HTTP + BeautifulSoup) | "js" (needs headless) | "pdf"
SCRAPE_SOURCES = {
    "bcb":      {"url": "https://www.bcb.gov.br/en/publications/copomminutes", "lang": "en",
                 "render": "pdf", "notes": "Org page is a JS SPA; use Copom Minutes PDF 'Present:' roster instead."},
    "cbrt":     {"url": "https://www.tcmb.gov.tr/wps/wcm/connect/tr/tcmb+tr/main+menu/banka+hakkinda/kurumsal+yapi/yonetim/para+politikasi+kurulu",
                 "lang": "tr", "render": "static", "notes": "TR PPK page returns the 6 names in served HTML; EN page has no names."},
    "riksbank": {"url": "https://www.riksbank.se/en-gb/about-the-riksbank/organisation/the-executive-board/", "lang": "en",
                 "render": "js", "notes": "JS-rendered; fallback = Annual Report PDF + press-release feed for 'new Deputy Governor'."},
    "sarb":     {"url": "https://www.resbank.co.za/en/home/what-we-do/monetary-policy/monetary-policy-committee", "lang": "en",
                 "render": "static", "notes": "Roster static HTML; appointment dates live in bios page."},
    "cnb":      {"url": "https://www.cnb.cz/en/about_cnb/bank-board/current-members-of-the-cnb-bank-board/", "lang": "en",
                 "render": "static", "notes": "Scrape the current-members SUBPAGE (overview page lacks names); dates on profile pages."},
    "nbp":      {"url": "https://nbp.pl/en/monetary-policy/monetary-policy-council/", "lang": "en",
                 "render": "js", "notes": "JS + Imperva anti-bot. Fallback = pl.wikipedia.org/wiki/Rada_Polityki_Pieniężnej (static)."},
    "bnr":      {"url": "https://www.bnr.ro/en/1389-the-board-of-directors", "lang": "en",
                 "render": "js", "notes": "JS-only. Changes ~once per 5-yr mandate; seed from Parliament decision, JS-render only to detect change."},
}


# ---------------------------------------------------------------------------
# Name matching: fold DB speaker strings to canonical committee members
# ---------------------------------------------------------------------------
# The DB stores names in varied forms (de-accented, short, nicknames). These
# ALIASES list the *extra* DB-form spellings that should map to a seed member,
# beyond what accent-folding already catches. Each string is an accepted alias
# for a member already in SEED[bank] (used for the membership filter).
ALIASES = {
    "bcb": [
        "Gabriel Galípolo", "Renato Gomes", "Diogo Guillen", "Ailton Santos",
        "Rodrigo Teixeira", "Nilton David", "Roberto Campos Neto",
        "Fernanda Guardado", "Paulo Souza",
    ],
    "sarb": ["Fundi Tshazibana"],           # nickname for Nomfundo Tshazibana
    "bnr":  ["Mugur Isarescu"],             # short form of Mugur Constantin Isărescu
    "cbrt": [], "riksbank": [], "cnb": [], "nbp": [],
}

# Non-voting officials we deliberately TRACK anyway because they deliver core
# monetary-policy content (kept separate from SEED so the voting roster stays clean).
EXTRA_TRACKED = {
    "cnb": ["Petr Král", "Luboš Komárek"],  # present the CNB Monetary Policy Report forecast
}

import re as _re
import unicodedata as _ud

# Turkish letters NFKD doesn't fold to ASCII the way we need.
_TURKISH = {"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g"}
_TITLE_RE = _re.compile(
    r"^(governor|dr\.?|prof\.?( dr\.?)?|mr\.?|ms\.?|mrs\.?|sir|dame|"
    r"deputy governor|vice.?governor|president|acad\.?)\s+", _re.I)


def _fold(s: str) -> str:
    """Normalise a name for matching: Turkish letters, strip accents, drop titles,
    collapse whitespace, lowercase."""
    if not s:
        return ""
    for a, b in _TURKISH.items():
        s = s.replace(a, b)
    s = _ud.normalize("NFKD", s)
    s = "".join(ch for ch in s if not _ud.combining(ch))
    s = _TITLE_RE.sub("", s.strip())
    return _re.sub(r"\s+", " ", s).strip().lower()


# Precompute the accepted folded-name set per bank (seed members + aliases).
_VALID = {
    key: ({_fold(n) for n in names}
          | {_fold(a) for a in ALIASES.get(key, [])}
          | {_fold(e) for e in EXTRA_TRACKED.get(key, [])})
    for key, names in SEED.items()
}


def is_member(bank_key: str, speaker: str, date: str = None) -> bool:
    """True if `speaker` is (or was) a voting member of the bank's rate-setting body.
    Matches by folded identity (accent/title/nickname-robust). `date` is accepted for
    API symmetry with was_member but not currently used to bound the match."""
    return _fold(speaker) in _VALID.get(bank_key, set())


def current_members(bank_key: str) -> list:
    """Canonical names of members with an open (end=None) tenure — for 'active' display."""
    return [n for n, periods in SEED.get(bank_key, {}).items()
            if any(p[1] is None for p in periods)]
