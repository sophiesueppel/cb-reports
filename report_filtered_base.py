"""
Shared logic for filtered central-bank sentiment reports.

Each bank has a thin wrapper (report_ecb_filtered.py etc.) that calls
generate_filtered_report() with bank-specific config.
"""

import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Callable, List, Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from report_frb import (
    score_color, tone, wrap_text,
    make_trend_chart,
    _add_meeting_vlines,
    SPEAKER_PALETTE,
)

DB_PATH = Path("data/speeches.db")


# ---------------------------------------------------------------------------
# Relevance classification (keyword fallback; LLM results preferred)
# ---------------------------------------------------------------------------

_TITLE_OFF_TOPIC = [re.compile(p, re.I) for p in [
    r"\bwelcome remarks\b",
    r"\bopening remarks\b",
    r"\bacceptance remarks\b",
    r"\bbrief remarks\b",
    r"\btokeniz",
    r"\bartificial intelligence\b",
    r"\boperationaliz",
    r"\bsupervision and regulation\b",
    r"\bconsumer fraud\b",
    r"\bstablecoin",
    r"\brural communit",
    r"\bsmall business",
    r"\bfinancial health\b",
    r"\bcapital rules\b",
    r"public.private partnership",
    r"\bliquidity resilienc",
    r"international role of the.*dollar",
    r"\bderegulat",
    r"when regulation reshapes",
    r"migration of corporate lending",
    r"supporting small",
    r"update on federal reserve.*operations",
    r"modernizing federal reserve",
    r"operationalizing ai",
    r"measuring financial",
    r"perspectives on tokenization",
]]

_JUST_OFF_TOPIC = [re.compile(p, re.I) for p in [
    r"no explicit reference to the policy rate",
    r"no explicit monetary policy",
    r"\bnot monetary policy\b",
    r"no mention of monetary policy",
    r"does not address.*monetary policy",
    r"does not directly.*monetary policy",
    r"exclusively on (?:supervision|regulatory|operational)",
    r"\boperationally focused\b",
    r"\bceremonial\b",
    r"focused entirely on",
    r"no reference to.*(?:rate|inflation|labor|labour)",
    r"does not address.*rate path",
]]


def _classify_relevance(title: str, justification: str, score) -> int:
    """Return 1 (relevant) or 0 (off-topic). Hawkish/dovish always relevant."""
    if score is None:
        return 1
    if int(score) == 0:
        return 0
    if int(score) <= 3 or int(score) >= 7:
        return 1
    for pat in _TITLE_OFF_TOPIC:
        if pat.search(title or ""):
            return 0
    for pat in _JUST_OFF_TOPIC:
        if pat.search(justification or ""):
            return 0
    return 1


_CEREMONIAL = re.compile(
    r"\b(welcome|welcoming|opening|acceptance|accepting|introductory|commencement|brief)\b.*\bremarks?\b"
    r"|\bremarks?\b.*(welcome|welcoming|opening)"
    r"|\bcommencement address\b", re.I
)
_FINTECH = re.compile(
    r"tokeniz|stablecoin|\bartificial intelligence\b|\bai\b.*(financial|bank|system|economy)"
    r"|fintech|interlinking.*fast|cross.border payment|payment.*innov|operationaliz.*ai", re.I
)
_REGULATORY = re.compile(
    r"\bsupervision\b|\bregulat|\bcapital rules\b|\bliquidity resilienc"
    r"|bank mergers|deregulat|when regulation|migration of corporate"
    r"|modernizing.*(?:supervision|regulation|federal reserve)"
    r"|update on.*operations|novel activities|stress.test|stress capital buffer"
    r"|tailoring.*rule|unintended consequences|large bank supervision", re.I
)
_FINANCIAL_STABILITY = re.compile(r"financial stability|systemic risk|macroprudential", re.I)
_COMMUNITY = re.compile(
    r"rural communit|small business|financial inclusion|consumer fraud"
    r"|financial health|public.private|entrepreneurship|building.*inclusive"
    r"|financial system safer|financial system fairer|cross.border.*inclusion"
    r"|advancing.*inclusion|creating.*inclusive|making.*fairer", re.I
)
_OPERATIONAL = re.compile(
    r"operationaliz|modernizing federal reserve|update on federal reserve"
    r"|international role of the.*dollar|interlinking fast", re.I
)


def _offtopic_category(title: str, justification: str) -> str:
    t = title or ""
    j = justification or ""
    if _CEREMONIAL.search(t):
        return "Ceremonial"
    if _FINTECH.search(t):
        return "Fintech / Digital"
    if _REGULATORY.search(t):
        return "Regulatory"
    if _FINANCIAL_STABILITY.search(t):
        return "Financial Stability"
    if _COMMUNITY.search(t):
        return "Community / Social"
    if _OPERATIONAL.search(t):
        return "Operational"
    if _REGULATORY.search(j):
        return "Regulatory"
    if _FINANCIAL_STABILITY.search(j):
        return "Financial Stability"
    if _CEREMONIAL.search(j):
        return "Ceremonial"
    return "Off-topic"


NEUTRAL_GREEN = "#7A9E87"


def _dot_color(score):
    if 4 <= score <= 6:
        return NEUTRAL_GREEN
    return score_color(score)


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

