"""
Generate a side-by-side comparison of 4 theme chart styles for the Fed.
Saves chart_options_fed.html and opens it in the browser.
"""
import json
import re
import sqlite3
import webbrowser
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
from plotly.offline import get_plotlyjs

ROOT        = Path(__file__).parent
DB_PATH     = ROOT / "data/speeches.db"
THEMES_PATH = ROOT / "data/themes.json"
OUT_PATH    = ROOT / "chart_options_fed.html"

COLORS = [
    "#2563EB", "#DC2626", "#059669", "#D97706", "#7C3AED",
    "#DB2777", "#0891B2", "#65A30D", "#EA580C", "#4F46E5",
    "#B45309", "#0F766E", "#9333EA", "#C2410C", "#1D4ED8",
]

# ── Load themes ───────────────────────────────────────────────────────────────
themes_data = json.loads(THEMES_PATH.read_text(encoding="utf-8"))
watchlist   = themes_data.get("watchlist", {})

# ── Load Fed speeches ─────────────────────────────────────────────────────────
conn  = sqlite3.connect(str(DB_PATH))
df    = pd.read_sql_query(
    "SELECT date, body, score FROM speeches WHERE central_bank='Federal Reserve'", conn
)
conn.close()

today  = date.today()
cutoff = date(today.year - 1, today.month, today.day).isoformat()
df_w   = df[
    (df["score"] > 0) & df["body"].notna() &
    (df["body"] != "") & (df["date"] >= cutoff)
].copy()
df_w["month"] = df_w["date"].str[:7]

# ── Build month labels (last 12 months) ──────────────────────────────────────
MON_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
months, month_labels = [], []
for i in range(11, -1, -1):
    m = today.month - i
    y = today.year
    while m <= 0:
        m += 12; y -= 1
    months.append(f"{y}-{m:02d}")
    month_labels.append(f"{MON_NAMES[m-1]} {y}")

# ── Compile keyword patterns ──────────────────────────────────────────────────
theme_patterns = {}
for theme, terms in watchlist.items():
    if terms:
        theme_patterns[theme] = re.compile(
            r'\b(' + '|'.join(re.escape(t.lower()) for t in terms) + r')\b'
        )

df_w["_scores"] = df_w["body"].apply(
    lambda b: {t: len(p.findall((b or "").lower())) for t, p in theme_patterns.items()}
)

# ── Monthly aggregation ───────────────────────────────────────────────────────
theme_monthly = {theme: {} for theme in theme_patterns}
for month in months:
    rows = df_w[df_w["month"] == month]
    n = len(rows)
    for theme in theme_patterns:
        if n < 2:
            theme_monthly[theme][month] = {"intensity": None, "n": n}
        else:
            vals = [r["_scores"][theme] for _, r in rows.iterrows()]
            theme_monthly[theme][month] = {"intensity": sum(vals) / n, "n": n}

show_themes = list(watchlist.keys())


# ── Chart builders ────────────────────────────────────────────────────────────

def make_line_chart():
    fig = go.Figure()
    for i, theme in enumerate(show_themes):
        color   = COLORS[i % len(COLORS)]
        monthly = theme_monthly[theme]
        y_vals  = [monthly[m]["intensity"] for m in months]
        n_vals  = [monthly[m]["n"] for m in months]
        hover   = []
        for ml, yi, n in zip(month_labels, y_vals, n_vals):
            if yi is None:
                note = "<2 speeches" if n > 0 else "no speeches"
                hover.append(f"<b>{theme}</b><br>{ml}<br><i style='color:#9CA3AF'>{note}</i>")
            else:
                hover.append(f"<b>{theme}</b><br>{ml}<br>Avg: {yi:.2f}<br>Speeches: {n}")
        fig.add_trace(go.Scatter(
            x=month_labels, y=y_vals,
            mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=5, color=color),
            name=theme,
            connectgaps=False,
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover,
        ))
    fig.update_layout(
        title="Option 1 — Line chart (current)",
        height=420, margin=dict(l=50, r=20, t=50, b=60),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="system-ui, sans-serif", size=11, color="#6B7280"),
        yaxis=dict(gridcolor="#F0F1F3", title="avg mentions / speech", rangemode="tozero"),
        xaxis=dict(gridcolor="#F0F1F3", tickangle=-30, type="category"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=10)),
    )
    return fig


