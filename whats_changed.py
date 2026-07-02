"""
"What changed" digest — the daily macro read.

The dashboard is a reference you visit; this is the delta you consume each morning:
new rate decisions, fresh policy-relevant speeches (esp. directional ones), where each
bank's stance sits right now, the cross-bank divergence that drives FX/rates trades, and
the meetings coming up. Reads the DB only; prints a digest and returns structured sections
(so it can be posted to Slack from the daily pipeline).

Run:  python whats_changed.py            # default windows
      python whats_changed.py 7 21       # speeches window, decisions window (days)
"""
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))


def _tone(s):
    return "Off-topic" if s == 0 else "Dovish" if s <= 3 else "Neutral" if s <= 6 else "Hawkish"


def _stance(avg):
    if avg < 4:
        return "Dovish" if avg < 2 else "Leaning dovish"
    if avg > 6:
        return "Hawkish" if avg > 8 else "Leaning hawkish"
    return "Neutral"


def gather(days_speeches=7, days_decisions=21, days_stance=45, days_upcoming=14, db_path=DB_PATH):
    conn = sqlite3.connect(str(db_path), timeout=30)
    today = date.today()
    ti = today.isoformat()
    rel = "(relevant_to_mp IS NULL OR relevant_to_mp=1)"

    def ago(n):
        return (today - timedelta(days=n)).isoformat()

    decisions = conn.execute(
        "SELECT bank, date, decision, rate, label FROM meetings "
        "WHERE decision!='upcoming' AND date>=? AND date<=? ORDER BY date DESC",
        (ago(days_decisions), ti)).fetchall()

    speeches = conn.execute(
        f"SELECT central_bank, date, speaker, score, COALESCE(title_en,title) "
        f"FROM speeches WHERE score>0 AND {rel} AND date>=? AND date<=? ORDER BY date DESC",
        (ago(days_speeches), ti)).fetchall()

    stance = conn.execute(
        f"SELECT central_bank, AVG(score)*1.0, COUNT(*) FROM speeches "
        f"WHERE score>0 AND {rel} AND date>=? GROUP BY central_bank "
        f"HAVING COUNT(*)>=2 ORDER BY 2 DESC",
        (ago(days_stance),)).fetchall()

    upcoming = conn.execute(
        "SELECT bank, date, label FROM meetings WHERE decision='upcoming' "
        "AND date>=? AND date<=? ORDER BY date",
        (ti, (today + timedelta(days=days_upcoming)).isoformat())).fetchall()
    conn.close()
    return {"decisions": decisions, "speeches": speeches, "stance": stance,
            "upcoming": upcoming, "windows": (days_speeches, days_decisions, days_stance, days_upcoming)}


def render(d) -> str:
    ws, wd, wst, wu = d["windows"]
    L = [f"CENTRAL-BANK TRACKER — WHAT CHANGED  ({date.today():%d %b %Y})", "=" * 58, ""]

    L.append(f"RATE DECISIONS (last {wd}d)")
    if d["decisions"]:
        for bank, dt, dec, rate, label in d["decisions"]:
            arrow = "▲" if dec == "hike" else "▼" if dec == "cut" else "—"
            L.append(f"  {dt}  {arrow} {bank:16} {label or dec} → {rate or '?'}")
    else:
        L.append("  (none)")
    L.append("")

    L.append(f"NEW POLICY-RELEVANT SPEECHES (last {ws}d)")
    if d["speeches"]:
        by_bank = {}
        for cb, dt, sp, sc, title in d["speeches"]:
            by_bank.setdefault(cb, []).append((dt, sp, sc, title))
        for cb in sorted(by_bank, key=lambda k: -len(by_bank[k])):
            items = by_bank[cb]
            L.append(f"  {cb} ({len(items)}):")
            for dt, sp, sc, title in items[:4]:
                flag = "  «directional»" if sc <= 3 or sc >= 7 else ""
                L.append(f"     {dt}  {sc}/10 {_tone(sc):8} {sp.split()[-1]:12} {(title or '')[:44]}{flag}")
            if len(items) > 4:
                L.append(f"     … +{len(items)-4} more")
    else:
        L.append("  (none)")
    L.append("")

    L.append(f"CURRENT STANCE BY BANK  (avg of relevant speeches, last {wst}d)")
    if d["stance"]:
        for cb, avg, n in d["stance"]:
            L.append(f"  {avg:4.1f}/10  {_stance(avg):15} {cb:16} ({n} speeches)")
        hawk = d["stance"][0]
        dove = d["stance"][-1]
        if len(d["stance"]) >= 2 and (hawk[1] - dove[1]) >= 1.5:
            L.append("")
            L.append(f"  ⇄ DIVERGENCE: {hawk[0]} ({hawk[1]:.1f}, {_stance(hawk[1]).lower()}) "
                     f"vs {dove[0]} ({dove[1]:.1f}, {_stance(dove[1]).lower()}) "
                     f"— {hawk[1]-dove[1]:.1f}pt spread")
    else:
        L.append("  (insufficient data)")
    L.append("")

    L.append(f"UPCOMING MEETINGS (next {wu}d)")
    if d["upcoming"]:
        for bank, dt, label in d["upcoming"]:
            L.append(f"  {dt}  {bank}")
    else:
        L.append("  (none scheduled / no calendar data)")
    return "\n".join(L)


def main():
    args = [int(a) for a in sys.argv[1:3]] if len(sys.argv) > 1 else []
    kw = {}
    if len(args) >= 1:
        kw["days_speeches"] = args[0]
    if len(args) >= 2:
        kw["days_decisions"] = args[1]
    print(render(gather(**kw)))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