def make_timeline_with_ghosts(
    df_relevant: pd.DataFrame,
    df_offtopic: pd.DataFrame,
    meetings=None,
) -> str:
    asc = df_relevant.sort_values("date")
    colors = [_dot_color(s) for s in asc["score"]]

    hover_rel = [
        f"<span style='color:#111827;font-weight:600'>{r['speaker']}</span><br>"
        f"<span style='color:#374151'>{r['title']}</span><br>"
        f"<span style='color:#6B7280'>{r['date']}</span><br><br>"
        f"<span style='color:{score_color(r['score'])};font-weight:700'>{r['score']}/10 — {tone(r['score'])}</span><br><br>"
        f"<span style='color:#374151'>{wrap_text(r['justification'])}</span>"
        for _, r in asc.iterrows()
    ]

    fig = go.Figure()
    fig.add_hrect(y0=7, y1=10, fillcolor="rgba(220,38,38,0.04)", line_width=0)
    fig.add_hrect(y0=1, y1=3, fillcolor="rgba(37,99,235,0.04)", line_width=0)

    fig.add_trace(go.Scatter(
        x=asc["date"], y=asc["score"],
        mode="lines",
        line=dict(color="rgba(17,24,39,0.12)", width=1),
        hoverinfo="skip", showlegend=False,
    ))

    rolling = asc["score"].rolling(window=10, min_periods=3).mean()
    fig.add_trace(go.Scatter(
        x=asc["date"], y=rolling,
        mode="lines",
        line=dict(color="rgba(17,24,39,0.55)", width=2.5),
        hoverinfo="skip", showlegend=False,
    ))

    if not df_offtopic.empty:
        ghost = df_offtopic.sort_values("date")
        ghost_y = ghost.apply(
            lambda r: int(r["original_score"]) if pd.notna(r.get("original_score")) and r.get("original_score") else 5,
            axis=1,
        )
        ghost_hover = [
            f"<span style='color:#9CA3AF;font-weight:600'>{r['speaker']}</span><br>"
            f"<span style='color:#9CA3AF'>{r['title']}</span><br>"
            f"<span style='color:#D1D5DB'>{r['date']}</span><br>"
            f"<span style='color:#D1D5DB;font-size:11px'>Off-topic · not counted in signal</span>"
            for _, r in ghost.iterrows()
        ]
        fig.add_trace(go.Scatter(
            x=ghost["date"], y=ghost_y,
            mode="markers",
            marker=dict(
                color="rgba(255,255,255,0)",
                size=7,
                line=dict(color="rgba(156,163,175,0.45)", width=1.5),
            ),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=ghost_hover,
            showlegend=False,
            name="Off-topic",
        ))

    fig.add_trace(go.Scatter(
        x=asc["date"], y=asc["score"],
        mode="markers",
        marker=dict(color=colors, size=9, line=dict(color="white", width=1.5)),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover_rel,
        showlegend=False,
    ))

    fig.update_layout(
        height=360,
        margin=dict(l=48, r=20, t=24, b=40),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="system-ui, -apple-system, sans-serif", size=11, color="#6B7280"),
        yaxis=dict(range=[0.5, 10.5], tickvals=[1, 3, 5, 7, 10],
                   gridcolor="#F0F1F3", gridwidth=1, zeroline=False, title=None),
        xaxis=dict(gridcolor="#F0F1F3", gridwidth=1, zeroline=False,
                   title=None, tickformat="%b %Y"),
        hoverlabel=dict(
            bgcolor="white", bordercolor="#E4E8EF",
            font=dict(size=12, color="#111827", family="system-ui, -apple-system, sans-serif"),
            align="left", namelength=0,
        ),
        annotations=[
            dict(x=0, xref="paper", y=10, yref="y", text="HAWK", showarrow=False,
                 font=dict(size=9, color="#DC2626", family="system-ui"), xanchor="left"),
            dict(x=0, xref="paper", y=1, yref="y", text="DOVE", showarrow=False,
                 font=dict(size=9, color="#2563EB", family="system-ui"), xanchor="left"),
        ],
    )
    if meetings:
        _add_meeting_vlines(fig, meetings)
    return pio.to_html(fig, include_plotlyjs=True, full_html=False,
                       config={"displayModeBar": False, "responsive": True})


# ---------------------------------------------------------------------------
# Theme frequency chart
# ---------------------------------------------------------------------------

THEMES_PATH = Path("data/themes.json")

_MON_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

_SPARSE_SENTINEL = -1.0  # z value for months with <2 speeches — mapped to grey


def _score_themes(body: str, theme_patterns: dict) -> dict:
    """Count mentions of each theme in body using pre-compiled patterns."""
    body_lower = (body or "").lower()
    return {theme: len(pat.findall(body_lower)) for theme, pat in theme_patterns.items()}


def build_month_list(n: int = 12) -> tuple[list, list]:
    """Return (ISO month keys, human labels) for the last n months, oldest first."""
    today = date.today()
    months, labels = [], []
    for i in range(n - 1, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y}-{m:02d}")
        labels.append(f"{_MON_ABBR[m-1]} {y}")
    return months, labels


def compile_theme_patterns(themes_dict: dict) -> dict:
    """Compile a regex pattern per theme from a {theme: [keywords]} dict."""
    patterns = {}
    for theme, terms in themes_dict.items():
        if not terms:
            continue
        patterns[theme] = re.compile(
            r'\b(' + '|'.join(re.escape(t.lower()) for t in terms) + r')\b'
        )
    return patterns


def score_themes_monthly(
    df: pd.DataFrame,
    theme_patterns: dict,
    months: list,
    min_speeches: int = 2,
) -> dict:
    """Score a DataFrame of speeches against theme patterns, aggregated by month.

    Returns {theme: {month: {"intensity": float|None, "n": int}}}.
    Months with fewer than min_speeches get intensity=None (rendered as grey).
    df must have a "month" column (YYYY-MM) and a "_scores" column already computed.
    """
    result = {theme: {} for theme in theme_patterns}
    for month in months:
        rows = df[df["month"] == month]
        n = len(rows)
        for theme in theme_patterns:
            if n < min_speeches:
                result[theme][month] = {"intensity": None, "n": n}
            else:
                vals = [r["_scores"][theme] for _, r in rows.iterrows()]
                result[theme][month] = {"intensity": sum(vals) / n, "n": n}
    return result


def _p90(values: list) -> float:
    """90th-percentile of a list (no numpy)."""
    if not values:
        return 1.0
    s = sorted(values)
    idx = max(0, int(len(s) * 0.9) - 1)
    return float(s[idx]) or 1.0


