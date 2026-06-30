"""
Normalize central bank speaker names for display and grouping.

Strips title prefixes so that the same person is not split into multiple
speakers when their title changes (e.g. Governor → Vice Chair).
Applied at report-generation time; the raw name is kept in the database.
"""

import re

# Fed titles that precede the actual name
_FED_TITLE_RE = re.compile(
    r"^(?:"
    r"Vice\s+Chair(?:man)?\s+for\s+Supervision(?:\s+and\s+Chair\s+of\s+the\s+Financial\s+Stability\s+Board)?\s+"
    r"|Vice\s+Chair(?:man)?\s+"
    r"|Chair(?:man)?(?:\s+Pro\s+Tempore)?\s+"
    r"|Governor\s+"
    r"|President\s+"
    r")",
    re.IGNORECASE,
)

# BoE: strip UK honorary prefixes
_BOE_TITLE_RE = re.compile(
    r"^(?:Sir|Dame|Lord|Lady|Dr\.?|Prof(?:essor)?\.?)\s+",
    re.IGNORECASE,
)

# Manual overrides for names that differ beyond just a title prefix
# (central_bank, raw_name) -> canonical_name
_ALIASES: dict[tuple[str, str], str] = {
    # Missing period after middle initial
    ("Bank of England", "Catherine L Mann"): "Catherine L. Mann",
    # Middle initial present in some records, absent in others
    ("Bank of England", "Carolyn A Wilkins"): "Carolyn Wilkins",
    # BCB: full legal names → canonical short names (mirror scraper_bcb._BCB_ALIASES)
    ("BCB", "Renato Dias De Brito Gomes"): "Renato Gomes",
    ("BCB", "Renato Dias de Brito Gomes"): "Renato Gomes",
    ("BCB", "Nilton José Aquino Moreira"): "Nilton David",
    ("BCB", "Nilton Jose Aquino Moreira"): "Nilton David",
    ("BCB", "Diogo Abry Guillen"): "Diogo Guillen",
    ("BCB", "Otávio Damaso"): "Otavio Ribeiro Damaso",
    ("BCB", "Otavio Damaso"): "Otavio Ribeiro Damaso",
    ("BCB", "Ailton Aquino"): "Ailton Santos",
    ("BCB", "Ailton Aquino Santos"): "Ailton Santos",
    ("BCB", "Ailton de Aquino"): "Ailton Santos",
    ("BCB", "Mauricio Moura"): "Maurício Costa de Moura",
    ("BCB", "Maurício Moura"): "Maurício Costa de Moura",
    ("BCB", "Mauricio Costa de Moura"): "Maurício Costa de Moura",
    ("BCB", "Sergio Gouvea"): "Sérgio Gouvêa",
    ("BCB", "Sergio Gouvêa"): "Sérgio Gouvêa",
    ("BCB", "Sérgio Gouvea"): "Sérgio Gouvêa",
}


def normalize_speaker(speaker: str, central_bank: str) -> str:
    """Return the canonical display name for a speaker.

    Strips title prefixes (Governor, Vice Chair for Supervision, Sir, etc.)
    so that the same person is grouped together across title changes.
    """
    key = (central_bank, speaker)
    if key in _ALIASES:
        return _ALIASES[key]

    if central_bank == "Federal Reserve":
        speaker = _FED_TITLE_RE.sub("", speaker).strip()
    elif central_bank == "Bank of England":
        speaker = _BOE_TITLE_RE.sub("", speaker).strip()

    return speaker
