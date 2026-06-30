"""
Generate the global watchlist themes overview page.

Two heatmaps:
  1. Global trend   — topics × months, fraction of speeches across all banks
  2. Bank breakdown — topics × banks,  fraction over last 12 months

Output: report_global_themes.html
Intensity = share of relevant speeches per month/bank that substantively discussed each topic.
"""
import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

from report_filtered_base import build_month_list, _build_heatmap, _section_html, _p90

ROOT     = Path(__file__).parent
DB_PATH  = ROOT / "data/speeches.db"
OUT_PATH = ROOT / "report_global_themes.html"

SPARSE = -1.0

BANK_LABELS = {
    "Federal Reserve": "Fed",
    "Bank of England": "BOE",
    "ECB":             "ECB",
    "Bank of Japan":   "BOJ",
    "BCB":             "BCB",
    "Riksbank":        "Riksbank",
    "SARB":            "SARB",
    "CNB":             "CNB",
}


def generate_global_themes_report() -> None:
    from topics import WATCHLIST_NAMES

    conn = sqlite3.connect(str(DB_PATH))
    df = pd.read_sql_query(
        "SELECT central_bank, date, topic_scores, score FROM speeches", conn
    )
    conn.close()

    today  = date.today()
    cutoff = date(today.year - 1, today.month, today.day).isoformat()
    df_w = df[
        (df["score"] > 0) &
        df["topic_scores"].notna() &
        (df["date"] >= cutoff) &
        df["central_bank"].isin(BANK_LABELS)
    ].copy()

    if df_w.empty:
        print("No topic_scores data yet — run backfill_topic_scores.py first.")
        return

    df_w["month"] = df_w["date"].str[:7]
    df_w["_ts"] = df_w["topic_scores"].apply(
        lambda s: json.loads(s) if isinstance(s, str) else {}
    )

    months, month_labels = build_month_list(12)

    def _fmt(intensity, n):
        return f"Avg prominence: {intensity:.2f} / 3<br>Speeches: {n}"

    # ── Chart 1: Global trend (topics × months) ───────────────────────────────
    global_monthly = {}
    for topic in WATCHLIST_NAMES:
        global_monthly[topic] = {}
        for month in months:
            rows = df_w[df_w["month"] == month]
            n = len(rows)
            if n < 3:
                global_monthly[topic][month] = {"intensity": None, "n": n}
            else:
                avg = sum(r["_ts"].get(topic, 0) for _, r in rows.iterrows()) / n
                global_monthly[topic][month] = {"intensity": avg, "n": n}

    def _topic_avg(data: dict) -> float:
        vals = [v["intensity"] for v in data.values() if v["intensity"] is not None]
        return sum(vals) / len(vals) if vals else 0.0

    def _trend_arrow(data: dict) -> str:
        recent = [data[m]["intensity"] for m in months[-3:] if data[m]["intensity"] is not None]
        prior  = [data[m]["intensity"] for m in months[-6:-3] if data[m]["intensity"] is not None]
        if not recent or not prior:
            return "→"
        diff = sum(recent) / len(recent) - sum(prior) / len(prior)
        if diff > 0.15:
            return "↑"
        if diff < -0.15:
            return "↓"
        return "→"

    # Filter to topics with meaningful global prominence and add trend arrows
    active_global = [t for t in WATCHLIST_NAMES if _topic_avg(global_monthly[t]) >= 0.15]
    global_labelled = {}
    global_labels = []
    for t in active_global:
        label = f"{t}  {_trend_arrow(global_monthly[t])}"
        global_labels.append(label)
        global_labelled[label] = global_monthly[t]

    fig1 = _build_heatmap(global_labelled, global_labels, months, month_labels, fmt_intensity=_fmt)
    fig1.update_layout(margin=dict(l=170, r=100, t=20, b=60))

    # ── Chart 2: Bank breakdown (topics × banks) ──────────────────────────────
    banks_ordered = [b for b in BANK_LABELS if b in df_w["central_bank"].unique()]
    bank_labels   = [BANK_LABELS[b] for b in banks_ordered]

    bank_topic = {}
    for bank in banks_ordered:
        bdf = df_w[df_w["central_bank"] == bank]
        n = len(bdf)
        bank_topic[bank] = {}
        for topic in WATCHLIST_NAMES:
            if n < 2:
                bank_topic[bank][topic] = None
            else:
                bank_topic[bank][topic] = sum(r["_ts"].get(topic, 0) for _, r in bdf.iterrows()) / n

    # Repack into theme_monthly format for _build_heatmap (using bank labels as "months")
    bank_monthly = {}
    for topic in WATCHLIST_NAMES:
        bank_monthly[topic] = {}
        for bank, bl in zip(banks_ordered, bank_labels):
            v = bank_topic[bank][topic]
            n = len(df_w[df_w["central_bank"] == bank])
            bank_monthly[topic][bl] = {"intensity": v, "n": n}

    fig2 = _build_heatmap(bank_monthly, WATCHLIST_NAMES, bank_labels, bank_labels, fmt_intensity=_fmt)
    fig2.update_layout(
        margin=dict(l=160, r=100, t=20, b=40),
        xaxis=dict(side="bottom", tickfont=dict(size=12, color="#111827")),
    )

    # ── Render ────────────────────────────────────────────────────────────────
    plotlyjs = get_plotlyjs()

    def to_div(fig):
        return pio.to_html(fig, include_plotlyjs=False, full_html=False,
                           config={"displayModeBar": False, "responsive": True})

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Global Policy Themes</title>
<script>{plotlyjs}</script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, sans-serif; background: #F3F4F6; color: #111827; padding: 32px 24px; }}
h1 {{ font-size: 1.4rem; font-weight: 700; margin-bottom: 4px; }}
.sub {{ font-size: 0.85rem; color: #6B7280; margin-bottom: 28px; }}
.section {{ background: white; border-radius: 12px; padding: 20px 20px 12px;
            margin-bottom: 28px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.section-title {{ font-size: 0.78rem; font-weight: 600; letter-spacing: .06em;
                  text-transform: uppercase; color: #6B7280; margin-bottom: 14px; }}
</style>
</head>
<body>
<h1>Global Policy Themes</h1>
<p class="sub">All central banks &middot; Last 12 months &middot; Relevant speeches only &middot; Intensity = share of speeches discussing each topic</p>

<div class="section">
  <div class="section-title">Global trend &mdash; % of speeches discussing each topic, by month</div>
  {to_div(fig1)}
</div>

<div class="section">
  <div class="section-title">Bank breakdown &mdash; % of speeches discussing each topic, last 12 months</div>
  {to_div(fig2)}
</div>

</body>
</html>"""

    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Written: {OUT_PATH}")


if __name__ == "__main__":
    import webbrowser
    generate_global_themes_report()
    webbrowser.open(OUT_PATH.as_uri())