def _build_heatmap(theme_monthly: dict, themes: list, months: list, month_labels: list, fmt_intensity=None) -> go.Figure:
    """Build a heatmap from pre-computed monthly theme data.

    Sparse months (<2 speeches) → grey sentinel cell.
    Colour scale capped at p90 so a single dominant topic doesn't wash out the rest.
    Themes sorted most-active → least-active (top to bottom).
    """
    # Compute p90 over all non-None intensities for this set of themes
    all_vals = [
        theme_monthly[t][m]["intensity"]
        for t in themes for m in months
        if theme_monthly[t][m]["intensity"] is not None
    ]
    zmax = _p90(all_vals)

    # Sort themes: most total activity at top
    totals = {t: sum(theme_monthly[t][m]["intensity"] or 0 for m in months) for t in themes}
    themes_ordered = sorted(themes, key=lambda t: totals[t], reverse=True)

    z, customdata = [], []
    for theme in themes_ordered:
        z_row, cd_row = [], []
        for month, ml in zip(months, month_labels):
            d = theme_monthly[theme][month]
            n, intensity = d["n"], d["intensity"]
            if intensity is None:
                z_row.append(_SPARSE_SENTINEL)
                note = "&lt;2 speeches" if n > 0 else "no speeches"
                cd_row.append(f"<b>{theme}</b><br>{ml}<br><i style='color:#9CA3AF'>{note}</i>")
            else:
                z_row.append(min(intensity, zmax))  # cap at p90 for display
                if fmt_intensity:
                    detail = fmt_intensity(intensity, n)
                else:
                    detail = f"Avg mentions/speech: {intensity:.2f}<br>Speeches: {n}"
                cd_row.append(f"<b>{theme}</b><br>{ml}<br>{detail}")
        z.append(z_row)
        customdata.append(cd_row)

    # Colorscale: sentinel → grey; 0 → near-white; zmax → dark blue
    # Normalised: 0 = _SPARSE_SENTINEL, 1 = zmax
    span = zmax - _SPARSE_SENTINEL

    def _n(v):
        return round((v - _SPARSE_SENTINEL) / span, 6)

    colorscale = [
        [0.0,           "#D1D5DB"],   # sentinel → grey
        [_n(0) - 1e-4, "#D1D5DB"],   # up to (just below) zero → grey
        [_n(0),         "#F1F5F9"],   # zero intensity → near-white
        [_n(zmax * 0.1),"#DBEAFE"],
        [_n(zmax * 0.35),"#60A5FA"],
        [_n(zmax * 0.7), "#2563EB"],
        [1.0,            "#1E3A8A"],
    ]

    n_themes = len(themes_ordered)
    height = max(280, n_themes * 34 + 110)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=month_labels,
        y=themes_ordered,
        zmin=_SPARSE_SENTINEL,
        zmax=zmax,
        colorscale=colorscale,
        hovertemplate="%{customdata}<extra></extra>",
        customdata=customdata,
        showscale=True,
        colorbar=dict(
            title=dict(text="avg<br>mentions/<br>speech", font=dict(size=10)),
            thickness=10,
            len=0.7,
            tickvals=[0, zmax * 0.5, zmax],
            ticktext=["0", f"{zmax * 0.5:.1f}", f"≥{zmax:.1f}"],
            outlinewidth=0,
        ),
        xgap=2,
        ygap=2,
    ))
    fig.update_layout(
        height=height,
        margin=dict(l=160, r=90, t=20, b=55),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="system-ui, -apple-system, sans-serif", size=11, color="#374151"),
        xaxis=dict(side="bottom", tickangle=-30, type="category", tickfont=dict(size=10)),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
        hoverlabel=dict(
            bgcolor="white", bordercolor="#E4E8EF",
            font=dict(size=12, color="#111827", family="system-ui, -apple-system, sans-serif"),
            align="left",
        ),
    )
    return fig


def _section_html(title: str, chart_html: str) -> str:
    return (
        f'<section class="chart-section">'
        f'<div class="section-header">'
        f'<span class="section-title">{title}</span>'
        f'<div class="section-rule"></div>'
        f'</div>'
        f'<div class="chart-wrap">{chart_html}</div>'
        f'</section>'
    )


def make_watchlist_chart(df: pd.DataFrame) -> str:
    """Return the Macro Watchlist heatmap section.

    Reads LLM-scored topic_scores from the DataFrame (stored as JSON in the DB column).
    Intensity = fraction of speeches per month that substantively discussed each topic.
    """
    from topics import WATCHLIST_NAMES

    if "topic_scores" not in df.columns:
        return ""

    today = date.today()
    cutoff_12m = date(today.year - 1, today.month, today.day).isoformat()
    df_w = df[
        (df["score"] > 0) &
        df["topic_scores"].notna() &
        (df["date"] >= cutoff_12m)
    ].copy()
    if df_w.empty:
        return ""

    df_w["month"] = df_w["date"].str[:7]
    months, month_labels = build_month_list(12)

    df_w["_ts"] = df_w["topic_scores"].apply(
        lambda s: json.loads(s) if isinstance(s, str) else {}
    )

    theme_monthly = {}
    for topic in WATCHLIST_NAMES:
        theme_monthly[topic] = {}
        for month in months:
            rows = df_w[df_w["month"] == month]
            n = len(rows)
            if n < 2:
                theme_monthly[topic][month] = {"intensity": None, "n": n}
            else:
                avg = sum(r["_ts"].get(topic, 0) for _, r in rows.iterrows()) / n
                theme_monthly[topic][month] = {"intensity": avg, "n": n}

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

    # Only show topics with meaningful average prominence (≥0.15 across all months)
    active_topics = [t for t in WATCHLIST_NAMES if _topic_avg(theme_monthly[t]) >= 0.15]
    if not active_topics:
        return ""

    # Build labelled copies — topic name + trend arrow as y-axis label
    labelled_monthly = {}
    active_labels = []
    for t in active_topics:
        label = f"{t}  {_trend_arrow(theme_monthly[t])}"
        active_labels.append(label)
        labelled_monthly[label] = theme_monthly[t]

    def _fmt(intensity, n):
        return f"Avg prominence: {intensity:.2f} / 3<br>Speeches: {n}"

    fig = _build_heatmap(
        labelled_monthly,
        active_labels, months, month_labels, fmt_intensity=_fmt,
    )
    chart_html = pio.to_html(fig, include_plotlyjs=False, full_html=False,
                             config={"displayModeBar": False, "responsive": True})
    return _section_html(
        "Macro Watchlist &middot; Last 12 Months &middot; Share of relevant speeches",
        chart_html,
    )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ensure_column(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    if "relevant_to_mp" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN relevant_to_mp INTEGER")
        conn.commit()


def _classify_and_store(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    if "relevant_to_mp_source" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN relevant_to_mp_source TEXT")
    if "relevant_to_mp_reason" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN relevant_to_mp_reason TEXT")
    conn.commit()
    for _, row in df.iterrows():
        source = row.get("relevant_to_mp_source")
        if pd.isna(source) or source is None:
            val = _classify_relevance(row["title"], row["justification"], row["score"])
            conn.execute(
                "UPDATE speeches SET relevant_to_mp=?, relevant_to_mp_source='keyword' WHERE url=?",
                (val, row["url"]),
            )
    conn.commit()


# ---------------------------------------------------------------------------
# Page template  (__ACCENT__ and __BANK_LABEL__ replaced before .format())
# ---------------------------------------------------------------------------

PAGE_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__BANK_LABEL__ Policy Sentiment Tracker (Filtered)</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  background:#F7F8FA;color:#111827;min-height:100vh;font-size:14px;line-height:1.5;
}}
.page{{max-width:1100px;margin:0 auto;padding:44px 32px 80px}}

