"""
Compare heatmap scaling approaches for theme frequency charts.
Saves chart_scale_test.html and opens in browser.
"""
import json
import math
import re
import sqlite3
import webbrowser
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

ROOT        = Path(__file__).parent
DB_PATH     = ROOT / "data/speeches.db"
THEMES_PATH = ROOT / "data/themes.json"
OUT_PATH    = ROOT / "chart_scale_test.html"

MON_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
SPARSE   = -1.0   # sentinel z-value for months with <2 speeches

# ── Load data ─────────────────────────────────────────────────────────────────
themes_data = json.loads(THEMES_PATH.read_text(encoding="utf-8"))
watchlist   = themes_data.get("watchlist", {})

conn = sqlite3.connect(str(DB_PATH))
df   = pd.read_sql_query(
    "SELECT date, body, score FROM speeches WHERE central_bank='Federal Reserve'", conn
)
conn.close()

today  = date.today()
cutoff = date(today.year - 1, today.month, today.day).isoformat()
df_w   = df[(df["score"] > 0) & df["body"].notna() & (df["body"] != "") & (df["date"] >= cutoff)].copy()
df_w["month"] = df_w["date"].str[:7]

months, month_labels = [], []
for i in range(11, -1, -1):
    m = today.month - i
    y = today.year
    while m <= 0:
        m += 12; y -= 1
    months.append(f"{y}-{m:02d}")
    month_labels.append(f"{MON_ABBR[m-1]} {y}")

theme_patterns = {
    theme: re.compile(r'\b(' + '|'.join(re.escape(t.lower()) for t in terms) + r')\b')
    for theme, terms in watchlist.items() if terms
}
df_w["_scores"] = df_w["body"].apply(
    lambda b: {t: len(p.findall((b or "").lower())) for t, p in theme_patterns.items()}
)

theme_monthly = {}
for theme in theme_patterns:
    theme_monthly[theme] = {}
    for month in months:
        rows = df_w[df_w["month"] == month]
        n = len(rows)
        if n < 2:
            theme_monthly[theme][month] = {"intensity": None, "n": n}
        else:
            vals = [r["_scores"][theme] for _, r in rows.iterrows()]
            theme_monthly[theme][month] = {"intensity": sum(vals) / n, "n": n}

show_themes = list(watchlist.keys())

# Sort themes by total intensity (most active at top) — shared across all charts
totals = {t: sum(theme_monthly[t][m]["intensity"] or 0 for m in months) for t in show_themes}
themes_ordered = sorted(show_themes, key=lambda t: totals[t], reverse=True)


# ── Shared heatmap builder ────────────────────────────────────────────────────
def _blue_colorscale(zmin, zmax):
    """Blue colorscale anchored to [zmin, zmax], grey below zero."""
    span = zmax - zmin
    def n(v): return round((v - zmin) / span, 6)
    return [
        [0.0,           "#D1D5DB"],
        [n(0) - 1e-4,  "#D1D5DB"],
        [n(0),          "#F1F5F9"],
        [n(zmax * 0.1), "#DBEAFE"],
        [n(zmax * 0.35),"#60A5FA"],
        [n(zmax * 0.7), "#2563EB"],
        [1.0,           "#1E3A8A"],
    ]


def make_heatmap(title, z_matrix, customdata, zmin, zmax, colorbar_ticks):
    n_themes = len(themes_ordered)
    fig = go.Figure(go.Heatmap(
        z=z_matrix,
        x=month_labels,
        y=themes_ordered,
        zmin=zmin,
        zmax=zmax,
        colorscale=_blue_colorscale(zmin, zmax),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=customdata,
        showscale=True,
        colorbar=dict(
            title=dict(text="avg mentions/<br>speech", font=dict(size=10)),
            thickness=10, len=0.7,
            tickvals=colorbar_ticks["vals"],
            ticktext=colorbar_ticks["text"],
            outlinewidth=0,
        ),
        xgap=2, ygap=2,
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#111827")),
        height=max(320, n_themes * 34 + 120),
        margin=dict(l=160, r=110, t=50, b=60),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="system-ui, sans-serif", size=11, color="#374151"),
        xaxis=dict(side="bottom", tickangle=-30, type="category", tickfont=dict(size=10)),
        yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
        hoverlabel=dict(bgcolor="white", bordercolor="#E4E8EF",
                        font=dict(size=12, color="#111827"), align="left"),
    )
    return fig


# ── Option A: Global p90 cap (current) ───────────────────────────────────────
def p90(vals):
    s = sorted(vals)
    return float(s[max(0, int(len(s) * 0.9) - 1)]) if s else 1.0

all_raw = [theme_monthly[t][m]["intensity"] for t in themes_ordered for m in months
           if theme_monthly[t][m]["intensity"] is not None]
zmax_a  = p90(all_raw) or 1.0

z_a, cd_a = [], []
for theme in themes_ordered:
    z_row, cd_row = [], []
    for month, ml in zip(months, month_labels):
        d = theme_monthly[theme][month]
        v, n = d["intensity"], d["n"]
        if v is None:
            z_row.append(SPARSE)
            cd_row.append(f"<b>{theme}</b><br>{ml}<br><i style='color:#9CA3AF'>{'&lt;2 speeches' if n else 'no speeches'}</i>")
        else:
            z_row.append(min(v, zmax_a))
            cd_row.append(f"<b>{theme}</b><br>{ml}<br>Avg: {v:.2f}<br>Speeches: {n}")
    z_a.append(z_row); cd_a.append(cd_row)