def make_heatmap():
    z    = [[theme_monthly[t][m]["intensity"] or 0.0 for m in months] for t in show_themes]
    n    = [[theme_monthly[t][m]["n"] for m in months] for t in show_themes]
    text = [[
        f"{show_themes[r]}<br>{month_labels[c]}<br>Avg: {z[r][c]:.2f}<br>Speeches: {n[r][c]}"
        for c in range(len(months))
    ] for r in range(len(show_themes))]
    fig = go.Figure(go.Heatmap(
        z=z, x=month_labels, y=show_themes,
        colorscale=[[0,"#F9FAFB"],[0.05,"#DBEAFE"],[0.4,"#3B82F6"],[1,"#1E3A8A"]],
        hovertemplate="%{customdata}<extra></extra>",
        customdata=text,
        showscale=True,
        colorbar=dict(title="avg mentions<br>/speech", thickness=12, len=0.8),
        xgap=2, ygap=2,
    ))
    fig.update_layout(
        title="Option 2 — Heatmap",
        height=500, margin=dict(l=180, r=80, t=50, b=70),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="system-ui, sans-serif", size=11, color="#374151"),
        xaxis=dict(tickangle=-30, side="bottom", type="category"),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def make_bubble():
    max_v = max(
        (theme_monthly[t][m]["intensity"] or 0)
        for t in show_themes for m in months
    ) or 1
    MAX_PX = 40

    fig = go.Figure()
    for ri, theme in enumerate(show_themes):
        color = COLORS[ri % len(COLORS)]
        x_present, y_present, sizes, hover_present = [], [], [], []
        x_absent,  y_absent  = [], []
        for ml, month in zip(month_labels, months):
            val = theme_monthly[theme][month]["intensity"]
            ns  = theme_monthly[theme][month]["n"]
            if val is not None and val > 0:
                x_present.append(ml)
                y_present.append(theme)
                sizes.append(max(6, MAX_PX * (val / max_v) ** 0.5))
                hover_present.append(f"<b>{theme}</b><br>{ml}<br>Avg: {val:.2f}<br>Speeches: {ns}")
            else:
                x_absent.append(ml)
                y_absent.append(theme)

        if x_present:
            fig.add_trace(go.Scatter(
                x=x_present, y=y_present, mode="markers",
                marker=dict(size=sizes, color=color, opacity=0.7,
                            line=dict(width=1, color="white")),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=hover_present,
                name=theme, legendgroup=theme,
            ))
        if x_absent:
            fig.add_trace(go.Scatter(
                x=x_absent, y=y_absent, mode="markers",
                marker=dict(size=4, color="#E5E7EB"),
                hoverinfo="skip", showlegend=False,
                legendgroup=theme,
            ))

    fig.update_layout(
        title="Option 3 — Bubble / dot grid",
        height=520, margin=dict(l=180, r=20, t=50, b=70),
        paper_bgcolor="white", plot_bgcolor="#FAFAFA",
        font=dict(family="system-ui, sans-serif", size=11, color="#374151"),
        xaxis=dict(tickangle=-30, showgrid=False, type="category"),
        yaxis=dict(showgrid=True, gridcolor="#F0F1F3", autorange="reversed"),
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.01,
                    font=dict(size=10), itemclick="toggle"),
    )
    return fig


def make_small_multiples():
    ncols = 3
    nrows = -(-len(show_themes) // ncols)
    fig = make_subplots(
        rows=nrows, cols=ncols,
        subplot_titles=show_themes,
        shared_xaxes=False,
        vertical_spacing=0.09,
        horizontal_spacing=0.07,
    )
    for i, theme in enumerate(show_themes):
        row = i // ncols + 1
        col = i % ncols + 1
        color  = COLORS[i % len(COLORS)]
        y_vals = [theme_monthly[theme][m]["intensity"] or 0 for m in months]
        n_vals = [theme_monthly[theme][m]["n"] for m in months]
        hover  = [
            f"<b>{theme}</b><br>{ml}<br>Avg: {y:.2f}<br>Speeches: {n}"
            for ml, y, n in zip(month_labels, y_vals, n_vals)
        ]
        fig.add_trace(
            go.Bar(x=month_labels, y=y_vals,
                   marker_color=color, marker_opacity=0.75,
                   hovertemplate="%{customdata}<extra></extra>",
                   customdata=hover, showlegend=False),
            row=row, col=col,
        )
        fig.update_xaxes(tickangle=-45, tickfont=dict(size=8), type="category", row=row, col=col)
        fig.update_yaxes(rangemode="tozero", tickfont=dict(size=8), row=row, col=col)

    fig.update_layout(
        title="Option 4 — Small multiples (bar per theme)",
        height=180 * nrows + 80,
        margin=dict(l=40, r=20, t=60, b=40),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="system-ui, sans-serif", size=10, color="#374151"),
    )
    for ann in fig.layout.annotations:
        ann.font.size = 11
        ann.font.color = "#374151"
    return fig


# ── Render ────────────────────────────────────────────────────────────────────
figs = [make_line_chart(), make_heatmap(), make_bubble(), make_small_multiples()]

# plotly.js inlined once in <head>; each chart rendered as fragment
plotlyjs = get_plotlyjs()

chart_divs = ""
for f in figs:
    div_html = pio.to_html(f, include_plotlyjs=False, full_html=False,
                           config={"displayModeBar": False, "responsive": True})
    chart_divs += f'<div class="chart-block">{div_html}</div>\n'

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Fed Theme Chart Options</title>
<script>{plotlyjs}</script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, -apple-system, sans-serif; background: #F3F4F6;
        color: #111827; padding: 32px 24px; }}
h1 {{ font-size: 1.4rem; font-weight: 600; margin-bottom: 6px; }}
.sub {{ font-size: 0.85rem; color: #6B7280; margin-bottom: 32px; }}
.chart-block {{ background: white; border-radius: 12px; padding: 24px 20px 16px;
                margin-bottom: 32px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
</style>
</head>
<body>
<h1>Fed - Theme Frequency: 4 Chart Options</h1>
<p class="sub">Same data: Macro Watchlist, last 12 months, relevant speeches only</p>
{chart_divs}
</body>
</html>"""

OUT_PATH.write_text(html, encoding="utf-8")
print(f"Written: {OUT_PATH}  ({OUT_PATH.stat().st_size // 1024} KB)")
webbrowser.open(OUT_PATH.as_uri())
print("Opened.")