header{{
  display:flex;justify-content:space-between;align-items:flex-end;
  padding-bottom:20px;border-bottom:1px solid #E4E8EF;margin-bottom:40px;
}}
.eyebrow{{font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:__ACCENT__;margin-bottom:5px}}
h1{{font-family:Georgia,serif;font-size:23px;font-weight:normal;color:#111827;line-height:1.2}}
.header-sub{{font-size:11px;color:#9CA3AF;margin-top:5px}}
.header-meta{{font-size:11px;color:#9CA3AF;text-align:right;line-height:1.9}}

.latest-card{{
  background:#fff;border:1px solid #E4E8EF;border-radius:6px;
  padding:26px 30px;margin-bottom:40px;
  display:grid;grid-template-columns:1fr auto;gap:36px;align-items:start;
}}
.card-label{{font-size:9px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#9CA3AF;margin-bottom:18px;grid-column:1/-1}}
.card-date{{font-size:11px;color:#9CA3AF;margin-bottom:4px;font-variant-numeric:tabular-nums}}
.card-speaker{{font-size:13px;font-weight:600;margin-bottom:7px}}
.card-title{{font-family:Georgia,serif;font-size:17px;font-weight:normal;text-wrap:balance;margin-bottom:13px;line-height:1.45;color:#111827}}
.card-justification{{font-size:13px;color:#6B7280;line-height:1.7;max-width:58ch}}
.score-block{{text-align:right;min-width:72px;padding-top:2px}}
.score-numeral{{font-family:Georgia,serif;font-size:46px;font-weight:normal;line-height:1;font-variant-numeric:tabular-nums}}
.score-denom{{font-size:17px;opacity:.4}}
.score-tone{{font-size:9px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;margin-top:5px}}

.section-header{{display:flex;align-items:center;gap:14px;margin-bottom:16px}}
.section-title{{font-size:9px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#9CA3AF;white-space:nowrap}}
.section-rule{{flex:1;height:1px;background:#E4E8EF}}

.toggle-btn{{
  font-size:11px;color:#6B7280;background:#fff;border:1px solid #E4E8EF;
  border-radius:4px;padding:3px 10px;cursor:pointer;white-space:nowrap;
  transition:background .1s,color .1s;
}}
.toggle-btn:hover{{background:#F3F4F6;color:#111827}}
.toggle-btn.active{{background:#F3F4F6;color:#374151;border-color:#D1D5DB}}

.chart-section{{margin-bottom:40px}}
.chart-wrap{{background:#fff;border:1px solid #E4E8EF;border-radius:6px;padding:8px 12px;overflow:hidden}}
.chart-wrap .plotly-graph-div{{width:100% !important}}

.table-wrap{{background:#fff;border:1px solid #E4E8EF;border-radius:6px;overflow:hidden}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;table-layout:fixed}}
col.c-date{{width:82px}}
col.c-speaker{{width:210px}}
col.c-title{{width:auto}}
col.c-score{{width:130px}}
col.c-toggle{{width:28px}}
thead th{{
  font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
  color:#9CA3AF;padding:13px 16px;text-align:left;border-bottom:1px solid #E4E8EF;white-space:nowrap;
}}
tbody td{{padding:13px 16px;border-bottom:1px solid #F3F4F6;font-size:13px;vertical-align:top}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr{{cursor:pointer;transition:background .1s}}
tbody tr:hover td{{background:#FAFBFC}}
tbody tr.expanded td{{background:#FAFBFC}}

tbody tr.off-topic{{opacity:0.35}}
tbody tr.off-topic:hover{{opacity:0.6}}
tbody tr.off-topic.expanded{{opacity:0.7}}
tbody tr.off-topic.hidden{{display:none}}

.off-topic-badge{{
  display:inline-block;font-size:9px;font-weight:700;letter-spacing:.06em;
  text-transform:uppercase;border-radius:3px;padding:2px 6px;margin-left:7px;
  vertical-align:middle;cursor:help;white-space:nowrap;
}}
.badge-ceremonial{{color:#92400E;background:#FEF3C7}}
.badge-regulatory{{color:#1E40AF;background:#DBEAFE}}
.badge-fintech{{color:#5B21B6;background:#EDE9FE}}
.badge-stability{{color:#065F46;background:#D1FAE5}}
.badge-community{{color:#9D174D;background:#FCE7F3}}
.badge-operational{{color:#374151;background:#F3F4F6}}
.badge-default{{color:#6B7280;background:#F3F4F6}}

.td-date{{color:#9CA3AF;font-size:11px;padding-top:15px !important}}
.td-speaker{{font-weight:600;font-size:13px;padding-top:14px !important;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.title-text{{color:#111827;line-height:1.45;word-break:break-word}}
.title-text a{{color:#111827;text-decoration:none}}
.title-text a:hover{{text-decoration:underline}}
.td-justification{{
  font-size:12px;color:#6B7280;line-height:1.65;
  max-height:0;overflow:hidden;opacity:0;
  transition:max-height .28s ease,opacity .22s ease,margin-top .2s ease;
  margin-top:0;
}}
tr.expanded .td-justification{{max-height:320px;opacity:1;margin-top:7px}}

.td-body-section{{max-height:0;overflow:hidden;opacity:0;transition:max-height .35s ease,opacity .25s ease,margin-top .2s ease;margin-top:0}}
tr.expanded .td-body-section{{max-height:520px;opacity:1;margin-top:12px}}
.td-body-label{{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#9CA3AF;display:block;margin-bottom:10px;padding-top:10px;border-top:1px solid #E4E8EF}}
.td-body{{font-size:12.5px;color:#374151;line-height:1.8;max-height:480px;overflow-y:auto;padding-right:10px}}
.sp-p{{margin:0 0 0.85em;color:#374151}}.sp-p:last-child{{margin-bottom:0}}
.sp-h{{font-weight:600;font-size:12.5px;color:#111827;margin:1.1em 0 0.35em;letter-spacing:.01em}}
.sp-notice{{font-size:11px;color:#6B7280;background:#F9FAFB;border:1px solid #E4E8EF;border-radius:4px;padding:7px 10px;margin-bottom:12px;line-height:1.5}}
.sp-notice a{{color:#2563EB;text-decoration:none}}.sp-notice a:hover{{text-decoration:underline}}
.sp-list{{margin:0 0 0.85em;padding-left:1.4em;color:#374151}}.sp-list li{{margin-bottom:0.25em;font-size:12.5px;line-height:1.7}}

.td-source-link{{max-height:0;overflow:hidden;opacity:0;transition:max-height .28s ease,opacity .22s ease,margin-top .2s ease;margin-top:0}}
tr.expanded .td-source-link{{max-height:44px;opacity:1;margin-top:8px}}
.source-btn{{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:#4F46E5;border:1px solid #C7D2FE;background:#EEF2FF;border-radius:4px;padding:4px 10px;text-decoration:none;letter-spacing:.01em}}
.source-btn:hover{{background:#E0E7FF;color:#3730A3}}

.row-bar{{display:flex;align-items:center;gap:9px;white-space:nowrap;padding-top:1px}}
.row-num{{font-family:Georgia,serif;font-size:15px;min-width:14px;text-align:right;font-variant-numeric:tabular-nums}}
.row-track{{width:48px;height:3px;background:#F3F4F6;border-radius:2px;flex-shrink:0}}
.row-fill{{height:100%;border-radius:2px}}
.row-tone{{font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;min-width:44px}}

.td-toggle{{text-align:right;color:#D1D5DB;font-size:11px;padding-top:14px !important}}
tr.expanded .td-toggle{{color:#6B7280}}
.chevron{{display:inline-block;transition:transform .22s ease}}
.speaker-select{{font-size:11px;color:#6B7280;background:#fff;border:1px solid #E4E8EF;border-radius:4px;padding:3px 8px;cursor:pointer;font-family:inherit}}
.speaker-select:hover{{background:#F3F4F6;color:#111827}}
tr.expanded .chevron{{transform:rotate(180deg)}}

.trend-container{{display:flex;align-items:flex-start}}
.trend-container .chart-wrap{{flex:1;min-width:0}}
.trend-legend{{width:116px;flex-shrink:0;padding:14px 0 14px 8px}}
.tl-item{{display:flex;align-items:center;gap:5px;padding:3px 6px;border-radius:4px;cursor:pointer;white-space:nowrap}}
.tl-item:hover{{background:#F3F4F6}}
.tl-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.tl-name{{font-size:11.5px;color:#374151;flex:1;overflow:hidden;text-overflow:ellipsis}}
.tl-avg{{font-family:Georgia,serif;font-size:12px;font-weight:bold;min-width:22px;text-align:right}}

.meeting-key{{display:flex;gap:20px;padding:7px 14px 2px;font-size:11px;color:#6B7280}}
.mk-item{{display:flex;align-items:center;gap:6px}}
.mk-line{{display:inline-block;width:22px;height:2px}}
.mk-hike{{background:#DC2626}}
.mk-cut{{background:#2563EB}}
.mk-hold{{background:repeating-linear-gradient(90deg,rgba(156,163,175,0.7) 0,rgba(156,163,175,0.7) 5px,transparent 5px,transparent 9px)}}

.stats-wrap{{background:#fff;border:1px solid #E4E8EF;border-radius:6px;overflow-x:auto}}
.stats-table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;table-layout:auto}}
.stats-table thead th{{font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#9CA3AF;padding:12px 16px;text-align:left;border-bottom:1px solid #E4E8EF;white-space:nowrap}}
.stats-table tbody td{{padding:11px 16px;border-bottom:1px solid #F3F4F6;font-size:13px;vertical-align:middle}}
.stats-table tbody tr{{cursor:default}}
.stats-table tbody tr:last-child td{{border-bottom:none}}
.stats-table tbody tr.has-flag{{background:#FFFBEB}}
.stats-table tbody tr:hover td{{background:#FAFBFC}}
.st-name{{font-weight:600;white-space:nowrap}}
.st-avg{{font-family:Georgia,serif;font-size:16px;font-weight:normal}}
.st-meta{{font-size:11px;color:#9CA3AF}}
.spk-trend-hawk{{color:#DC2626;font-weight:600}}
.spk-trend-dove{{color:#2563EB;font-weight:600}}
.spk-trend-flat{{color:#9CA3AF}}
.no-flag{{color:#D1D5DB}}
.flag-chip{{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:10px;font-size:11px;margin:2px 3px 2px 0;cursor:default;white-space:nowrap;line-height:1.4}}
.flag-hawk{{background:#FEE2E2;color:#B91C1C}}
.flag-dove{{background:#DBEAFE;color:#1D4ED8}}
.flag-recent{{font-weight:700;outline:1px solid currentColor;outline-offset:1px}}

.filter-notice{{
  font-size:11px;color:#6B7280;background:#F9FAFB;border:1px solid #E4E8EF;
  border-radius:4px;padding:8px 12px;margin-bottom:16px;
}}
</style>
</head>
<body>
<div class="page">

<header>
  <div>
    <div class="eyebrow">__BANK_LABEL__</div>
    <h1>Policy Sentiment Tracker</h1>
    <div class="header-sub">Off-topic neutral speeches filtered · Charts show policy-relevant speeches only</div>
  </div>
  <div class="header-meta" id="hm"></div>
</header>

<div id="latest-wrap"></div>

<section class="chart-section">
  <div class="section-header">
    <span class="section-title">Score History &middot; Last 5 Years &middot; Hollow dots = off-topic (not counted)</span>
    <div class="section-rule"></div>
  </div>
  <div class="chart-wrap">{timeline}</div>
  <div class="meeting-key">
    <span class="mk-item"><span class="mk-line mk-hike"></span>Rate hike</span>
    <span class="mk-item"><span class="mk-line mk-cut"></span>Rate cut</span>
    <span class="mk-item"><span class="mk-line mk-hold"></span>Rates held</span>
  </div>
</section>

<section class="chart-section">
  <div class="section-header">
    <span class="section-title">Score Trajectory by Speaker &middot; Last 5 Years &middot; Relevant speeches only</span>
    <div class="section-rule"></div>
  </div>
  <div class="trend-container">
    <div class="chart-wrap">{trend_chart}</div>
    <div class="trend-legend" id="trend-legend"></div>
  </div>
</section>

{theme_chart}

<section class="chart-section">
  <div class="section-header">
    <span class="section-title">Speaker Analysis &middot; Active Members &middot; Relevant speeches only</span>
    <div class="section-rule"></div>
  </div>
  <div class="stats-wrap">
    <table class="stats-table">
      <thead>
        <tr>
          <th>Speaker</th>
          <th>Avg</th>
          <th>Std Dev</th>
          <th>Speeches</th>
          <th>Trend</th>
          <th>Flagged Speeches</th>
        </tr>
      </thead>
      <tbody id="stats-tbody"></tbody>
    </table>
  </div>
</section>

<section>
  <div class="section-header">
    <span class="section-title">All Speeches &middot; Last 5 Years &middot; Click row to expand</span>
    <div class="section-rule"></div>
    <button class="toggle-btn" id="toggle-btn" onclick="toggleOffTopic()">Show off-topic</button>
    <select id="speaker-filter" class="speaker-select"><option value="">All speakers</option></select>
  </div>
  <div class="filter-notice" id="filter-notice"></div>
  <div class="table-wrap">
    <table>
      <colgroup>
        <col class="c-date"><col class="c-speaker"><col class="c-title"><col class="c-score"><col class="c-toggle">
      </colgroup>
      <thead>
        <tr><th>Date</th><th>Speaker</th><th>Title</th><th>Score</th><th></th></tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
</section>

</div>
<script>
const ACTIVE_MEMBERS = {active_members_json};
const DATA = {data};

function lerp(a,b,t){{return Math.round(a+(b-a)*t)}}
function scoreColor(s){{
  const t=(s-1)/9;
  if(t<=0.5){{const u=t*2;return`rgb(${{lerp(37,107,u)}},${{lerp(99,114,u)}},${{lerp(235,128,u)}})`}}
  const u=(t-0.5)*2;return`rgb(${{lerp(107,220,u)}},${{lerp(114,38,u)}},${{lerp(128,38,u)}})`;
}}
function tone(s){{return s<=3?'Dovish':s<=6?'Neutral':'Hawkish'}}
function fmt(iso){{return new Date(iso+'T00:00:00').toLocaleDateString('en-US',{{month:'short',day:'numeric',year:'numeric'}})}}

const n=DATA.length;
const nRelev=DATA.filter(d=>d.relevant).length;
const nOff=n-nRelev;
const ts=new Date().toLocaleDateString('en-US',{{month:'long',day:'numeric',year:'numeric'}});
document.getElementById('hm').innerHTML=`Updated ${{ts}}<br>${{n}} speech${{n!==1?'es':''}} total · ${{nOff}} off-topic`;

const relevSorted=[...DATA].filter(d=>d.relevant).sort((a,b)=>b.date.localeCompare(a.date));
const latest=relevSorted[0];
if(latest){{
  const col=scoreColor(latest.score);
  document.getElementById('latest-wrap').innerHTML=`
  <div class="latest-card">
    <div class="card-label">Most Recent Policy-Relevant Speech</div>
    <div>
      <div class="card-date">${{fmt(latest.date)}}</div>
      <div class="card-speaker">${{latest.speaker}}</div>
      <div class="card-title">${{latest.title}}</div>
      <p class="card-justification">${{latest.justification||''}}</p>
    </div>
    <div class="score-block">
      <div class="score-numeral" style="color:${{col}}">${{latest.score}}<span class="score-denom">/10</span></div>
      <div class="score-tone" style="color:${{col}}">${{tone(latest.score)}}</div>
    </div>
  </div>`;
}}

const notice=document.getElementById('filter-notice');
if(nOff>0){{
  notice.textContent=`${{nOff}} off-topic neutral speech${{nOff!==1?'es are':' is'}} hidden below (ceremonial remarks, regulatory/operational topics, fintech). Click "Show off-topic" to reveal them faded.`;
}}else{{
  notice.style.display='none';
}}

function realUrl(u){{
  if(!u)return '';
  if(u.startsWith('bcb::')){{
    const path=(u.split('::')[2]||'');
    return path.startsWith('/')?'https://www.bcb.gov.br'+path:'https://www.bcb.gov.br/acessoinformacao/discursos';
  }}
  return u;
}}

function fmtBody(txt,url){{
  if(!txt||txt==='nan'||txt==='None') return '';
  function esc(s){{return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
  txt=txt.replace(/\\r\\n/g,'\\n').replace(/\\r/g,'\\n');
  txt=txt.replace(/Official websites use \\.gov[\\s\\S]*?Share sensitive information only on official, secure websites\\.\\s*/,'').trim();
  txt=txt.replace(/The Federal Reserve, the central bank of the United States[\\s\\S]*?system\\.\\s*/,'').trim();
  txt=txt.replace(/^\\s*SPEECH[\\s\\S]*?(?:\\d{{1,2}}\\s+\\w+\\s+20\\d\\d|\\w+\\s+\\d{{1,2}},\\s*20\\d\\d)\\s*/,'').trim();
  txt=txt.replace(/\\n(PRESENTATION|SPEECH) /g,'\\n').trim();
  txt=txt.replace(/\\n(?:Date:|Speaker:|Place:)\\t[^\\n]*/g,'').trim();
  txt=txt.replace(/\\nShare [^\\n]*/g,'').trim();
  txt=txt.replace(/\\nPublished \\d[^\\n]*/g,'').trim();
  txt=txt.replace(/\\nRELATED CONTENT[\\s\\S]*$/,'').trim();
  txt=txt.replace(/\\nUpdated \\d{{2}}\\/\\d{{2}}\\/\\d{{4}}\\s*$/,'').trim();
  var hasCharts=/\\b(?:Chart|Figure|Graph|Exhibit)\\s*\\d+/i.test(txt);
  var notice=hasCharts&&url?'<div class="sp-notice">This speech references charts/figures not available in text — <a href="'+esc(url)+'" target="_blank" rel="noopener">view at source ↗</a></div>':'';
  var html=txt.split(/\\n\\n+/).map(function(b){{
    b=b.trim();if(!b) return '';
    var ls=b.split('\\n').map(function(l){{return l.trim();}}).filter(function(l){{return !!l;}});
    if(!ls.length) return '';
    if(ls.length>1){{
      var allOl=ls.every(function(l){{return /^\\d+[.)]\\s+\\S/.test(l);}});
      if(allOl) return '<ol class="sp-list">'+ls.map(function(l){{return '<li>'+esc(l.replace(/^\\d+[.)]\\s+/,''))+'</li>';}}).join('')+'</ol>';
      var allUl=ls.every(function(l){{return /^[-•·*]\\s+\\S/.test(l);}});
      if(allUl) return '<ul class="sp-list">'+ls.map(function(l){{return '<li>'+esc(l.replace(/^[-•·*]\\s+/,''))+'</li>';}}).join('')+'</ul>';
    }}
    if(ls.length===1){{
      var t=ls[0];
      if(/^[IVX]{{1,5}}\\.\\s+\\S/.test(t)&&t.length<120) return '<div class="sp-h">'+esc(t)+'</div>';
      if(t.length>4&&t.length<90&&!/[.,;:?!]$/.test(t)) return '<div class="sp-h">'+esc(t)+'</div>';
    }}
    return '<p class="sp-p">'+ls.map(esc).join('<br>')+'</p>';
  }}).filter(function(x){{return !!x;}}).join('');
  return notice+html;
}}

const byDate=[...DATA].sort((a,b)=>b.date.localeCompare(a.date));
document.getElementById('tbody').innerHTML=byDate.map((d,i)=>{{
  const col=scoreColor(d.score),pct=d.score>0?(d.score-1)/9*100:0;
  const scoreCell=d.score===0?'<span style="color:#9CA3AF;font-size:11px;font-weight:700">Off-topic</span>':'<div class="row-bar"><span class="row-num" style="color:'+col+'">'+d.score+'</span><div class="row-track"><div class="row-fill" style="width:'+pct+'%;background:'+col+'"></div></div><span class="row-tone" style="color:'+col+'">'+tone(d.score)+'</span></div>';
  const isOff=!d.relevant;
  const CAT_CLASS={{
    'Ceremonial':'badge-ceremonial','Regulatory':'badge-regulatory',
    'Fintech / Digital':'badge-fintech','Financial Stability':'badge-stability',
    'Community / Social':'badge-community','Operational':'badge-operational',
  }};
  const cat=d.offtopic_category||'Off-topic';
  const cls=CAT_CLASS[cat]||'badge-default';
  const src=d.relevant_to_mp_source||'keyword';
  const reason=d.relevant_to_mp_reason?` — "${{d.relevant_to_mp_reason}}"`:'';
  const badge=isOff?`<span class="off-topic-badge ${{cls}}" title="Off-topic (${{src}}): ${{cat}}${{reason}}">${{cat}}</span>`:'';
  const rowCls=isOff?'off-topic hidden':'';
  const hasBody=!!(d.body&&d.body!=='nan'&&d.body!=='None')||(d.body_en&&d.body_en!=='nan'&&d.body_en!=='None');
  const bodySection=hasBody?'<div class="td-body-section"><span class="td-body-label">Full speech text</span><div class="td-body"></div></div>':'';
  const rUrl=realUrl(d.url);
  const sourceBtn=rUrl?'<div class="td-source-link"><a class="source-btn" href="'+rUrl+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">View original speech ↗</a></div>':'';
  return`<tr class="${{rowCls}}" data-idx="${{i}}">
    <td class="td-date">${{fmt(d.date)}}</td>
    <td class="td-speaker" title="${{d.speaker}}">${{d.speaker}}</td>
    <td>
      <div class="title-text"><a href="${{rUrl}}" target="_blank" onclick="event.stopPropagation()">${{d.title}}</a>${{badge}}</div>
      <div class="td-justification">${{d.justification||''}}</div>
      ${{sourceBtn}}
      ${{bodySection}}
    </td>
    <td>${{scoreCell}}</td>
    <td class="td-toggle"><span class="chevron">&#8964;</span></td>
  </tr>`;
}}).join('');

document.getElementById('tbody').addEventListener('click',function(e){{
  if(e.target.tagName==='A')return;
  const r=e.target.closest('tr');
  if(!r)return;
  r.classList.toggle('expanded');
  if(r.classList.contains('expanded')){{
    const bodyDiv=r.querySelector('.td-body');
    if(bodyDiv&&!bodyDiv.dataset.loaded){{
      const di=byDate[parseInt(r.dataset.idx)];
      bodyDiv.innerHTML=fmtBody(di.body_en||di.body||'',realUrl(di.url||''));
      bodyDiv.dataset.loaded='1';
    }}
  }}
}});

let offVisible=false;
function applyTableFilters(){{
  const v=(document.getElementById('speaker-filter')||{{}}).value||'';
  document.querySelectorAll('#tbody tr').forEach(r=>{{
    const spk=r.querySelector('.td-speaker')?.title||'';
    const spkMatch=!v||spk===v;
    const isOff=r.classList.contains('off-topic');
    r.style.display=(!spkMatch||(isOff&&!offVisible))?'none':'table-row';
  }});
}}
function toggleOffTopic(){{
  offVisible=!offVisible;
  const btn=document.getElementById('toggle-btn');
  btn.textContent=offVisible?'Hide off-topic':'Show off-topic';
  btn.classList.toggle('active',offVisible);
  applyTableFilters();
}}
(function(){{
  const sel=document.getElementById('speaker-filter');
  if(!sel)return;
  const speakers=[...new Set(DATA.map(d=>d.speaker))].sort();
  sel.innerHTML='<option value="">All speakers</option>'+speakers.map(s=>`<option value="${{s}}">${{s}}</option>`).join('');
  sel.addEventListener('change',applyTableFilters);
}})();

(function(){{
  const PAL=["#2563EB","#DC2626","#16A34A","#F97316","#9333EA","#0891B2","#EC4899","#D97706","#475569","#6366F1","#65A30D","#BE185D","#0F766E","#A16207","#7C3AED"];
  const relev=DATA.filter(d=>d.relevant&&d.score>0);
  const spk={{}};
  relev.forEach(d=>{{if(!spk[d.speaker])spk[d.speaker]={{d:[],s:[]}};spk[d.speaker].d.push(d.date);spk[d.speaker].s.push(d.score);}});
  const q=Object.entries(spk).filter(([,v])=>v.s.length>=2).sort((a,b)=>a[0].localeCompare(b[0]));
  const el=document.getElementById('trend-legend');
  if(!el)return;
  el.innerHTML=q.map(([name,v],i)=>{{
    const avg=v.s.reduce((a,b)=>a+b,0)/v.s.length;
    const sd=[...v.d].sort();
    const tip=`${{sd[0]}} – ${{sd[sd.length-1]}}\nAvg: ${{avg.toFixed(1)}}/10 — ${{tone(Math.round(avg))}}`;
    const isActive=new Set(ACTIVE_MEMBERS).has(name);
    const lname=name.split(' ').pop();
    const nameHtml=isActive?`<strong>${{lname}}</strong>`:lname;
    return`<div class="tl-item" title="${{tip}}"><span class="tl-dot" style="background:${{PAL[i%PAL.length]}}"></span><span class="tl-name">${{nameHtml}}</span><span class="tl-avg" style="color:${{scoreColor(Math.round(avg))}}">${{avg.toFixed(1)}}</span></div>`;
  }}).join('');
  const trendPlot=document.querySelector('.trend-container .plotly-graph-div');
  let activeIdx=null;
  el.addEventListener('click',function(e){{
    const item=e.target.closest('.tl-item');
    if(!item||!trendPlot)return;
    const items=[...el.querySelectorAll('.tl-item')];
    const idx=items.indexOf(item);
    if(idx<0)return;
    const spkName=q[idx][0];
    const nT=trendPlot.data.length;
    const allIdxs=[...Array(nT).keys()];
    const spkIdxs=trendPlot.data.map((t,i)=>t.legendgroup===spkName?i:-1).filter(i=>i>=0);
    if(activeIdx===idx){{
      activeIdx=null;
      Plotly.restyle(trendPlot,{{opacity:1}},allIdxs);
      items.forEach(el=>{{el.style.opacity='';}});
    }}else{{
      activeIdx=idx;
      Plotly.restyle(trendPlot,{{opacity:0.08}},allIdxs);
      Plotly.restyle(trendPlot,{{opacity:1}},spkIdxs);
      items.forEach((el,i)=>{{el.style.opacity=i===idx?'1':'0.3';}});
    }}
  }});
}})();

(function(){{
  const ACTIVE=new Set(ACTIVE_MEMBERS);
  const relev=DATA.filter(d=>d.relevant&&d.score>0);
  const spk={{}};
  relev.forEach(d=>{{
    if(ACTIVE.size>0&&!ACTIVE.has(d.speaker))return;
    if(!spk[d.speaker])spk[d.speaker]=[];
    spk[d.speaker].push(d);
  }});
  const rows=Object.entries(spk)
    .map(([name,sps])=>{{
      sps.sort((a,b)=>a.date.localeCompare(b.date));
      const sc=sps.map(s=>s.score);
      const n=sc.length;
      const avg=sc.reduce((a,b)=>a+b,0)/n;
      const std=n>1?Math.sqrt(sc.reduce((a,b)=>a+(b-avg)**2,0)/n):0;
      const trend=n>=4?(()=>{{const r=sc.slice(-3).reduce((a,b)=>a+b,0)/3-avg;return r>0.7?'hawk':r<-0.7?'dove':'flat'}})():null;
      const flags=n>=3?sps.filter(s=>Math.abs(s.score-avg)>=2.5):[];
      return{{name,n,avg,std,trend,flags}};
    }})
    .filter(r=>r.n>=1)
    .sort((a,b)=>b.n-a.n||a.name.localeCompare(b.name));
  const tb=document.getElementById('stats-tbody');
  if(!tb)return;
  const cutoff=new Date();cutoff.setDate(cutoff.getDate()-90);
  tb.innerHTML=rows.map(r=>{{
    const ac=scoreColor(Math.round(r.avg));
    const tr2=r.trend===null?'<span class="spk-trend-flat">—</span>':r.trend==='hawk'?'<span class="spk-trend-hawk">↑ Hawkish</span>':r.trend==='dove'?'<span class="spk-trend-dove">↓ Dovish</span>':'<span class="spk-trend-flat">→ Stable</span>';
    const fl=r.flags.length===0?'<span class="no-flag">—</span>':r.flags.map(f=>{{
      const dev=f.score-r.avg;
      const isRecent=new Date(f.date)>=cutoff;
      const devStr=(dev>0?'+':'')+dev.toFixed(1);
      const tip=`${{f.date}}: "${{f.title}}"\nScore ${{f.score}}/10  (avg ${{r.avg.toFixed(1)}}, ${{devStr}} from avg)`;
      return`<span class="flag-chip flag-${{dev>0?'hawk':'dove'}}${{isRecent?' flag-recent':''}}" title="${{tip}}">${{f.date.slice(0,7)}} \xb7 ${{f.score}}/10 (${{devStr}})</span>`;
    }}).join('');
    return`<tr class="${{r.flags.length>0?'has-flag':''}}">
      <td class="st-name">${{r.name}}</td>
      <td><span class="st-avg" style="color:${{ac}}">${{r.avg.toFixed(1)}}</span></td>
      <td class="st-meta">${{r.n>1?r.std.toFixed(2):'—'}}</td>
      <td class="st-meta">${{r.n}}</td>
      <td>${{tr2}}</td>
      <td>${{fl}}</td>
    </tr>`;
  }}).join('');
}})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Generic generator
# ---------------------------------------------------------------------------

def generate_filtered_report(
    bank_db_name: str,
    bank_label: str,
    accent_color: str,
    output_path: Path,
    meetings: list,
    member_filter,
    active_members: List[str],
) -> None:
    if not DB_PATH.exists():
        print("No database found.")
        return

    today = date.today()
    cutoff = date(today.year - 5, today.month, today.day).isoformat()

    conn = sqlite3.connect(str(DB_PATH))
    _ensure_column(conn)

    df = pd.read_sql(
        "SELECT * FROM speeches WHERE central_bank=? AND score IS NOT NULL AND date >= ? ORDER BY date DESC",
        conn,
        params=(bank_db_name, cutoff),
    )

    if member_filter is not None:
        df = df[df.apply(lambda r: member_filter(r["speaker"], r["date"]), axis=1)].copy()

    if df.empty:
        print(f"No rated speeches for {bank_db_name} in the last 5 years.")
        conn.close()
        return

    _classify_and_store(conn, df)

    # Reload to pick up LLM classifications already in DB
    df = pd.read_sql(
        "SELECT * FROM speeches WHERE central_bank=? AND score IS NOT NULL AND date >= ? ORDER BY date DESC",
        conn,
        params=(bank_db_name, cutoff),
    )
    if member_filter is not None:
        df = df[df.apply(lambda r: member_filter(r["speaker"], r["date"]), axis=1)].copy()

    df["relevant_to_mp"] = df.apply(
        lambda r: _classify_relevance(r["title"], r["justification"], r["score"])
        if pd.isna(r.get("relevant_to_mp")) else int(r["relevant_to_mp"]),
        axis=1,
    )
    conn.close()

    # Normalize speaker names so title changes don't split one person into two
    from speaker_norm import normalize_speaker
    df["speaker"] = df.apply(lambda r: normalize_speaker(r["speaker"], r["central_bank"]), axis=1)

    df_relevant = df[df["relevant_to_mp"] == 1].copy()
    df_offtopic = df[df["relevant_to_mp"] == 0].copy()

    timeline_html = make_timeline_with_ghosts(df_relevant, df_offtopic, meetings=meetings)
    trend_html = make_trend_chart(df_relevant)
    theme_html = make_watchlist_chart(df)

    active_members_json = json.dumps(sorted(active_members))

    records = df.to_dict("records")
    for r in records:
        r["relevant"] = bool(r.get("relevant_to_mp", 1))
        if not r["relevant"]:
            r["offtopic_category"] = _offtopic_category(r.get("title", ""), r.get("justification", ""))

    off_count = sum(1 for r in records if not r["relevant"])
    print(f"  {len(records)} total speeches · {off_count} classified as off-topic")

    html = (
        PAGE_TEMPLATE
        .replace("__ACCENT__", accent_color)
        .replace("__BANK_LABEL__", bank_label)
        .format(
            timeline=timeline_html,
            trend_chart=trend_html,
            theme_chart=theme_html,
            data=json.dumps(records, default=str),
            active_members_json=active_members_json,
        )
    )
    output_path.write_text(html, encoding="utf-8")
    print(f"Report written to {output_path.resolve()}")
