"""
Content-based de-duplication for speeches.db.

The same speech sometimes lands in the DB more than once — scraped from both a
native site and the BIS mirror, or under two URL variants, or re-scraped at
different completeness. These share a (central_bank, speaker, date) AND either an
identical body or the same title. This collapses each such cluster to ONE row,
keeping the most complete/enriched copy.

IMPORTANT: speeches that merely share a speaker+date but have DIFFERENT titles and
bodies are genuinely distinct speeches and are always kept.

Keeper preference (highest wins): has a score > has topic_scores/evidence_quotes >
has body_en > native URL over bis.org > longer body.

Usage:
    python dedupe_speeches.py            # dry run — report only
    python dedupe_speeches.py --apply    # actually delete the duplicate rows
Also importable: dedupe_speeches(apply=True) -> number of rows removed.
"""
import hashlib
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(os.environ.get("CB_DB_PATH", "data/speeches.db"))


def _norm_title(t: str) -> str:
    t = (t or "").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _body_sig(b: str) -> str:
    b = (b or "").strip()
    if not b:
        return ""
    nb = re.sub(r"\s+", " ", b.lower())
    return f"{len(nb)}:{hashlib.md5(nb.encode()).hexdigest()[:12]}"


def _keeper_score(r: sqlite3.Row) -> int:
    body = r["body_en"] or r["body"] or ""
    s = 0
    if r["score"] is not None:
        s += 100_000
    if r["topic_scores"]:
        s += 20_000
    if r["evidence_quotes"]:
        s += 20_000
    if r["body_en"]:
        s += 10_000
    if "bis.org" not in (r["url"] or ""):
        s += 5_000
    s += len(body)
    return s


_TITLE_LEN_RATIO = 0.5  # only merge same-title rows if bodies are of similar length


def _same_speech(a, b) -> bool:
    """Two rows are the same speech if their bodies are byte-identical, OR they share
    a normalized title AND their bodies are of similar length (guards against distinct
    docs that happen to reuse a generic title, e.g. 'Opening Remarks')."""
    ba, bb = (a["body_en"] or a["body"] or ""), (b["body_en"] or b["body"] or "")
    sa, sb = _body_sig(ba), _body_sig(bb)
    if sa and sa == sb:
        return True
    ta, tb = _norm_title(a["title"]), _norm_title(b["title"])
    if ta and ta == tb:
        if not ba or not bb:
            return True
        lo, hi = sorted((len(ba), len(bb)))
        return hi > 0 and lo / hi >= _TITLE_LEN_RATIO
    return False


def _clusters(group: list) -> list:
    """Cluster rows in one (bank,speaker,date) group into same-speech sets."""
    parent = list(range(len(group)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    for i in range(len(group)):
        for j in range(i + 1, len(group)):
            if _same_speech(group[i], group[j]):
                union(i, j)

    out = defaultdict(list)
    for i, r in enumerate(group):
        out[find(i)].append(r)
    return list(out.values())


def dedupe_speeches(apply: bool = False, verbose: bool = True) -> int:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    sel = ["url", "central_bank", "speaker", "date", "title", "score", "body"]
    for opt in ("body_en", "topic_scores", "evidence_quotes"):
        if opt in cols:
            sel.append(opt)
    rows = conn.execute(f"SELECT {', '.join(sel)} FROM speeches").fetchall()

    # backfill missing optional keys so _keeper_score/_clusters can index safely
    def g(r, k):
        try:
            return r[k]
        except (IndexError, KeyError):
            return None

    class R(dict):
        __getitem__ = dict.get

    norm_rows = [R({k: g(r, k) for k in ("url", "central_bank", "speaker", "date",
                                          "title", "score", "body", "body_en",
                                          "topic_scores", "evidence_quotes")}) for r in rows]

    groups = defaultdict(list)
    for r in norm_rows:
        groups[(r["central_bank"], r["speaker"], r["date"])].append(r)

    to_delete = []
    skipped = []
    for key, grp in groups.items():
        if len(grp) < 2:
            continue
        for cluster in _clusters(grp):
            if len(cluster) < 2:
                continue
            urls = [c["url"] or "" for c in cluster]
            # Testimony/speech crossovers touch the Fed testimony feature and can
            # score differently despite identical text — leave for manual review.
            if any("/testimony/" in u for u in urls) and any("/speech/" in u for u in urls):
                skipped.append(cluster)
                continue
            cluster.sort(key=_keeper_score, reverse=True)
            keeper, losers = cluster[0], cluster[1:]
            for lo in losers:
                to_delete.append((keeper, lo))

    if verbose and skipped:
        print(f"Skipped {len(skipped)} testimony/speech crossover cluster(s) for manual review:")
        for cl in skipped:
            for x in cl:
                print(f"    {x['central_bank']} {x['date']} {str(x['speaker'])[:20]} score={x['score']} url=...{str(x['url'])[-45:]}")

    if verbose:
        print(f"Duplicate rows to remove: {len(to_delete)}")
        for keeper, lo in to_delete[:40]:
            print(f"  DROP {lo['central_bank']:6} {lo['date']} {str(lo['speaker'])[:20]:20} "
                  f"score={lo['score']} url=...{str(lo['url'])[-40:]}")
            print(f"    keep url=...{str(keeper['url'])[-40:]} (score={keeper['score']})")
        if len(to_delete) > 40:
            print(f"  ... and {len(to_delete) - 40} more")

    if apply and to_delete:
        conn.executemany("DELETE FROM speeches WHERE url=?", [(lo["url"],) for _, lo in to_delete])
        conn.commit()
        if verbose:
            print(f"Deleted {len(to_delete)} duplicate rows.")
    conn.close()
    return len(to_delete)


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    n = dedupe_speeches(apply=apply)
    if not apply:
        print("\nDry run only. Re-run with --apply to delete.")
