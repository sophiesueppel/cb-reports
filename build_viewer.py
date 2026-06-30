import json
from pathlib import Path

JSON_DATA = Path("data/viewer_export_full.json").read_text(encoding="utf-8")
N = json.loads(JSON_DATA)
total = len(N)
rated = sum(1 for r in N if "sc" in r)
years = sorted({r["d"][:4] for r in N if r.get("d")}, reverse=True)
year_options = "\n".join(f"      <option>{y}</option>" for y in years)

HTML_TOP = """<title>Central Bank Speech Database</title>
<meta name="description" content="Browse {total:,} central bank speeches (Fed, ECB, BoE, BoJ) from 1996 to present.">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;background:#F8F9FB;color:#111827;font-size:13px;line-height:1.5;min-height:100vh}
.filterbar{position:sticky;top:0;z-index:100;background:#1C2333;padding:12px 20px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;box-shadow:0 2px 8px rgba(0,0,0,.35)}
.filterbar-title{color:#94A3B8;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;white-space:nowrap;margin-right:4px}
.fb-group{display:flex;align-items:center;gap:6px}
select,input[type=text]{background:#263044;border:1px solid #364154;color:#E2E8F0;border-radius:4px;padding:5px 8px;font-size:12px;height:30px;outline:none;cursor:pointer}
select{padding-right:24px;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394A3B8'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 8px center}
select:focus,input[type=text]:focus{border-color:#60A5FA}
input[type=text]{width:180px}
input[type=text]::placeholder{color:#64748B}
.btn-clear{background:#364154;border:1px solid #475569;color:#CBD5E1;border-radius:4px;padding:5px 12px;font-size:12px;height:30px;cursor:pointer;white-space:nowrap}
.btn-clear:hover{background:#475569}
.statsbar{display:flex;background:#fff;border-bottom:1px solid #E4E8EF;padding:0 20px}
.stat{padding:10px 20px 10px 0;margin-right:20px;border-right:1px solid #E4E8EF;display:flex;flex-direction:column;gap:2px}
.stat:last-child{border-right:none}
.stat-val{font-size:20px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1}
.stat-lbl{font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#9CA3AF}
.sortbar{background:#fff;border-bottom:1px solid #E4E8EF;padding:8px 20px;display:flex;align-items:center;gap:6px}
.sortbar-lbl{font-size:11px;color:#9CA3AF;font-weight:600;letter-spacing:.08em;text-transform:uppercase;margin-right:4px}
.sort-btn{background:none;border:1px solid #E4E8EF;border-radius:4px;padding:4px 10px;font-size:11px;cursor:pointer;color:#6B7280;display:flex;align-items:center;gap:4px}
.sort-btn.active{background:#EFF6FF;border-color:#BFDBFE;color:#1D4ED8;font-weight:600}
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;table-layout:fixed}
col.c-date{width:88px}col.c-bank{width:130px}col.c-speaker{width:170px}col.c-title{width:auto}col.c-score{width:120px}col.c-tone{width:80px}col.c-toggle{width:24px}
thead th{font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#9CA3AF;padding:10px 14px;text-align:left;border-bottom:2px solid #E4E8EF;white-space:nowrap;background:#fff;position:sticky;top:55px;z-index:50}
tbody td{padding:11px 14px;border-bottom:1px solid #F3F4F6;vertical-align:top}
tbody tr.data-row{cursor:pointer;transition:background .1s}
tbody tr.data-row:hover td{background:#F8FAFF}
tbody tr.data-row.expanded td{background:#F0F7FF}
.td-date{font-size:11px;color:#9CA3AF;font-variant-numeric:tabular-nums;white-space:nowrap;padding-top:13px!important}
.td-bank{font-size:11px;color:#6B7280;padding-top:13px!important;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.td-speaker{font-weight:600;font-size:12px;padding-top:12px!important;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.title-link{color:#111827;text-decoration:none;font-size:13px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.title-link:hover{color:#1D4ED8;text-decoration:underline}
.td-toggle{text-align:right;color:#D1D5DB;font-size:11px;padding-top:12px!important}
tr.expanded .td-toggle{color:#6B7280}
.chevron{display:inline-block;transition:transform .2s}
tr.expanded .chevron{transform:rotate(180deg)}
.score-wrap{display:flex;align-items:center;gap:7px;white-space:nowrap;padding-top:2px}
.score-num{font-size:15px;font-family:Georgia,serif;font-variant-numeric:tabular-nums;min-width:14px;text-align:right}
.score-track{width:52px;height:3px;background:#F3F4F6;border-radius:2px;flex-shrink:0}
.score-fill{height:100%;border-radius:2px}
.chip{display:inline-flex;align-items:center;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;border-radius:10px;white-space:nowrap}
.chip-dove{background:#DBEAFE;color:#1D4ED8}
.chip-neutral{background:#F3F4F6;color:#6B7280}
.chip-hawk{background:#FEE2E2;color:#B91C1C}
.chip-unrated{background:#F3F4F6;color:#9CA3AF}
tr.just-row td{padding:0 14px 14px 14px;border-bottom:1px solid #E8EDFF;background:#F0F7FF}
.just-text{font-size:12px;color:#374151;line-height:1.7;max-width:80ch;padding-top:4px}
.just-none{font-size:12px;color:#9CA3AF;font-style:italic;padding-top:4px}
.empty{text-align:center;padding:60px 20px;color:#9CA3AF;font-size:14px}
</style>
"""

