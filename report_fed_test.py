"""
TEST COPY of the Fed report that ALSO includes Congressional testimony (experimental).

Unlike the live report_fed_filtered.py (which filters testimony out), this version
pulls testimony rows in too and marks them distinctly on the charts (diamonds) so we
can eyeball whether testimony adds monetary-policy signal. Writes report_fed_test.html.

Run:  python report_fed_test.py
"""

import html as _html
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

import plotly.graph_objects as go
import plotly.io as pio

from report_frb import (
    score_color, tone, wrap_text,
    make_trend_chart,
    _add_meeting_vlines,
    SPEAKER_PALETTE,
)
from rater import SYSTEM as RATING_PROMPT

DB_PATH = Path("data/speeches.db")
OUTPUT_PATH = Path("report_fed_test.html")


# ---------------------------------------------------------------------------
# Relevance classification (keyword-based, replaced by LLM later)
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
    """Return 1 (relevant to monetary policy) or 0 (off-topic).
    Hawkish/dovish scores are always relevant; only neutrals need classification."""
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
    """Return a short human-readable label for why a speech was flagged off-topic."""
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
    # fall back to justification
    if _REGULATORY.search(j):
        return "Regulatory"
    if _FINANCIAL_STABILITY.search(j):
        return "Financial Stability"
    if _CEREMONIAL.search(j):
        return "Ceremonial"
    return "Off-topic"


NEUTRAL_GREEN = "#7A9E87"  # dusty sage — neutral-on-MP colour

def _dot_color(score):
    """Hawkish/dovish use the standard ramp; neutral-relevant gets dusty green."""
    if 4 <= score <= 6:
        return NEUTRAL_GREEN
    return score_color(score)


