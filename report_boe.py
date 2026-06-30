import json
import sqlite3
from datetime import date

import pandas as pd
from pathlib import Path

from report_frb import (
    score_color, tone, wrap_text,
    make_timeline, make_speaker_chart, make_trend_chart,
)
from scraper_boe import was_mpc_member

DB_PATH = Path("data/speeches.db")
OUTPUT_PATH = Path("report_boe.html")

BOE_REPORT_URL = "https://claude.ai/code/artifact/2506b5d7-5242-4f8b-9cbd-b6e5487c4ddc"


PAGE_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BoE Policy Sentiment Tracker</title>
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
.eyebrow{{font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:#C8102E;margin-bottom:5px}}
h1{{font-family:Georgia,serif;font-size:23px;font-weight:normal;color:#111827;line-height:1.2}}
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

.row-bar{{display:flex;align-items:center;gap:9px;white-space:nowrap;padding-top:1px}}
.row-num{{font-family:Georgia,serif;font-size:15px;min-width:14px;text-align:right;font-variant-numeric:tabular-nums}}
.row-track{{width:48px;height:3px;background:#F3F4F6;border-radius:2px;flex-shrink:0}}
.row-fill{{height:100%;border-radius:2px}}
.row-tone{{font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;min-width:44px}}

.td-toggle{{text-align:right;color:#D1D5DB;font-size:11px;padding-top:14px !important}}
tr.expanded .td-toggle{{color:#6B7280}}
.chevron{{display:inline-block;transition:transform .22s ease}}
tr.expanded .chevron{{transform:rotate(180deg)}}
.speaker-select{{font-size:11px;color:#6B7280;background:#fff;border:1px solid #E4E8EF;border-radius:4px;padding:3px 8px;cursor:pointer;font-family:inherit}}
.speaker-select:hover{{background:#F3F4F6;color:#111827}}

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
</style>
</head>
<body>
<div class="page">

<header>
  <div>
    <div class="eyebrow">Bank of England</div>
    <h1>Policy Sentiment Tracker</h1>
  </div>
  <div class="header-meta" id="hm"></div>
</header>

<div id="latest-wrap"></div>

<section class="chart-section">
  <div class="section-header">
    <span class="section-title">Score History &middot; Last 5 Years</span>
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
    <span class="section-title">Score Trend by Speaker &middot; Last 5 Years</span>
    <div class="section-rule"></div>
  </div>
  <div class="trend-container">
    <div class="chart-wrap">{trend_chart}</div>
    <div class="trend-legend" id="trend-legend"></div>
  </div>
</section>

<section class="chart-section">
  <div class="section-header">
    <span class="section-title">Speaker Analysis &middot; Active Members</span>
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
    <span class="section-title">MPC Speeches &middot; Last 5 Years &middot; Click row to expand</span>
    <div class="section-rule"></div>
    <select id="speaker-filter" class="speaker-select"><option value="">All speakers</option></select>
  </div>
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
function fmtShort(iso){{return new Date(iso+'T00:00:00').toLocaleDateString('en-US',{{month:'short',day:'numeric',year:'numeric'}})}}

const n=DATA.length;
const ts=new Date().toLocaleDateString('en-US',{{month:'long',day:'numeric',year:'numeric'}});
document.getElementById('hm').innerHTML=`Updated ${{ts}}<br>${{n}} speech${{n!==1?'es':''}} · last 5 years`;

const latest=[...DATA].filter(d=>d.score>0).sort((a,b)=>b.date.localeCompare(a.date))[0];
if(latest){{
  const col=scoreColor(latest.score);
  document.getElementById('latest-wrap').innerHTML=`
  <div class="latest-card">
    <div class="card-label">Most Recent MPC Speech</div>
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

const byDate=[...DATA].sort((a,b)=>b.date.localeCompare(a.date));
document.getElementById('tbody').innerHTML=byDate.map(d=>{{
  const col=scoreColor(d.score),pct=d.score>0?(d.score-1)/9*100:0;
  return`<tr>
    <td class="td-date">${{fmtShort(d.date)}}</td>
    <td class="td-speaker" title="${{d.speaker}}">${{d.speaker}}</td>
    <td>
      <div class="title-text"><a href="${{d.url}}" target="_blank" onclick="event.stopPropagation()">${{d.title}}</a></div>
      <div class="td-justification">${{d.justification||''}}</div>
    </td>
    <td>
      <div class="row-bar">
        <span class="row-num" style="color:${{col}}">${{d.score}}</span>
        <div class="row-track"><div class="row-fill" style="width:${{pct}}%;background:${{col}}"></div></div>
        <span class="row-tone" style="color:${{col}}">${{tone(d.score)}}</span>
      </div>
    </td>
    <td class="td-toggle"><span class="chevron">&#8964;</span></td>
  </tr>`;
}}).join('');

document.getElementById('tbody').addEventListener('click',function(e){{
  if(e.target.tagName==='A')return;
  const r=e.target.closest('tr');
  if(r)r.classList.toggle('expanded');
}});
(function(){{
  const sel=document.getElementById('speaker-filter');
  if(!sel)return;
  const speakers=[...new Set(DATA.map(d=>d.speaker))].sort();
  sel.innerHTML='<option value="">All speakers</option>'+speakers.map(s=>`<option value="${{s}}">${{s}}</option>`).join('');
  sel.addEventListener('change',function(){{
    const v=sel.value;
    document.querySelectorAll('#tbody tr').forEach(r=>{{
      const spk=r.querySelector('.td-speaker')?.title||'';
      r.style.display=v&&spk!==v?'none':'';
    }});
  }});
}})();

(function(){{
  const PAL=["#2563EB","#DC2626","#16A34A","#F97316","#9333EA","#0891B2","#EC4899","#D97706","#475569","#6366F1","#65A30D","#BE185D","#0F766E","#A16207","#7C3AED"];
  const spk={{}};
  DATA.filter(d=>d.score>0).forEach(d=>{{if(!spk[d.speaker])spk[d.speaker]={{d:[],s:[]}};spk[d.speaker].d.push(d.date);spk[d.speaker].s.push(d.score);}});
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
  const spk={{}};
  DATA.filter(d=>d.score>0).forEach(d=>{{
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


def generate_boe_report() -> None:
    if not DB_PATH.exists():
        return
    today = date.today()
    cutoff = date(today.year - 5, today.month, today.day).isoformat()
    conn = sqlite3.connect(str(DB_PATH))
    df = pd.read_sql(
        "SELECT * FROM speeches "
        "WHERE central_bank='Bank of England' AND score IS NOT NULL AND date >= ? "
        "ORDER BY date DESC",
        conn,
        params=(cutoff,),
    )
    conn.close()

    # Keep only speeches where the speaker was actually an MPC member on that date
    df = df[df.apply(lambda r: was_mpc_member(r["speaker"], r["date"]), axis=1)].copy()

    if df.empty:
        print("No rated BoE MPC speeches in the last 5 years — skipping BoE report generation.")
        return

    # Normalize speaker names so title/name variants don't split one person into two
    from speaker_norm import normalize_speaker
    df["speaker"] = df.apply(lambda r: normalize_speaker(r["speaker"], r["central_bank"]), axis=1)

    from meetings import BOE_MEETINGS
    timeline_html = make_timeline(df, meetings=BOE_MEETINGS)
    trend_html = make_trend_chart(df)

    from scraper_boe import MPC_MEMBERS
    active_members_json = json.dumps(sorted(MPC_MEMBERS))

    html = PAGE_TEMPLATE.format(
        timeline=timeline_html,
        trend_chart=trend_html,
        data=json.dumps(df.to_dict("records"), default=str),
        active_members_json=active_members_json,
    )
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"BoE report written to {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    generate_boe_report()