HTML_TOP = HTML_TOP.replace("{total:,}", f"{total:,}")

HTML_BODY = f"""
<div class="filterbar">
  <span class="filterbar-title">Filters</span>
  <div class="fb-group">
    <select id="f-bank">
      <option value="">All banks</option>
      <option>Bank of England</option>
      <option>Bank of Japan</option>
      <option>ECB</option>
      <option>Federal Reserve</option>
    </select>
  </div>
  <div class="fb-group"><select id="f-speaker"><option value="">All speakers</option></select></div>
  <div class="fb-group">
    <select id="f-year">
      <option value="">All years</option>
{year_options}
    </select>
  </div>
  <div class="fb-group">
    <select id="f-tone">
      <option value="">All tones</option>
      <option value="dove">Dovish (1-4)</option>
      <option value="neutral">Neutral (5-6)</option>
      <option value="hawk">Hawkish (7-10)</option>
      <option value="unrated">Unrated</option>
    </select>
  </div>
  <div class="fb-group">
    <input type="text" id="f-search" placeholder="Search speaker or title..." autocomplete="off">
  </div>
  <button class="btn-clear" id="btn-clear">Clear filters</button>
</div>

<div class="statsbar">
  <div class="stat"><span class="stat-val" id="st-count">-</span><span class="stat-lbl">Speeches</span></div>
  <div class="stat"><span class="stat-val" id="st-rated">-</span><span class="stat-lbl">Rated</span></div>
  <div class="stat"><span class="stat-val" id="st-avg">-</span><span class="stat-lbl">Avg score</span></div>
  <div class="stat"><span class="stat-val" id="st-hawk" style="color:#DC2626">-</span><span class="stat-lbl">% Hawkish</span></div>
  <div class="stat"><span class="stat-val" id="st-dove" style="color:#2563EB">-</span><span class="stat-lbl">% Dovish</span></div>
</div>

<div class="sortbar">
  <span class="sortbar-lbl">Sort</span>
  <button class="sort-btn active" data-sort="date">Date <span id="arr-date">v</span></button>
  <button class="sort-btn" data-sort="score">Score <span id="arr-score">v</span></button>
  <button class="sort-btn" data-sort="speaker">Speaker <span id="arr-speaker">^</span></button>
</div>

<div class="tbl-wrap">
<table>
  <colgroup>
    <col class="c-date"><col class="c-bank"><col class="c-speaker">
    <col class="c-title"><col class="c-score"><col class="c-tone"><col class="c-toggle">
  </colgroup>
  <thead><tr><th>Date</th><th>Bank</th><th>Speaker</th><th>Title</th><th>Score</th><th>Tone</th><th></th></tr></thead>
  <tbody id="tbody"></tbody>
</table>
<div class="empty" id="empty" style="display:none">No speeches match the current filters.</div>
</div>

<script>
const ALL_DATA={{JSON_DATA_PLACEHOLDER}};

function esc(s){{return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}}
function lerp(a,b,t){{return Math.round(a+(b-a)*t)}}
function scoreColor(sc){{
  if(sc==null)return"#9CA3AF";
  const t=(sc-1)/9;
  if(t<0.5){{const u=t*2;return`rgb(${{lerp(37,107,u)}},${{lerp(99,114,u)}},${{lerp(235,128,u)}})`}}
  const u=(t-0.5)*2;return`rgb(${{lerp(107,220,u)}},${{lerp(114,38,u)}},${{lerp(128,38,u)}})`;
}}
function tone(sc){{return sc==null?"unrated":sc<=4?"dove":sc<=6?"neutral":"hawk"}}
function toneLabel(sc){{return sc==null?"Unrated":sc<=4?"Dovish":sc<=6?"Neutral":"Hawkish"}}
function fmt(iso){{
  if(!iso)return"";
  const[y,m,d]=iso.split("-");
  const mon=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+m-1];
  return mon+" "+d.replace(/^0/,"")+", "+y;
}}

const speakersByBank={{}};
ALL_DATA.forEach(r=>{{
  if(!speakersByBank[r.c])speakersByBank[r.c]=new Set();
  speakersByBank[r.c].add(r.s);
}});
const allSpeakers=[...new Set(ALL_DATA.map(r=>r.s))].sort();

function updateSpeakerDropdown(bank){{
  const sel=document.getElementById("f-speaker");
  const cur=sel.value;
  const pool=bank?[...(speakersByBank[bank]||[])].sort():allSpeakers;
  sel.innerHTML="<option value=''>All speakers</option>"+pool.map(n=>"<option"+(n===cur?" selected":"")+">"+esc(n)+"</option>").join("");
}}
updateSpeakerDropdown("");

document.getElementById("f-bank").addEventListener("change",function(){{updateSpeakerDropdown(this.value);render();}});

let sortKey="date",sortDir={{date:-1,score:-1,speaker:1}};

function getFiltered(){{
  const bank=document.getElementById("f-bank").value;
  const speaker=document.getElementById("f-speaker").value;
  const year=document.getElementById("f-year").value;
  const tv=document.getElementById("f-tone").value;
  const q=document.getElementById("f-search").value.toLowerCase().trim();
  return ALL_DATA.filter(r=>{{
    if(bank&&r.c!==bank)return false;
    if(speaker&&r.s!==speaker)return false;
    if(year&&!r.d.startsWith(year))return false;
    const sc=(r.sc!=null)?r.sc:null;
    if(tv&&tone(sc)!==tv)return false;
    if(q&&!r.s.toLowerCase().includes(q)&&!r.t.toLowerCase().includes(q))return false;
    return true;
  }});
}}

function getSorted(arr){{
  return[...arr].sort((a,b)=>{{
    let av,bv;
    if(sortKey==="date"){{av=a.d;bv=b.d;}}
    else if(sortKey==="score"){{av=a.sc??-999;bv=b.sc??-999;}}
    else{{av=a.s;bv=b.s;}}
    if(av<bv)return-sortDir[sortKey];
    if(av>bv)return sortDir[sortKey];
    return 0;
  }});
}}

function updateStats(arr){{
  const n=arr.length;
  document.getElementById("st-count").textContent=n.toLocaleString();
  const rArr=arr.filter(r=>r.sc!=null);
  const nr=rArr.length;
  document.getElementById("st-rated").textContent=nr.toLocaleString();
  if(!nr){{["st-avg","st-hawk","st-dove"].forEach(id=>document.getElementById(id).textContent="-");return;}}
  const avg=rArr.reduce((s,r)=>s+r.sc,0)/nr;
  document.getElementById("st-avg").textContent=avg.toFixed(1);
  document.getElementById("st-hawk").textContent=Math.round(rArr.filter(r=>r.sc>=7).length/nr*100)+"%";
  document.getElementById("st-dove").textContent=Math.round(rArr.filter(r=>r.sc<=4).length/nr*100)+"%";
}}

function rowKey(r){{return r.u||(r.d+"||"+r.s+"||"+(r.t||"").slice(0,30))}}

function render(){{
  const data=getSorted(getFiltered());
  updateStats(data);
  const tbody=document.getElementById("tbody");
  document.getElementById("empty").style.display=data.length?"none":"block";
  const bm={{"Federal Reserve":"Fed","Bank of England":"BoE","Bank of Japan":"BoJ","ECB":"ECB"}};
  tbody.innerHTML=data.map(r=>{{
    const sc=(r.sc!=null)?r.sc:null;
    const col=scoreColor(sc);
    const t=tone(sc);
    const key=esc(rowKey(r));
    const bs=bm[r.c]||r.c;
    const scoreHtml=sc!=null
      ?"<div class='score-wrap'><span class='score-num' style='color:"+col+"'>"+sc+"</span><div class='score-track'><div class='score-fill' style='width:"+((sc-1)/9*100).toFixed(1)+"%;background:"+col+"'></div></div></div>"
      :"<div class='score-wrap'><span class='score-num' style='color:#9CA3AF'>-</span></div>";
    return"<tr class='data-row' data-key='"+key+"'>"
      +"<td class='td-date'>"+fmt(r.d)+"</td>"
      +"<td class='td-bank'>"+esc(bs)+"</td>"
      +"<td class='td-speaker' title='"+esc(r.s)+"'>"+esc(r.s)+"</td>"
      +"<td><a class='title-link' href='"+esc(r.u||"#")+"' target='_blank' rel='noopener' onclick='event.stopPropagation()'>"+esc(r.t)+"</a></td>"
      +"<td>"+scoreHtml+"</td>"
      +"<td><span class='chip chip-"+t+"'>"+toneLabel(sc)+"</span></td>"
      +"<td class='td-toggle'><span class='chevron'>&#8964;</span></td>"
      +"</tr>";
  }}).join("");
}}

document.getElementById("tbody").addEventListener("click",function(e){{
  if(e.target.tagName==="A")return;
  const row=e.target.closest("tr.data-row");
  if(!row)return;
  const next=row.nextElementSibling;
  if(next&&next.classList.contains("just-row")){{next.remove();row.classList.remove("expanded");}}
  else{{
    const key=row.dataset.key;
    const r=ALL_DATA.find(x=>esc(rowKey(x))===key);
    if(!r)return;
    const jrow=document.createElement("tr");
    jrow.className="just-row";
    jrow.innerHTML="<td colspan='7'>"+(r.j?"<div class='just-text'>"+esc(r.j)+"</div>":"<div class='just-none'>No analysis available - this speech has not been rated yet.</div>")+"</td>";
    row.after(jrow);row.classList.add("expanded");
  }}
}});

document.querySelectorAll(".sort-btn").forEach(btn=>{{
  btn.addEventListener("click",function(){{
    const k=this.dataset.sort;
    if(k===sortKey)sortDir[k]*=-1;else sortKey=k;
    document.querySelectorAll(".sort-btn").forEach(b=>b.classList.remove("active"));
    this.classList.add("active");
    ["date","score","speaker"].forEach(key=>{{
      const el=document.getElementById("arr-"+key);
      if(el)el.textContent=sortDir[key]===-1?"v":"^";
    }});
    render();
  }});
}});

["f-speaker","f-year","f-tone"].forEach(id=>document.getElementById(id).addEventListener("change",render));
document.getElementById("f-search").addEventListener("input",render);
document.getElementById("btn-clear").addEventListener("click",function(){{
  ["f-bank","f-year","f-tone"].forEach(id=>document.getElementById(id).value="");
  document.getElementById("f-search").value="";
  updateSpeakerDropdown("");render();
}});
render();
</script>
"""

html = HTML_TOP + HTML_BODY.replace("{JSON_DATA_PLACEHOLDER}", JSON_DATA)
from pathlib import Path
Path("speech_viewer.html").write_text(html, encoding="utf-8")
print(f"Written speech_viewer.html: {len(html)/1024:.0f} KB")
print(f"Total: {total} speeches ({rated} rated)")