ticks_a = {
    "vals": [0, zmax_a * 0.5, zmax_a],
    "text": ["0", f"{zmax_a*0.5:.1f}", f"≥{zmax_a:.1f}"],
}
fig_a = make_heatmap("Option A — Global p90 cap (current)", z_a, cd_a, SPARSE, zmax_a, ticks_a)


# ── Option B: Sqrt transform on global scale ──────────────────────────────────
# Apply sqrt to raw intensities before passing to colorscale.
# Cross-theme comparability preserved; dynamic range compressed.
all_sqrt = [math.sqrt(v) for v in all_raw]
zmax_b   = max(all_sqrt) or 1.0   # use actual max after transform (no cap needed — sqrt handles it)

z_b, cd_b = [], []
for theme in themes_ordered:
    z_row, cd_row = [], []
    for month, ml in zip(months, month_labels):
        d = theme_monthly[theme][month]
        v, n = d["intensity"], d["n"]
        if v is None:
            z_row.append(SPARSE)
            cd_row.append(f"<b>{theme}</b><br>{ml}<br><i style='color:#9CA3AF'>{'&lt;2 speeches' if n else 'no speeches'}</i>")
        else:
            # Hover shows the REAL value; colour uses sqrt-transformed value
            z_row.append(math.sqrt(v))
            cd_row.append(f"<b>{theme}</b><br>{ml}<br>Avg: {v:.2f}<br>Speeches: {n}")
    z_b.append(z_row); cd_b.append(cd_row)

# Colorbar ticks: show real values (back-transformed from sqrt)
tick_sqrt_vals = [zmax_b * f for f in [0, 0.25, 0.5, 0.75, 1.0]]
tick_real_vals = [round(v ** 2, 1) for v in tick_sqrt_vals]
ticks_b = {
    "vals": tick_sqrt_vals,
    "text": [str(v) for v in tick_real_vals],
}
fig_b = make_heatmap("Option B — Square-root transform (global scale)", z_b, cd_b, SPARSE, zmax_b, ticks_b)


# ── Option C: Per-row p90 (each theme self-normalised) ───────────────────────
z_c, cd_c = [], []
for theme in themes_ordered:
    row_vals = [theme_monthly[theme][m]["intensity"] for m in months
                if theme_monthly[theme][m]["intensity"] is not None]
    zmax_row = p90(row_vals) or 1.0
    z_row, cd_row = [], []
    for month, ml in zip(months, month_labels):
        d = theme_monthly[theme][month]
        v, n = d["intensity"], d["n"]
        if v is None:
            z_row.append(SPARSE)
            cd_row.append(f"<b>{theme}</b><br>{ml}<br><i style='color:#9CA3AF'>{'&lt;2 speeches' if n else 'no speeches'}</i>")
        else:
            # Normalise to [0, 1] using this theme's own p90
            z_row.append(min(v / zmax_row, 1.0))
            cd_row.append(f"<b>{theme}</b><br>{ml}<br>Avg: {v:.2f}<br>Speeches: {n}")
    z_c.append(z_row); cd_c.append(cd_row)

# For per-row: z is now 0–1 for all themes; colorscale runs from SPARSE to 1.0
ticks_c = {"vals": [0, 0.5, 1.0], "text": ["0%", "50%", "100%\nof p90"]}
fig_c = make_heatmap(
    "Option C — Per-row p90 (each theme self-normalised, colour not cross-comparable)",
    z_c, cd_c, SPARSE, 1.0, ticks_c
)


# ── Render ────────────────────────────────────────────────────────────────────
plotlyjs = get_plotlyjs()

def to_div(fig):
    return pio.to_html(fig, include_plotlyjs=False, full_html=False,
                       config={"displayModeBar": False, "responsive": True})

notes = {
    "Option A": "Each colour maps to an absolute mentions/speech value. One dominant topic (e.g. Tariffs) pulls the cap up, compressing colour variation for quieter topics.",
    "Option B": "Same absolute scale — same colour still means same level of discussion — but the square-root transform compresses the top end so quieter topics show variation. Hover shows real values.",
    "Option C": "Each row uses its own scale. Taiwan's darkest blue = Taiwan's personal peak; Tariffs' darkest blue = Tariffs' personal peak. Best for spotting relative spikes, but colour is NOT cross-comparable.",
}

charts_html = ""
for fig, (opt, note) in zip([fig_a, fig_b, fig_c], notes.items()):
    charts_html += f"""
<div class="chart-block">
  <p class="note"><b>{opt}:</b> {note}</p>
  {to_div(fig)}
</div>
"""

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Heatmap Scale Comparison</title>
<script>{plotlyjs}</script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, sans-serif; background: #F3F4F6; color: #111827; padding: 32px 24px; }}
h1 {{ font-size: 1.3rem; font-weight: 600; margin-bottom: 4px; }}
.sub {{ font-size: 0.85rem; color: #6B7280; margin-bottom: 28px; }}
.chart-block {{ background: white; border-radius: 12px; padding: 20px 20px 12px;
                margin-bottom: 28px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
.note {{ font-size: 0.82rem; color: #4B5563; margin-bottom: 12px;
         background: #F9FAFB; border-left: 3px solid #D1D5DB;
         padding: 8px 12px; border-radius: 4px; }}
</style>
</head>
<body>
<h1>Heatmap Scale Options — Fed Macro Watchlist</h1>
<p class="sub">Last 12 months · Relevant speeches only · Hover for real values</p>
{charts_html}
</body>
</html>"""

OUT_PATH.write_text(html, encoding="utf-8")
print(f"Written: {OUT_PATH}")
webbrowser.open(OUT_PATH.as_uri())
