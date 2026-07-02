"""
data_audit.py — automated data-quality audit for speeches.db and meetings data.

Checks whole CLASSES of defects (each user-reported bug so far was an instance
of a general pattern), so problems are found systematically instead of by
manual spot-checks:

  1. cross-date duplicates   — same speaker, near-identical body, different date
                               (BIS republishes with a lag, so same-date dedupe misses them)
  2. url variants            — same URL modulo scheme/www/trailing slash
  3. quote integrity         — every stored quote must appear verbatim in the speech text
  4. quote lean vs score     — directional speech where ALL quotes lean the opposite way
  5. dangling quotes         — quotes still starting mid-sentence (missing referent)
  6. scored on thin text     — score assigned although body < 500 chars (scrape failure?)
  7. missing justification   — scored rows without a justification
  8. translation gaps        — non-English directional speech with no body_en
  9. speaker variants        — one person stored under multiple name strings
                               (splits their scoring history / baseline)
 10. scraper freshness       — bank whose newest speech is much older than its cadence
 11. meetings sanity         — unparseable rates; decision says hold but rate moved,
                               or hike/cut with rate moving the wrong way
 12. relevance coverage      — rated, in-window speeches with relevant_to_mp unset
                               (falls back to weaker keyword filter at render time)

Usage:
    python data_audit.py            # full report
Importable:
    from data_audit import run_audit; warnings = run_audit(quiet=True)
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))


def _norm_body(b):
    return re.sub(r"\s+", " ", (b or "").lower()).strip()


def _body_hash(nb):
    return hashlib.md5(nb.encode()).hexdigest()


def _norm_url(u):
    u = (u or "").lower()
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u.rstrip("/")


class Audit:
    def __init__(self, quiet=False):
        self.quiet = quiet
        self.findings = []   # (check, count, samples)

    def report(self, check, items, fmt=lambda x: str(x), max_samples=5):
        n = len(items)
        self.findings.append((check, n, [fmt(i) for i in items[:max_samples]]))
        if not self.quiet:
            mark = "OK " if n == 0 else "!! "
            print(f"{mark}{check}: {n}")
            for i in items[:max_samples]:
                print(f"      {fmt(i)}")
            if n > max_samples:
                print(f"      ... and {n - max_samples} more")


def run_audit(quiet=False):
    a = Audit(quiet)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT url, central_bank, speaker, date, title, score, justification, "
        "body, body_en, language, evidence_quotes, relevant_to_mp FROM speeches")]
    today = date.today()

    # -- 1. cross-date duplicates ------------------------------------------------
    import difflib
    by_speaker = defaultdict(list)
    for r in rows:
        nb = _norm_body(r["body_en"] or r["body"])
        if len(nb) > 500:
            by_speaker[(r["central_bank"], r["speaker"])].append(
                (r["date"], r["url"], nb, _body_hash(nb)))
    xdate = []
    for key, items in by_speaker.items():
        items.sort()
        for i in range(len(items)):
            for j in range(i + 1, min(i + 30, len(items))):  # neighbours by date
                d1, u1, b1, h1 = items[i]
                d2, u2, b2, h2 = items[j]
                if d1 == d2:
                    continue
                dd = abs((date.fromisoformat(d2) - date.fromisoformat(d1)).days)
                if dd > 400:
                    continue
                lo, hi = sorted((len(b1), len(b2)))
                if lo / hi < 0.9:
                    continue
                if h1 == h2 or difflib.SequenceMatcher(
                        None, b1[len(b1)//4:len(b1)//4+3000],
                        b2[len(b2)//4:len(b2)//4+3000]).ratio() >= 0.92:
                    xdate.append((key[0], key[1], d1, d2, u1, u2))
    a.report("1. cross-date duplicates (same text, different date)", xdate,
             lambda x: f"{x[0]} {x[1][:22]}: {x[2]} vs {x[3]}")

    # -- 2. url variants -----------------------------------------------------------
    seen_urls = defaultdict(list)
    for r in rows:
        seen_urls[_norm_url(r["url"])].append(r["url"])
    dup_urls = [v for v in seen_urls.values() if len(v) > 1]
    a.report("2. URL-variant duplicates", dup_urls, lambda v: " | ".join(v))

    # -- 3/4/5. quote checks -------------------------------------------------------
    sys.path.insert(0, str(Path(__file__).parent))
    from rater import _normalize_for_match
    bad_quote, wrong_lean, dangling = [], [], []
    for r in rows:
        ev = r["evidence_quotes"]
        if not ev or ev == "[]":
            continue
        try:
            quotes = json.loads(ev)
        except Exception:
            bad_quote.append((r["central_bank"], r["date"], r["speaker"], "unparseable JSON"))
            continue
        text_norm = _normalize_for_match((r["body"] or "") + " " + (r["body_en"] or ""))
        leans = set()
        for q in quotes:
            qt = q.get("quote", "")
            leans.add(q.get("lean"))
            if _normalize_for_match(qt) not in text_norm:
                bad_quote.append((r["central_bank"], r["date"], r["speaker"], qt[:60]))
            elif qt and qt[0].islower() and len(qt) < 90:
                dangling.append((r["central_bank"], r["date"], r["speaker"], qt[:70]))
        s = r["score"]
        if s is not None and quotes:
            if int(s) >= 7 and leans == {"dovish"}:
                wrong_lean.append((r["central_bank"], r["date"], r["speaker"], f"score {s}, all quotes dovish"))
            if 1 <= int(s) <= 3 and leans == {"hawkish"}:
                wrong_lean.append((r["central_bank"], r["date"], r["speaker"], f"score {s}, all quotes hawkish"))
    a.report("3. quotes not found verbatim in speech", bad_quote,
             lambda x: f"{x[0]} {x[1]} {x[2][:20]}: {x[3]}")
    a.report("4. all quotes lean AGAINST the score", wrong_lean,
             lambda x: f"{x[0]} {x[1]} {x[2][:20]}: {x[3]}")
    a.report("5. short lowercase-start quotes (possible missing referent)", dangling,
             lambda x: f"{x[0]} {x[1]} {x[2][:20]}: \"{x[3]}\"")

    # -- 6/7. scoring hygiene ------------------------------------------------------
    thin = [(r["central_bank"], r["date"], r["speaker"], len(r["body"] or ""))
            for r in rows if r["score"] is not None and len((r["body"] or "").strip()) < 500]
    a.report("6. scored despite body < 500 chars", thin,
             lambda x: f"{x[0]} {x[1]} {x[2][:24]} bodylen={x[3]}")
    nojust = [(r["central_bank"], r["date"], r["speaker"])
              for r in rows if r["score"] is not None and not (r["justification"] or "").strip()]
    a.report("7. scored but no justification", nojust, lambda x: f"{x[0]} {x[1]} {x[2][:24]}")

    # -- 8. translation gaps ---------------------------------------------------------
    trgap = [(r["central_bank"], r["date"], r["speaker"])
             for r in rows
             if r["language"] and r["language"] != "en" and r["score"] is not None
             and ((int(r["score"]) >= 7) or (1 <= int(r["score"]) <= 3))
             and not (r["body_en"] or "").strip()]
    a.report("8. non-English directional speech without body_en", trgap,
             lambda x: f"{x[0]} {x[1]} {x[2][:24]}")

    # -- 9. speaker name variants ------------------------------------------------------
    try:
        from speaker_norm import normalize_speaker
        variants = defaultdict(set)
        for r in rows:
            variants[(r["central_bank"], normalize_speaker(r["speaker"] or "", r["central_bank"]))].add(r["speaker"])
        multi = [(k[0], k[1], sorted(v)) for k, v in variants.items() if len(v) > 1]
        a.report("9. speaker name variants (informational — normalize_speaker resolves these "
                 "at render/baseline time; raw names kept in DB by design)", multi,
                 lambda x: f"{x[0]}: {x[2]}")
    except Exception as e:
        a.report("9. speaker-variant check failed to run", [str(e)])

    # -- 10. scraper freshness -----------------------------------------------------------
    stale = []
    for bank, in conn.execute("SELECT DISTINCT central_bank FROM speeches"):
        ds = [r[0] for r in conn.execute(
            "SELECT date FROM speeches WHERE central_bank=? AND date>=? ORDER BY date",
            (bank, (today - timedelta(days=540)).isoformat()))]
        if len(ds) < 4:
            continue
        gaps = [(date.fromisoformat(ds[i+1]) - date.fromisoformat(ds[i])).days
                for i in range(len(ds)-1)]
        gaps.sort()
        median_gap = gaps[len(gaps)//2] or 1
        idle = (today - date.fromisoformat(ds[-1])).days
        if idle > max(21, 4 * median_gap):
            stale.append((bank, ds[-1], idle, median_gap))
    a.report("10. bank possibly stale (scraper broken?)", stale,
             lambda x: f"{x[0]}: newest {x[1]} ({x[2]}d idle, median gap {x[3]}d)")

    # -- 11. meetings sanity ---------------------------------------------------------------
    meet_issues = []
    try:
        from meetings import get_meetings
        from report_frb import _rate_to_float
        for bank, in conn.execute("SELECT DISTINCT central_bank FROM speeches"):
            ms = get_meetings(bank) or []
            prev = None
            for m in ms:
                if m.get("decision") == "upcoming":
                    continue
                rate = _rate_to_float(m.get("rate", ""))
                if m.get("rate") and rate is None:
                    meet_issues.append((bank, m["date"], f"unparseable rate {m['rate']!r}"))
                if rate is not None and prev is not None:
                    dec = m.get("decision")
                    if dec == "hold" and abs(rate - prev) > 1e-9:
                        meet_issues.append((bank, m["date"], f"hold but rate moved {prev}->{rate}"))
                    if dec == "hike" and rate <= prev:
                        meet_issues.append((bank, m["date"], f"hike but rate {prev}->{rate}"))
                    if dec == "cut" and rate >= prev:
                        meet_issues.append((bank, m["date"], f"cut but rate {prev}->{rate}"))
                if rate is not None:
                    prev = rate
    except Exception as e:
        meet_issues.append(("(audit)", "", f"meetings check failed: {e}"))
    a.report("11. meetings data inconsistencies", meet_issues,
             lambda x: f"{x[0]} {x[1]}: {x[2]}")

    # -- 12. relevance coverage in-window ------------------------------------------------------
    cut5y = date(today.year - 5, today.month, today.day).isoformat()
    nocls = [(r["central_bank"], r["date"], r["speaker"])
             for r in rows
             if r["score"] is not None and r["date"] >= cut5y and r["relevant_to_mp"] is None]
    a.report("12. rated in-window but relevant_to_mp unset (keyword fallback)", nocls,
             lambda x: f"{x[0]} {x[1]} {x[2][:24]}")

    conn.close()
    total = sum(n for _, n, _ in a.findings)
    if not quiet:
        print(f"\n=== AUDIT SUMMARY: {total} finding(s) across "
              f"{sum(1 for _, n, _ in a.findings if n)} of {len(a.findings)} checks ===")
    return a.findings


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run_audit()