def make_timeline_with_ghosts(
    df_relevant: pd.DataFrame,
    df_offtopic: pd.DataFrame,
    meetings=None,
) -> str:
    """Timeline showing relevant speeches as solid dots and off-topic as hollow ghost dots."""
    asc = df_relevant.sort_values("date")
    colors = [_dot_color(s) for s in asc["score"]]

    def _is_test(u):
        return "/newsevents/testimony/" in (u or "")

    rel_test = [_is_test(u) for u in asc["url"]]

    def _test_tag(is_t):
        return ("<span style='color:#7C3AED;font-weight:700;font-size:10px;letter-spacing:.08em'>"
                "◆ TESTIMONY</span><br>") if is_t else ""

    hover_rel = [
        _test_tag(_is_test(r["url"]))
        + f"<span style='color:#111827;font-weight:600'>{r['speaker']}</span><br>"
        f"<span style='color:#374151'>{r['title']}</span><br>"
        f"<span style='color:#6B7280'>{r['date']}</span><br><br>"
        f"<span style='color:{score_color(r['score'])};font-weight:700'>{r['score']}/10 — {tone(r['score'])}</span><br><br>"
        f"<span style='color:#374151'>{wrap_text(r['justification'])}</span>"
        for _, r in asc.iterrows()
    ]

    fig = go.Figure()
    fig.add_hrect(y0=7, y1=10, fillcolor="rgba(220,38,38,0.04)", line_width=0)
    fig.add_hrect(y0=1, y1=3, fillcolor="rgba(37,99,235,0.04)", line_width=0)

    # Connecting line (relevant only)
    fig.add_trace(go.Scatter(
        x=asc["date"], y=asc["score"],
        mode="lines",
        line=dict(color="rgba(17,24,39,0.12)", width=1),
        hoverinfo="skip", showlegend=False,
    ))

    # Rolling average (relevant only)
    rolling = asc["score"].rolling(window=10, min_periods=3).mean()
    fig.add_trace(go.Scatter(
        x=asc["date"], y=rolling,
        mode="lines",
        line=dict(color="rgba(17,24,39,0.55)", width=2.5),
        hoverinfo="skip", showlegend=False,
    ))

    # Ghost dots — off-topic speeches (hollow, faint)
    if not df_offtopic.empty:
        ghost = df_offtopic.sort_values("date")
        ghost_y = ghost.apply(
            lambda r: int(r["original_score"]) if pd.notna(r.get("original_score")) and r.get("original_score") else 5,
            axis=1,
        )
        ghost_test = [_is_test(u) for u in ghost["url"]]
        ghost_hover = [
            [
                _test_tag(_is_test(r["url"]))
                + f"<span style='color:#9CA3AF;font-weight:600'>{r['speaker']}</span><br>"
                f"<span style='color:#9CA3AF'>{r['title']}</span><br>"
                f"<span style='color:#D1D5DB'>{r['date']}</span><br>"
                f"<span style='color:#D1D5DB;font-size:11px'>Off-topic · not counted in signal</span>",
                r["url"],
            ]
            for _, r in ghost.iterrows()
        ]
        fig.add_trace(go.Scatter(
            x=ghost["date"], y=ghost_y,
            mode="markers",
            marker=dict(
                color="rgba(255,255,255,0)",
                size=[9 if t else 7 for t in ghost_test],
                symbol=["diamond-open" if t else "circle" for t in ghost_test],
                line=dict(color="rgba(156,163,175,0.45)", width=1.5),
            ),
            hovertemplate="%{customdata[0]}<extra></extra>",
            customdata=ghost_hover,
            showlegend=False,
            name="Off-topic",
        ))

    # Solid dots — relevant speeches. customdata carries [hover_html, url] so a
    # click can jump to this speech's row in the table below.
    solid_cd = [[h, u] for h, u in zip(hover_rel, asc["url"].tolist())]
    fig.add_trace(go.Scatter(
        x=asc["date"], y=asc["score"],
        mode="markers",
        marker=dict(
            color=colors,
            size=[12 if t else 9 for t in rel_test],
            symbol=["diamond" if t else "circle" for t in rel_test],
            line=dict(color="white", width=1.5),
        ),
        hovertemplate="%{customdata[0]}<extra></extra>",
        customdata=solid_cd,
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


def make_trend_chart_linked(df: pd.DataFrame) -> str:
    """Local copy of report_frb.make_trend_chart, but each marker's customdata carries
    [hover_html, url] so clicking a dot can jump to that speech in the table below.
    Trace structure (line + markers per speaker, legendgroup=speaker) is unchanged so
    the existing trend-legend highlight logic keeps working."""
    df = df[df["score"] > 0]
    counts = df.groupby("speaker")["score"].count()
    speakers = sorted(counts[counts >= 2].index.tolist())
    color_map = {sp: SPEAKER_PALETTE[i % len(SPEAKER_PALETTE)] for i, sp in enumerate(speakers)}

    fig = go.Figure()
    fig.add_hrect(y0=7, y1=10, fillcolor="rgba(220,38,38,0.04)", line_width=0)
    fig.add_hrect(y0=1, y1=3, fillcolor="rgba(37,99,235,0.04)", line_width=0)

    for speaker in speakers:
        sdf = df[df["speaker"] == speaker].sort_values("date")
        color = color_map[speaker]
        avg = sdf["score"].mean()
        short = speaker.split()[-1]
        date_range = f"{sdf['date'].min()} – {sdf['date'].max()}"

        s_test = ["/newsevents/testimony/" in (u or "") for u in sdf["url"]]
        cd = [
            [
                ("<span style='color:#7C3AED;font-weight:700;font-size:10px'>◆ TESTIMONY</span><br>"
                 if "/newsevents/testimony/" in (r["url"] or "") else "")
                + f"<span style='color:#111827;font-weight:600'>{speaker}</span><br>"
                f"<span style='color:#374151'>{r['title']}</span><br>"
                f"<span style='color:#6B7280'>{r['date']}</span><br><br>"
                f"<span style='color:{score_color(r['score'])};font-weight:700'>{r['score']}/10 — {tone(r['score'])}</span><br>"
                f"<span style='color:#9CA3AF;font-size:11px'>Avg {avg:.1f} · {date_range}</span>",
                r["url"],
            ]
            for _, r in sdf.iterrows()
        ]

        fig.add_trace(go.Scatter(
            x=sdf["date"], y=sdf["score"],
            mode="lines", name=short, legendgroup=speaker, showlegend=False,
            line=dict(color=color, width=1.5), hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=sdf["date"], y=sdf["score"],
            mode="markers", name=short, legendgroup=speaker, showlegend=False,
            marker=dict(color=color, size=[11 if t else 8 for t in s_test],
                        symbol=["diamond" if t else "circle" for t in s_test],
                        line=dict(color="white", width=1.5), opacity=0.9),
            hovertemplate="%{customdata[0]}<extra></extra>",
            customdata=cd,
        ))

    fig.update_layout(
        height=380,
        margin=dict(l=48, r=20, t=24, b=40),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="system-ui, -apple-system, sans-serif", size=11, color="#6B7280"),
        yaxis=dict(range=[0.5, 10.5], tickvals=[1, 3, 5, 7, 10],
                   gridcolor="#F0F1F3", gridwidth=1, zeroline=False, title=None),
        xaxis=dict(gridcolor="#F0F1F3", gridwidth=1, zeroline=False,
                   title=None, tickformat="%b %Y"),
        showlegend=False,
        hoverlabel=dict(bgcolor="white", bordercolor="#E4E8EF",
                        font=dict(size=12, color="#111827",
                                  family="system-ui, -apple-system, sans-serif"),
                        align="left", namelength=0),
        annotations=[
            dict(x=0, xref="paper", y=10, yref="y", text="HAWK", showarrow=False,
                 font=dict(size=9, color="#DC2626", family="system-ui"), xanchor="left"),
            dict(x=0, xref="paper", y=1, yref="y", text="DOVE", showarrow=False,
                 font=dict(size=9, color="#2563EB", family="system-ui"), xanchor="left"),
        ],
    )
    return pio.to_html(fig, include_plotlyjs=False, full_html=False,
                       config={"displayModeBar": False, "responsive": True})


def _ensure_column(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(speeches)")}
    if "relevant_to_mp" not in cols:
        conn.execute("ALTER TABLE speeches ADD COLUMN relevant_to_mp INTEGER")
        conn.commit()


def _classify_and_store(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    """Write keyword classification to DB for rows with no source (never overwrites llm or manual)."""
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
# Report template
# ---------------------------------------------------------------------------

PAGE_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fed Policy Sentiment Tracker (Test + Testimony)</title>
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
.eyebrow{{font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:#2563EB;margin-bottom:5px}}
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
@keyframes rowflash{{0%{{background:#FDE68A}}55%{{background:#FEF3C7}}100%{{background:transparent}}}}
tbody tr.flash td{{animation:rowflash 1.7s ease-out}}

/* Off-topic row styling */
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
.testimony-badge{{display:inline-block;font-size:9px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;border-radius:3px;padding:2px 6px;margin-left:7px;vertical-align:middle;white-space:nowrap;color:#5B21B6;background:#EDE9FE;cursor:help}}

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

/* Supporting quotes (evidence for the score) */
.td-evidence{{max-height:0;overflow:hidden;opacity:0;transition:max-height .35s ease,opacity .25s ease,margin-top .2s ease;margin-top:0}}
tr.expanded .td-evidence{{max-height:520px;opacity:1;margin-top:12px}}
.ev-quote{{font-size:12.5px;line-height:1.6;color:#374151;background:#F9FAFB;border-left:3px solid #D1D5DB;border-radius:0 4px 4px 0;padding:8px 12px;margin:6px 0}}
.ev-quote::before{{content:'\\201C'}}.ev-quote::after{{content:'\\201D'}}
.ev-quote.ev-hawk{{border-left-color:#DC2626;background:#FEF2F2}}
.ev-quote.ev-dove{{border-left-color:#2563EB;background:#EFF4FE}}
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
.mk-sep{{width:1px;height:12px;background:#E4E8EF;margin:0 2px}}

/* Compact current-rate strip below the score-history chart */
.rate-box{{
  display:inline-flex;align-items:baseline;gap:10px;flex-wrap:wrap;
  background:#fff;border:1px solid #E4E8EF;border-radius:5px;
  padding:7px 13px;margin-top:10px;font-size:12px;
}}
.rate-box-label{{font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#9CA3AF}}
.rate-box-value{{font-weight:700;font-size:14px;color:#111827;font-variant-numeric:tabular-nums}}
.rate-box-move{{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600}}
.rate-box-move .arrow{{font-size:11px;line-height:1}}
.rate-box-move.hike{{color:#B91C1C}}
.rate-box-move.cut{{color:#1D4ED8}}
.rate-box-move.hold{{color:#6B7280}}
.rate-box-since{{font-size:11px;color:#9CA3AF}}

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
.trend-line{{display:flex;align-items:center;gap:7px;white-space:nowrap;line-height:1.7;font-size:12px}}
.trend-line+.trend-line{{margin-top:1px}}
.trend-lbl{{font-size:9px;font-weight:700;letter-spacing:.06em;color:#B0B6BE;min-width:16px}}
.no-flag{{color:#D1D5DB}}
.flag-chip{{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:10px;font-size:11px;margin:2px 3px 2px 0;cursor:default;white-space:nowrap;line-height:1.4}}
.flag-hawk{{background:#FEE2E2;color:#B91C1C}}
.flag-dove{{background:#DBEAFE;color:#1D4ED8}}
.flag-recent{{font-weight:700;outline:1px solid currentColor;outline-offset:1px}}

.filter-notice{{
  font-size:11px;color:#6B7280;background:#F9FAFB;border:1px solid #E4E8EF;
  border-radius:4px;padding:8px 12px;margin-bottom:16px;
}}

/* Scoring methodology panel */
.method{{
  background:#fff;border:1px solid #E4E8EF;border-radius:6px;
  margin-bottom:40px;overflow:hidden;
}}
.method>summary{{
  list-style:none;cursor:pointer;padding:15px 20px;
  display:flex;align-items:center;gap:10px;
  font-size:12px;font-weight:600;color:#374151;user-select:none;
}}
.method>summary::-webkit-details-marker{{display:none}}
.method>summary:hover{{background:#FAFBFC}}
.method-icon{{
  display:inline-flex;align-items:center;justify-content:center;
  width:20px;height:20px;border-radius:50%;background:#EEF2FF;color:#4F46E5;
  font-size:12px;font-weight:700;flex-shrink:0;
}}
.method-sub{{font-size:11px;font-weight:400;color:#9CA3AF;margin-left:2px}}
.method-chevron{{margin-left:auto;color:#9CA3AF;font-size:11px;transition:transform .2s ease}}
.method[open] .method-chevron{{transform:rotate(180deg)}}
.method-body{{padding:0 20px 20px;border-top:1px solid #F3F4F6}}
.method-intro{{
  font-size:12.5px;color:#6B7280;line-height:1.7;margin:16px 0 14px;max-width:74ch;
}}
.method-intro code{{
  background:#F3F4F6;border-radius:3px;padding:1px 5px;font-size:11.5px;
  color:#374151;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}}
.method-prompt-label{{
  font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
  color:#9CA3AF;margin-bottom:8px;
}}
.method-prompt{{
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:11.5px;line-height:1.65;color:#374151;
  background:#F9FAFB;border:1px solid #E4E8EF;border-radius:5px;
  padding:16px 18px;white-space:pre-wrap;word-break:break-word;
  max-height:440px;overflow-y:auto;
}}
.method-foot{{font-size:11px;color:#9CA3AF;margin-top:12px;line-height:1.6}}

/* "Since the last decision" sentiment gauge */
.since-card{{
  background:#fff;border:1px solid #E4E8EF;border-radius:6px;
  padding:20px 26px;margin-bottom:40px;
}}
.since-label{{font-size:9px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:#9CA3AF;margin-bottom:14px}}
.since-body{{display:flex;align-items:baseline;gap:18px;flex-wrap:wrap}}
.since-verdict{{font-family:Georgia,serif;font-size:26px;font-weight:normal;line-height:1;display:inline-flex;align-items:baseline;gap:8px}}
.since-arrow{{font-size:19px}}
.since-stats{{font-size:12.5px;color:#6B7280;line-height:1.6}}
.since-empty{{font-size:13px;color:#9CA3AF}}
.since-lowconf{{color:#B45309;font-weight:600}}
.since-caveat{{font-size:11px;color:#9CA3AF;margin-top:14px;line-height:1.6;max-width:72ch}}
</style>
</head>
<body>
<div class="page">

<header>
  <div>
    <div class="eyebrow">Federal Reserve</div>
    <h1>Policy Sentiment Tracker</h1>
    <div class="header-sub">TEST · Congressional testimony included &amp; marked as &#9670; diamonds · off-topic neutral items filtered</div>
  </div>
  <div class="header-meta" id="hm"></div>
</header>

<details class="method">
  <summary>
    <span class="method-icon">?</span>
    How is each speech scored?
    <span class="method-sub">View the exact prompt used to judge hawkishness / dovishness</span>
    <span class="method-chevron">&#8964;</span>
  </summary>
  <div class="method-body">
    <p class="method-intro">
      Every speech is read by an LLM (OpenAI <code>gpt-4.1</code>, temperature&nbsp;0) and rated on a
      0&ndash;10 hawkish&ndash;dovish scale. <strong>0</strong> means off-topic (no monetary-policy signal),
      <strong>1&ndash;3</strong> dovish, <strong>4&ndash;6</strong> neutral, <strong>7&ndash;10</strong> hawkish.
      The model also returns the one- or two-sentence justification you see when you expand a row.
      Below is the <em>verbatim</em> system prompt that instructs the model &mdash; the same one applied to every
      speech in this report, so scoring is consistent across speakers and dates.
    </p>
    <div class="method-prompt-label">System prompt &middot; verbatim</div>
    <div class="method-prompt">{scoring_prompt}</div>
    <p class="method-foot">
      Each speech is sent with its title, speaker, date, the policy rate in effect at the time, and the
      speaker's recent scoring history, followed by the full speech text.
    </p>
  </div>
</details>

<div id="latest-wrap"></div>

{since_card}

<section class="chart-section">
  <div class="section-header">
    <span class="section-title">Score History &middot; Last 5 Years &middot; Hollow dots = off-topic (not counted)</span>
    <div class="section-rule"></div>
  </div>
  <div class="chart-wrap" id="timeline-chart">{timeline}</div>
  {rate_box}
  <div class="meeting-key">
    <span class="mk-item"><span style="color:#6B7280;font-size:13px">&#9679;</span>Speech</span>
    <span class="mk-item"><span style="color:#7C3AED;font-size:13px">&#9670;</span>Testimony</span>
    <span class="mk-sep"></span>
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
  if(s===0)return'#9CA3AF';
  const t=(s-1)/9;
  if(t<=0.5){{const u=t*2;return`rgb(${{lerp(37,107,u)}},${{lerp(99,114,u)}},${{lerp(235,128,u)}})`}}
  const u=(t-0.5)*2;return`rgb(${{lerp(107,220,u)}},${{lerp(114,38,u)}},${{lerp(128,38,u)}})`;
}}
function tone(s){{return s===0?'Off-topic':s<=3?'Dovish':s<=6?'Neutral':'Hawkish'}}
function fmt(iso){{return new Date(iso+'T00:00:00').toLocaleDateString('en-US',{{month:'short',day:'numeric',year:'numeric'}})}}
function escHtml(s){{return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}

const n=DATA.length;
const nRelev=DATA.filter(d=>d.relevant).length;
const nOff=n-nRelev;
const ts=new Date().toLocaleDateString('en-US',{{month:'long',day:'numeric',year:'numeric'}});
document.getElementById('hm').innerHTML=`Updated ${{ts}}<br>${{n}} speech${{n!==1?'es':''}} total · ${{nOff}} off-topic`;

// Latest-speech card: use latest relevant speech
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

// Filter notice
const notice=document.getElementById('filter-notice');
if(nOff>0){{
  notice.textContent=`${{nOff}} off-topic neutral speech${{nOff!==1?'es are':' is'}} hidden below (ceremonial remarks, regulatory/operational topics, fintech). Click "Show off-topic" to reveal them faded.`;
}}else{{
  notice.style.display='none';
}}

// Table — all speeches, off-topic rows get class off-topic and hidden by default
function fmtBody(txt,url){{
  if(!txt||txt==='nan'||txt==='None') return '';
  function esc(s){{return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
  txt=txt.replace(/\\r\\n/g,'\\n').replace(/\\r/g,'\\n');
  txt=txt.replace(/Official websites use \\.gov[\\s\\S]*?Share sensitive information only on official, secure websites\\.\\s*/,'').trim();
  txt=txt.replace(/The Federal Reserve, the central bank of the United States[\\s\\S]*?system\\.\\s*/,'').trim();
  txt=txt.replace(/^\\s*SPEECH[\\s\\S]*?(?:\\d{{1,2}}\\s+\\w+\\s+20\\d\\d|\\w+\\s+\\d{{1,2}},\\s*20\\d\\d)\\s*/,'').trim();
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
const REASONS = {{
  title: 'Title indicates off-topic content (ceremonial, regulatory, operational, fintech)',
  just:  'Justification indicates no monetary policy signal',
}};
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
  const testBadge=d.is_testimony?'<span class="testimony-badge" title="Congressional testimony, not a speech">&#9670; Testimony</span>':'';
  const rowCls=isOff?'off-topic hidden':'';
  const hasBody=!!(d.body&&d.body!=='nan'&&d.body!=='None');
  const bodySection=hasBody?'<div class="td-body-section"><span class="td-body-label">Full speech text</span><div class="td-body"></div></div>':'';
  const sourceBtn=d.url?'<div class="td-source-link"><a class="source-btn" href="'+d.url+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">View original speech ↗</a></div>':'';
  let evq=[];try{{evq=d.evidence_quotes?(typeof d.evidence_quotes==='string'?JSON.parse(d.evidence_quotes):d.evidence_quotes):[];}}catch(e){{evq=[];}}
  const evidenceSection=(evq&&evq.length)?'<div class="td-evidence"><span class="td-body-label">Supporting quotes</span>'+evq.map(q=>'<div class="ev-quote ev-'+(q.lean==='hawkish'?'hawk':'dove')+'">'+escHtml(q.quote)+'</div>').join('')+'</div>':'';
  return`<tr class="${{rowCls}}" data-idx="${{i}}">
    <td class="td-date">${{fmt(d.date)}}</td>
    <td class="td-speaker" title="${{d.speaker}}">${{d.speaker}}</td>
    <td>
      <div class="title-text"><a href="${{d.url}}" target="_blank" onclick="event.stopPropagation()">${{d.title}}</a>${{testBadge}}${{badge}}</div>
      <div class="td-justification">${{d.justification||''}}</div>
      ${{evidenceSection}}
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
      bodyDiv.innerHTML=fmtBody(di.body||'',di.url||'');
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

// Trend legend (relevant speeches only)
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

// Speaker stats (relevant speeches, active members only)
(function(){{
  const ACTIVE=new Set(ACTIVE_MEMBERS);
  const relev=DATA.filter(d=>d.relevant&&d.score>0);
  const spk={{}};
  relev.forEach(d=>{{
    if(ACTIVE.size>0&&!ACTIVE.has(d.speaker))return;
    if(!spk[d.speaker])spk[d.speaker]=[];
    spk[d.speaker].push(d);
  }});
  // Half-vs-half trend within a window: later-half mean minus earlier-half mean.
  function halfTrend(arr){{
    const m=arr.length;
    if(m<4) return null;                 // need enough speeches to split meaningfully
    const half=Math.floor(m/2);
    const mean=a=>a.reduce((x,d)=>x+d.score,0)/a.length;
    const d=mean(arr.slice(m-half))-mean(arr.slice(0,half));
    return {{dir:d>0.7?'hawk':d<-0.7?'dove':'flat',d:d,n:m}};
  }}
  function trendChip(t,label,win){{
    if(!t) return '<div class="trend-line" title="'+win+': not enough speeches for a trend"><span class="trend-lbl">'+label+'</span><span class="spk-trend-flat">—</span></div>';
    const txt=t.dir==='hawk'?'<span class="spk-trend-hawk">↑ Hawkish</span>':t.dir==='dove'?'<span class="spk-trend-dove">↓ Dovish</span>':'<span class="spk-trend-flat">→ Stable</span>';
    const tip=win+' ('+t.n+' speeches): later half '+(t.d>0?'+':'')+t.d.toFixed(1)+' vs earlier half';
    return '<div class="trend-line" title="'+tip+'"><span class="trend-lbl">'+label+'</span>'+txt+'</div>';
  }}
  const oneYearAgo=new Date();oneYearAgo.setFullYear(oneYearAgo.getFullYear()-1);
  const rows=Object.entries(spk)
    .map(([name,sps])=>{{
      sps.sort((a,b)=>a.date.localeCompare(b.date));
      const sc=sps.map(s=>s.score);
      const n=sc.length;
      const avg=sc.reduce((a,b)=>a+b,0)/n;
      const std=n>1?Math.sqrt(sc.reduce((a,b)=>a+(b-avg)**2,0)/n):0;
      const sps1y=sps.filter(s=>new Date(s.date+'T00:00:00')>=oneYearAgo);
      const trend1y=halfTrend(sps1y);
      const trend5y=halfTrend(sps);
      const flags=n>=3?sps.filter(s=>Math.abs(s.score-avg)>=2.5):[];
      return{{name,n,avg,std,trend1y,trend5y,flags}};
    }})
    .filter(r=>r.n>=1)
    .sort((a,b)=>b.n-a.n||a.name.localeCompare(b.name));
  const tb=document.getElementById('stats-tbody');
  if(!tb)return;
  const cutoff=new Date();cutoff.setDate(cutoff.getDate()-90);
  tb.innerHTML=rows.map(r=>{{
    const ac=scoreColor(Math.round(r.avg));
    const trCell=trendChip(r.trend1y,'1Y','Last 12 months')+trendChip(r.trend5y,'5Y','Full 5-year window');
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
      <td>${{trCell}}</td>
      <td>${{fl}}</td>
    </tr>`;
  }}).join('');
}})();

// --- Click a chart dot -> reveal & scroll to that speech in the table ---
function jumpToSpeech(url){{
  if(!url) return;
  const rows=[...document.querySelectorAll('#tbody tr')];
  const row=rows.find(r=>{{const d=byDate[parseInt(r.dataset.idx)];return d&&d.url===url;}});
  if(!row) return;
  // Ensure the row is visible: clear any speaker filter, reveal off-topic if hidden.
  const sel=document.getElementById('speaker-filter');
  if(sel) sel.value='';
  if(row.classList.contains('off-topic')&&!offVisible){{ toggleOffTopic(); }}
  else {{ applyTableFilters(); }}
  // Expand it (and lazy-load the full text, mirroring the row-click handler).
  if(!row.classList.contains('expanded')){{
    row.classList.add('expanded');
    const bodyDiv=row.querySelector('.td-body');
    if(bodyDiv&&!bodyDiv.dataset.loaded){{
      const di=byDate[parseInt(row.dataset.idx)];
      bodyDiv.innerHTML=fmtBody(di.body||'',di.url||'');
      bodyDiv.dataset.loaded='1';
    }}
  }}
  row.scrollIntoView({{behavior:'smooth',block:'center'}});
  row.classList.remove('flash');
  void row.offsetWidth;              // restart the flash animation if re-clicked
  row.classList.add('flash');
  setTimeout(()=>row.classList.remove('flash'),1700);
}}
(function bindDotClicks(tries){{
  tries=tries||0;
  const sels=['#timeline-chart .plotly-graph-div','.trend-container .plotly-graph-div'];
  let allReady=true;
  sels.forEach(sel=>{{
    const gd=document.querySelector(sel);
    if(!gd) return;                  // chart may be absent (e.g. no data)
    if(!gd.on){{ allReady=false; return; }}
    if(gd.dataset.clickBound) return;
    gd.dataset.clickBound='1';
    gd.on('plotly_click',function(e){{
      const pt=e.points&&e.points[0];
      if(!pt||!pt.customdata) return;
      const url=Array.isArray(pt.customdata)?pt.customdata[1]:null;
      jumpToSpeech(url);
    }});
    gd.style.cursor='pointer';
  }});
  if(!allReady&&tries<25) setTimeout(()=>bindDotClicks(tries+1),150);
}})(0);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Current-rate box
# ---------------------------------------------------------------------------

def _current_rate_box(meetings, label: str = "Current Fed Funds Rate") -> str:
    """Build the small box shown beside the score-history chart: the active policy
    rate, the last committee decision (with a hike/cut/hold arrow), and how long
    the rate has been in effect. Returns "" if there are no dated rate meetings."""
    from datetime import datetime

    past = sorted(
        [m for m in meetings if m.get("decision") != "upcoming" and m.get("rate")],
        key=lambda m: m["date"],
    )
    if not past:
        return ""

    latest = past[-1]
    rate = _html.escape(latest.get("rate", ""))
    dec = latest.get("decision", "hold")
    move_label = _html.escape(latest.get("label", "").replace("\n", " ").strip())

    def _fmt(d, short=False):
        dt = datetime.strptime(d, "%Y-%m-%d")
        return dt.strftime("%b %Y") if short else f"{dt.strftime('%b')} {dt.day}, {dt.year}"

    arrows = {"hike": "&#9650;", "cut": "&#9660;", "hold": "&mdash;"}
    arrow = arrows.get(dec, "&mdash;")
    move_class = dec if dec in ("hike", "cut", "hold") else "hold"

    # When did the current rate level take effect? = most recent hike/cut.
    changes = [m for m in past if m.get("decision") in ("hike", "cut")]
    since = changes[-1]["date"] if changes else past[0]["date"]

    return (
        '<div class="rate-box">'
        f'<span class="rate-box-label">{label}</span>'
        f'<span class="rate-box-value">{rate}</span>'
        f'<span class="rate-box-move {move_class}"><span class="arrow">{arrow}</span>{move_label}</span>'
        f'<span class="rate-box-since">unchanged since {_fmt(since, short=True)}</span>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# "Since the last decision" sentiment gauge
# ---------------------------------------------------------------------------

def _lerp_hex(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two #RRGGBB colours (t clamped to 0..1)."""
    t = max(0.0, min(1.0, t))
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    r, g, bl = (round(a[j] + (b[j] - a[j]) * t) for j in range(3))
    return f"#{r:02X}{g:02X}{bl:02X}"


def _lean_style(avg: float):
    """Map an average score to (label, arrow, colour). 4–6 is neutral; below 4 is
    dovish and above 6 hawkish, with colour intensity scaled to conviction — pale
    near the neutral band, deepening toward the extremes."""
    if avg < 4:
        t = (4 - avg) / 3.0          # 0 just below 4 (pale) → 1 at 1 (deep)
        label = "Dovish" if avg < 2 else "Leaning dovish"
        return label, "&#9662;", _lerp_hex("#93C5FD", "#1E3A8A", t)
    if avg > 6:
        t = (avg - 6) / 4.0          # 0 just above 6 (pale) → 1 at 10 (deep)
        label = "Hawkish" if avg > 8 else "Leaning hawkish"
        return label, "&#9652;", _lerp_hex("#FCA5A5", "#7F1D1D", t)
    return "Neutral", "", NEUTRAL_GREEN


def _since_meeting_card(df_relevant: pd.DataFrame, meetings,
                        decision_name: str = "FOMC decision") -> str:
    """Aggregate the tone of relevant speeches made since the most recent committee
    decision into a soft dovish/hawkish read. Returns the card HTML, or "" if there
    is no meeting data.

    Deliberately hedged: reports a 'tilt', not a rate-move forecast. Flags a limited
    signal when fewer than 3 speeches, and shows an empty state when there are none."""
    from datetime import datetime

    past = sorted([m for m in meetings if m.get("decision") != "upcoming" and m.get("date")],
                  key=lambda m: m["date"])
    if not past:
        return ""
    lm = past[-1]
    md = lm["date"]
    dt = datetime.strptime(md, "%Y-%m-%d")
    md_fmt = f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    label = _html.escape((lm.get("label") or lm.get("decision", "")).replace("\n", " ").strip())
    header = f"Since the last {decision_name} &middot; {md_fmt}" + (f" ({label})" if label else "")

    sub = df_relevant[(df_relevant["date"] > md) & (df_relevant["score"] > 0)]
    if sub.empty:
        return (
            '<div class="since-card">'
            f'<div class="since-label">{header}</div>'
            '<div class="since-empty">No policy-relevant speeches yet since this meeting.</div>'
            '</div>'
        )

    scores = sub["score"].astype(float)
    n = len(sub)
    avg = scores.mean()
    n_dove = int((scores <= 3).sum())
    n_neut = int(((scores >= 4) & (scores <= 6)).sum())
    n_hawk = int((scores >= 7).sum())

    lean, arrow, col = _lean_style(avg)

    arrow_html = f'<span class="since-arrow">{arrow}</span>' if arrow else ""
    plural = "es" if n != 1 else ""
    stats = (f"{n} relevant speech{plural} &middot; avg {avg:.1f}/10 &middot; "
             f"{n_dove} dovish &middot; {n_neut} neutral &middot; {n_hawk} hawkish")
    if n < 3:
        stats += (f'<br><span class="since-lowconf">Limited signal '
                  f'&mdash; only {n} speech{plural} so far</span>')

    return (
        '<div class="since-card">'
        f'<div class="since-label">{header}</div>'
        '<div class="since-body">'
        f'<div class="since-verdict" style="color:{col}">{arrow_html}{lean}</div>'
        f'<div class="since-stats">{stats}</div>'
        '</div>'
        '<div class="since-caveat">Aggregate tone of public remarks since the meeting '
        '&mdash; a read on rhetoric, not a forecast of the next rate decision.</div>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

def generate_fed_filtered_report() -> None:
    if not DB_PATH.exists():
        print("No database found.")
        return

    from meetings import get_meetings
    FED_MEETINGS = get_meetings("Federal Reserve")
    today = date.today()
    cutoff = date(today.year - 5, today.month, today.day).isoformat()

    conn = sqlite3.connect(str(DB_PATH))
    _ensure_column(conn)

    df = pd.read_sql(
        "SELECT * FROM speeches WHERE central_bank='Federal Reserve' AND score IS NOT NULL "
        "AND date >= ? ORDER BY date DESC",  # test: INCLUDES testimony
        conn,
        params=(cutoff,),
    )

    # Filter to actual Fed members
    from membership import was_member
    df = df[df.apply(lambda r: was_member("fed", r["speaker"], r["date"]), axis=1)].copy()

    # Classify and persist
    _classify_and_store(conn, df)

    # Reload with relevant_to_mp populated
    df = pd.read_sql(
        "SELECT * FROM speeches WHERE central_bank='Federal Reserve' AND score IS NOT NULL "
        "AND date >= ? ORDER BY date DESC",  # test: INCLUDES testimony
        conn,
        params=(cutoff,),
    )
    from membership import was_member as _wm
    df = df[df.apply(lambda r: _wm("fed", r["speaker"], r["date"]), axis=1)].copy()

    # Fill any remaining NULLs (shouldn't happen after classify_and_store, but safe)
    df["relevant_to_mp"] = df.apply(
        lambda r: _classify_relevance(r["title"], r["justification"], r["score"])
        if pd.isna(r.get("relevant_to_mp")) else int(r["relevant_to_mp"]),
        axis=1,
    )
    conn.close()

    # Normalize speaker names so title changes don't split one person into two
    from speaker_norm import normalize_speaker
    df["speaker"] = df.apply(lambda r: normalize_speaker(r["speaker"], r["central_bank"]), axis=1)

    # Charts use relevant speeches as signal; off-topic shown as ghosts
    df_relevant = df[df["relevant_to_mp"] == 1].copy()
    df_offtopic = df[df["relevant_to_mp"] == 0].copy()

    timeline_html = make_timeline_with_ghosts(df_relevant, df_offtopic, meetings=FED_MEETINGS)
    trend_html = make_trend_chart_linked(df_relevant)
    from report_filtered_base import make_watchlist_chart
    theme_html = make_watchlist_chart(df)

    recent_cutoff = date(today.year - 1, today.month, today.day).isoformat()
    active_members_json = json.dumps(
        sorted(df_relevant[df_relevant["date"] >= recent_cutoff]["speaker"].unique().tolist())
    )

    # Build DATA — all speeches, with relevant flag and category
    records = df.to_dict("records")
    for r in records:
        r["relevant"] = bool(r.get("relevant_to_mp", 1))
        r["is_testimony"] = "/newsevents/testimony/" in (r.get("url") or "")
        if not r["relevant"]:
            r["offtopic_category"] = _offtopic_category(r.get("title", ""), r.get("justification", ""))

    off_count = sum(1 for r in records if not r["relevant"])
    n_test = sum(1 for r in records if r["is_testimony"])
    print(f"  {len(records)} total items · {off_count} off-topic · {n_test} testimony")

    html = PAGE_TEMPLATE.format(
        timeline=timeline_html,
        trend_chart=trend_html,
        theme_chart=theme_html,
        data=json.dumps(records, default=str),
        active_members_json=active_members_json,
        scoring_prompt=_html.escape(RATING_PROMPT),
        rate_box=_current_rate_box(FED_MEETINGS),
        since_card=_since_meeting_card(df_relevant, FED_MEETINGS),
    )
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Report written to {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    generate_fed_filtered_report()
