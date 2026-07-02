"""
BIS-backed rate-decision source for banks whose own sites are JS-rendered / unscrapeable.

The plain-HTTP + LLM extractor (meetings_extractor.py) silently fails on CBRT, BNR and
NBP — their decision pages return a JavaScript shell, so the extractor got no content and
left stale (and, for CBRT, outright WRONG) data in place for a year.

The BIS "central bank policy rates" dataset (WS_CBPOL) is a clean, authoritative, machine-
readable series covering these banks. We pull the daily policy-rate series and derive each
rate-CHANGE as a decision (date, new rate, hike/cut, bp). Holds aren't in the series (BIS
only records the rate level), but the changes are the tradeable events and they're correct
and current — far better than a fragile scrape or a hand-typed seed.

    from meetings_bis import sync_bank_from_bis
    sync_bank_from_bis("CBRT")   # rebuilds CBRT's non-locked meeting rows from BIS

CLI:  python meetings_bis.py            # sync all BIS-backed banks
      python meetings_bis.py CBRT       # one bank
"""
import csv
import io
import math
import sys
from datetime import datetime

import requests

from meetings_store import _conn, upsert_meeting

# DB bank name -> BIS REF_AREA (ISO-2). Extend as needed.
BIS_AREA = {"CBRT": "TR", "BNR": "RO", "NBP": "PL"}

_UA = {"User-Agent": "Mozilla/5.0 (cb-reports meetings sync)"}
_CBPOL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.{area}?startPeriod={start}&format=csv"


def _num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def bis_daily_series(area: str, start: str = "2020-01") -> list:
    """Return sorted [(iso_date, rate_float)] of the daily policy rate for a REF_AREA."""
    url = _CBPOL.format(area=area, start=start)
    r = requests.get(url, headers=_UA, timeout=60)
    r.raise_for_status()
    rows = csv.DictReader(io.StringIO(r.text))
    pts = [(row["TIME_PERIOD"], _num(row.get("OBS_VALUE"))) for row in rows]
    return sorted((d, v) for d, v in pts if v is not None)


def bis_decisions(area: str, start: str = "2020-01") -> tuple:
    """Derive rate-change decisions from the series. Returns (decisions, latest_point)."""
    pts = bis_daily_series(area, start)
    out, prev = [], None
    for d, v in pts:
        if prev is not None and abs(v - prev) > 1e-9:
            dec = "hike" if v > prev else "cut"
            out.append({"date": d, "decision": dec,
                        "rate": f"{v:.2f}%", "bp_change": round((v - prev) * 100)})
        prev = v
    return out, (pts[-1] if pts else None)


def _label(decision: str, bp: int) -> str:
    sign = "+" if decision == "hike" else "−"  # U+2212
    return f"{sign}{abs(bp)}bp {decision}"


def sync_bank_from_bis(bank: str, start: str = "2019-01", verbose: bool = True) -> int:
    """Rebuild `bank`'s meeting rows from BIS, but ONLY for the period after its last
    manually-locked (curated) row — so curated history is fully preserved and there's
    no overlap. Deletes only non-locked rows in that recent window, then inserts the
    BIS-derived rate changes. Returns the number of decisions written."""
    if bank not in BIS_AREA:
        raise ValueError(f"No BIS REF_AREA mapping for {bank}")
    area = BIS_AREA[bank]
    decisions, latest = bis_decisions(area, start)

    conn = _conn()
    cutoff = conn.execute(
        "SELECT MAX(date) FROM meetings WHERE bank=? AND locked=1", (bank,)).fetchone()[0]
    if cutoff:
        removed = conn.execute(
            "DELETE FROM meetings WHERE bank=? AND locked=0 AND date>?", (bank, cutoff)).rowcount
        decisions = [d for d in decisions if d["date"] > cutoff]
    else:
        removed = conn.execute(
            "DELETE FROM meetings WHERE bank=? AND locked=0", (bank,)).rowcount
    conn.commit()
    conn.close()

    src_url = f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.{area}"
    for d in decisions:
        upsert_meeting(bank, d["date"], d["decision"], rate=d["rate"],
                       bp_change=d["bp_change"], label=_label(d["decision"], d["bp_change"]),
                       source="bis", source_url=src_url)
    if verbose:
        last = f"{latest[1]:.2f}% on {latest[0]}" if latest else "n/a"
        print(f"  {bank}: kept curated rows ≤{cutoff or 'n/a'}; cleared {removed} non-locked "
              f"row(s) after; wrote {len(decisions)} BIS decision(s); latest rate {last}")
    return len(decisions)


def main():
    banks = [sys.argv[1]] if len(sys.argv) > 1 else list(BIS_AREA)
    print("Syncing rate decisions from BIS ...")
    for b in banks:
        try:
            sync_bank_from_bis(b)
        except Exception as e:
            print(f"  ! {b}: {e}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
