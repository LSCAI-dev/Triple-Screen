"""Builds the GitHub Pages site into docs/."""
from pathlib import Path
from jinja2 import Environment, DictLoader

import config as C
from .assets import CSS, THEME_JS
from .charts import daily_chart, weekly_chart, to_div
from .screens import SETUP_LONG, SETUP_SHORT, WATCH_LONG, WATCH_SHORT

LABELS = {"bid_ask": "Successful bid/ask", "price_volume": "Price-volume", "block_trades": "Block trades",
          "vwap": "VWAP", "obv": "OBV", "closing_strength": "Closing strength",
          "trend_alignment": "Trend alignment", "pullback_quality": "Pullback quality",
          "entry_confirmation": "Entry confirmation", "liquidity": "Turnover", "reward_risk": "R:R",
          "atr_band": "ATR band", "stop_width": "Stop width", "no_event_5d": "No event 5d", "weekly_impulse": "Weekly Impulse", "six_pct_rule": "6% rule", "bid/ask below floor": "bid/ask under half marks"}
PLOTLY = "https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.2/plotly.min.js"
CLS = {SETUP_LONG: "st-long", SETUP_SHORT: "st-short", WATCH_LONG: "st-lwatch", WATCH_SHORT: "st-swatch"}

BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{{ title }}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📈</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{{ root }}assets/style.css">
{% if plotly %}<script src="{{ plotly }}"></script>
<script>window.Plotly||document.write('<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"><\\/script>')</script>
<script>window.Plotly||document.write('<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"><\\/script>')</script>{% endif %}
</head><body><div class="wrap">
<header class="top"><h1>{{ site }}</h1>
<nav><a href="{{ root }}index.html" {% if page=='home' %}aria-current="page"{% endif %}>Today</a><a href="{{ root }}archive.html" {% if page=='archive' %}aria-current="page"{% endif %}>Saved runs</a><a href="https://github.com/LSCAI-dev/Triple-Screen/actions/workflows/triple-screen.yml" target="_blank" rel="noopener" title="Opens GitHub: tap Run workflow, wait 2-3 min, then refresh Today">Update now&nbsp;&#8599;</a><a href="{{ root }}method.html" {% if page=='method' %}aria-current="page"{% endif %}>Methodology</a></nav></header>
{% block body %}{% endblock %}
<footer>Source: {{ meta.source }}. Daily bars to {{ meta.as_of }}; generated {{ meta.generated }} SGT.
Prices are end-of-day and may differ from your broker. Verify every level on your broker terminal before placing an order. Not investment advice.</footer>
</div><script src="{{ root }}assets/theme.js"></script></body></html>"""

INDEX = """{% extends "base" %}{% block body %}
<p class="stamp">Bars to {{ meta.as_of }} &nbsp;|&nbsp; generated {{ meta.generated }} SGT &nbsp;|&nbsp; {{ meta.source }}{% if meta.demo %} &nbsp;|&nbsp; <b>DEMO DATA - not real prices</b>{% endif %}</p>
<div class="tide"><span>STI weekly tide</span><b class="{{ sti.tide }}">{{ sti.tide }}</b>
<span class="counts"><span><strong>{{ counts.ls }}</strong>long setups</span><span><strong>{{ counts.ss }}</strong>short setups</span>
<span><strong>{{ counts.w }}</strong>on watch</span><span><strong>{{ counts.n }}</strong>no trade</span></span></div>
{% if sti.tide == 'Down' %}<p class="warn">The index tide is falling. Elder's rule: longs against a falling market tide need extra confirmation; consider half size.</p>{% endif %}

<h2>Dual score: disciplined buys</h2>
<p class="note">BUY needs Triple Screen &ge; {{ thr.ts }} and Smart Money &ge; {{ thr.sm }} (both +10 when the STI is below a falling 50-day EMA{% if dual_bear %}, <b>as it is now</b>{% endif %}), bid/ask &ge; half marks, and every gate: turnover &ge; S$1M, R:R &ge; 2, ATR 0.8&ndash;6%, stop &le; 2.5 ATR, weekly Impulse not red (spec v1.2). Hourly bars for the bid/ask estimate: {{ meta.hourly_ok }} of {{ results|length }} stocks.</p>
{% if dual_rows %}<table class="t stack"><thead><tr><th class="l">Stock</th><th class="l">Decision</th><th>Smart Money</th><th>Triple Screen</th><th>Entry</th><th>Stop</th><th>T1</th><th>R:R</th><th>Qty</th><th class="l">Blocked by</th></tr></thead><tbody>
{% for r in dual_rows %}{% set dl = r.dual %}{% set p = dl.plan %}<tr>
<td><a href="stocks/{{ r.code }}.html"><b>{{ r.code }}</b></a> {{ r.name }}</td>
<td class="l" data-h="Decision"><b class="dec-{{ dl.decision }}">{{ dl.decision }}</b></td>
<td data-h="Smart Money">{{ dl.sm.score }}</td><td data-h="Triple Screen">{{ dl.ts.score }}</td>
<td data-h="Entry"><b>{{ '%.3f'|format(p.entry_buy_stop) }}</b></td><td data-h="Stop">{{ '%.3f'|format(p.stop) }}</td>
<td data-h="T1">{{ '%.3f'|format(p.target1) }}</td><td data-h="R:R">{{ p.rr_t1 }}</td><td data-h="Qty">{{ '{:,}'.format(p.shares or 0) }}</td>
<td class="l" data-h="Blocked by">{% for b in dl.blocked_by %}{{ labels.get(b, b)|e }}{{ ', ' if not loop.last }}{% else %}-{% endfor %}</td></tr>{% endfor %}
</tbody></table>
<p class="note">Shows every BUY and WATCH, then the stocks closest to qualifying. Full score breakdown on each stock page.</p>
{% else %}<div class="empty">Dual scores not available in this run.</div>{% endif %}

<h2>Setups for the next session</h2>
{% if setups %}
<table class="t stack"><thead><tr><th class="l">Stock</th><th>Grade</th><th>Close</th><th>Entry</th><th>Stop</th><th>T1</th><th>T2</th><th>R:R T1</th><th>Stop %</th><th>Qty</th></tr></thead><tbody>
{% for r in setups %}{% set p = r.plan %}<tr>
<td><a href="stocks/{{ r.code }}.html"><b>{{ r.code }}</b></a> {{ r.name }} <span class="{{ 'up' if p.side=='Long' else 'dn' }}">{{ p.side }}</span></td>
<td data-h="Grade"><span class="g g{{ p.grade }}">{{ p.grade }}</span></td>
<td data-h="Close">{{ '%.3f'|format(r.close) }}</td><td data-h="Entry"><b>{{ '%.3f'|format(p.entry) }}</b></td>
<td data-h="Stop">{{ '%.3f'|format(p.stop) }}</td><td data-h="T1">{{ '%.3f'|format(p.t1) }}</td><td data-h="T2">{{ '%.3f'|format(p.t2) }}</td>
<td data-h="R:R T1">{{ p.rr1 }}</td><td data-h="Stop %">{{ p.stop_pct }}%</td><td data-h="Qty">{{ '{:,}'.format(p.qty) }}</td></tr>{% endfor %}
</tbody></table>
<p class="note">Qty sizes each trade to risk {{ risk_pct }}% of S${{ '{:,}'.format(acct) }}, in board lots of {{ lot }}. Orders are stop orders for the next session; if unfilled, trail them to one tick beyond each new day's high (long) or low (short) for up to {{ valid }} sessions.</p>
{% else %}<div class="empty">No stock passes all three screens today. Check the watch list below; setups usually appear after a 2 to 4 day pullback in an up-tide.</div>{% endif %}

<h2>All {{ results|length }} STI stocks</h2>
<div class="board">{% for r in results %}<a class="tile {{ cls.get(r.status,'') }}" href="stocks/{{ r.code }}.html">
<div class="c">{{ r.code }}</div><div class="n">{{ r.name }}</div>
<div class="p">{{ '%.3f'|format(r.close) }} <span class="{{ 'up' if r.chg_pct>=0 else 'dn' }}">{{ '%+.1f'|format(r.chg_pct) }}%</span></div>
<div class="s">{{ r.status }}</div>{% if r.dual and r.dual.sm %}<div class="ds">SM {{ r.dual.sm.score|round|int }} · TS {{ r.dual.ts.score|round|int }} <b class="dec-{{ r.dual.decision }}">{{ r.dual.decision }}</b></div>{% endif %}</a>{% endfor %}</div>

<h2>Screen readings</h2>
<table class="t stack"><thead><tr><th class="l">Stock</th><th class="l">Weekly tide</th><th class="l">Daily wave</th><th>RSI</th><th>Force(2)</th><th>MACD-H</th><th>EMA20</th><th>EMA50</th><th>Support</th><th>Resistance</th></tr></thead><tbody>
{% for r in results %}<tr><td><a href="stocks/{{ r.code }}.html"><b>{{ r.code }}</b></a></td>
<td class="l" data-h="Tide">{{ r.tide.tide }}</td><td class="l" data-h="Wave">{{ r.wave }}</td><td data-h="RSI">{{ r.rsi }}</td>
<td data-h="Force(2)" class="{{ 'up' if r.fi2>=0 else 'dn' }}">{{ '{:,.0f}'.format(r.fi2/1000) }}k</td>
<td data-h="MACD-H">{{ '▲' if r.macd_hist_rising else '▼' }}</td>
<td data-h="EMA20">{{ '%.3f'|format(r.ema20) }}</td><td data-h="EMA50">{{ '%.3f'|format(r.ema50) }}</td>
<td data-h="Support">{{ '%.3f'|format(r.support[0].price) }}</td><td data-h="Resistance">{{ '%.3f'|format(r.resistance[0].price) }}</td></tr>{% endfor %}
</tbody></table>

<details><summary>How the three screens decide</summary>
<p><b>Screen 1, weekly tide.</b> The slope of the weekly MACD histogram (12/26/9) sets direction, confirmed by the 26-week EMA rising or price above it. Up allows only longs; down allows only shorts; mixed means stand aside.</p>
<p><b>Screen 2, daily wave.</b> Trade against the wave, with the tide. In an up-tide a long qualifies when the 2-day Force Index is below zero, RSI(14) is at or under {{ rsi_l }}, or the day's low touched the 20-day EMA, with price no more than 3% under the 50-day EMA. Shorts mirror this.</p>
<p><b>Screen 3, entry.</b> Buy stop one SGX tick above the last day's high. Stop one tick below the lower of the last two lows, but never closer than {{ min_atr }} ATR. T1 is the nearest resistance cluster above entry; T2 is the next level or 2R, whichever is higher.</p>
<p><b>Grade.</b> One point each for touching the value zone (EMA20), daily MACD histogram turning in the trade direction, R:R to T1 of at least 2, and weekly MACD-H and EMA agreeing. A = 3+ points with R:R &ge; 1.5; B = 2 points with R:R &ge; 1.2; C = the rest.</p>
<p><b>Support and resistance.</b> Swing highs and lows ({{ win }} bars each side) over the last {{ lb }} sessions, merged when within {{ cl }} ATR. The count in brackets is how many swings formed the level.</p>
</details>
{% endblock %}"""

STOCK = """{% extends "base" %}{% block body %}
{% set p = r.plan %}
<div class="stock-head"><h1>{{ r.code }}</h1><span>{{ r.name }}</span>
<span class="badge tile {{ cls.get(r.status,'') }}" style="border-left-width:0"><span class="s">{{ r.status }}{% if p %} &nbsp;grade {{ p.grade }}{% endif %}</span></span>
<span>{{ '%.3f'|format(r.close) }} <span class="{{ 'up' if r.chg_pct>=0 else 'dn' }}">{{ '%+.2f'|format(r.chg_pct) }}%</span></span></div>
<p class="stamp">Bars to {{ r.date }} &nbsp;|&nbsp; {{ meta.source }}{% if meta.demo %} &nbsp;|&nbsp; <b>DEMO DATA</b>{% endif %}</p>
{% if p %}<div class="plan">
<div><span>{{ 'Buy stop' if p.side=='Long' else 'Sell stop' }}</span><b>{{ '%.3f'|format(p.entry) }}</b></div>
<div><span>Stop</span><b class="dn">{{ '%.3f'|format(p.stop) }}</b></div>
<div><span>Target 1</span><b class="up">{{ '%.3f'|format(p.t1) }}</b></div>
<div><span>Target 2</span><b class="up">{{ '%.3f'|format(p.t2) }}</b></div>
<div><span>R:R to T1 / T2</span><b>{{ p.rr1 }} / {{ p.rr2 }}</b></div>
<div><span>Qty ({{ risk_pct }}% risk)</span><b>{{ '{:,}'.format(p.qty) }}</b></div>
<div><span>Cash at risk</span><b>S${{ '{:,.0f}'.format(p.cash_risk) }}</b></div>
</div><p class="note">{{ p.order }}. Take part profit at T1 and move the stop to entry; let the rest run to T2.</p>{% endif %}
{% for n in r.notes %}<p class="warn">{{ n }}</p>{% endfor %}

{% set dl = r.dual %}{% if dl and dl.sm %}{% set bump = 10 if dl.regime_bearish else 0 %}{% set q = dl.plan %}
<h2>Dual score</h2>
<div class="dual"><div class="hd"><b class="dec dec-{{ dl.decision }}">{{ dl.decision }}</b>
<span>Smart Money <b>{{ dl.sm.score }}</b> / needs {{ thr.sm + bump }}</span>
<span>Triple Screen <b>{{ dl.ts.score }}</b> / needs {{ thr.ts + bump }}</span>
<span>SM measured on real data: {{ (dl.sm.confidence * 100)|round|int }}%</span></div>
{% if dl.blocked_by %}<p class="note">Blocked by: {% for b in dl.blocked_by %}{{ labels.get(b, b)|e }}{{ ', ' if not loop.last }}{% endfor %}{% if dl.regime_bearish %}. STI below a falling 50-day EMA, so thresholds are raised by 10.{% endif %}</p>{% endif %}
<div class="sc"><div><h3>Smart Money</h3>{% for k, c in dl.sm.components.items() %}<div class="bar"><div class="lb"><span>{{ labels.get(k, k) }}{% if c.tier.endswith('proxy') %} (estimated){% elif c.tier == 'missing' %} (no data){% endif %}</span></div>
<div class="tr"><div class="fl" style="width:{{ (100 * (c.pts or 0) / c.max)|round|int }}%"></div></div><span>{{ c.pts if c.pts is not none else '-' }} / {{ c.max }}</span></div>{% endfor %}</div>
<div><h3>Triple Screen</h3>{% for k, c in dl.ts.components.items() %}<div class="bar"><div class="lb"><span>{{ labels.get(k, k) }}</span></div>
<div class="tr"><div class="fl" style="width:{{ (100 * c.pts / c.max)|round|int }}%"></div></div><span>{{ c.pts }} / {{ c.max }}</span></div>{% endfor %}</div></div>
<div class="chips">{% for k, g in dl.gates.items() %}<span class="chip {{ '' if g['pass'] else 'no' }}">{{ labels.get(k, k) }}: {{ g.value }}</span>{% endfor %}</div>
<div class="plan"><div><span>Buy stop</span><b>{{ '%.3f'|format(q.entry_buy_stop) }}</b></div>
<div><span>Stop</span><b class="dn">{{ '%.3f'|format(q.stop) }}</b></div>
<div><span>Target 1</span><b class="up">{{ '%.3f'|format(q.target1) }}</b></div>
<div><span>Target 2</span><b class="up">{{ '%.3f'|format(q.target2) }}</b></div>
<div><span>R:R to T1</span><b>{{ q.rr_t1 }}</b></div>
<div><span>Qty ({{ risk_pct }}% risk)</span><b>{{ '{:,}'.format(q.shares or 0) }}</b></div></div>
<p class="note">Dual-score plan (purple dash-dot lines on the chart when BUY or WATCH): buy stop valid 2 sessions; stop to breakeven at +1R; sell half at T1 and trail the rest under EMA20; exit after 7 sessions if under +0.5R.</p></div>
{% endif %}

<div class="screens">
<div><h3>Screen 1, weekly tide</h3><p><b>{{ r.tide.tide }}</b>. MACD-H {{ 'rising' if r.tide.hist_rising else 'falling' }}, EMA26w {{ 'rising' if r.tide.ema26_rising else 'falling' }}, price {{ 'above' if r.tide.above_ema26 else 'below' }} EMA26w. Impulse {{ r.tide.impulse }}.</p></div>
<div><h3>Screen 2, daily wave</h3><p><b>{{ r.wave }}</b>. RSI {{ r.rsi }}, Force(2) {{ '{:,.0f}'.format(r.fi2) }}, EMA20 {{ '%.3f'|format(r.ema20) }}, EMA50 {{ '%.3f'|format(r.ema50) }}.</p></div>
<div><h3>Screen 3, trigger</h3><p>Daily MACD-H {{ 'turning up' if r.macd_hist_rising else 'turning down' }} ({{ r.macd_hist }}). ATR {{ '%.3f'|format(r.atr) }}.</p></div>
</div>

<h2>Daily: EMA 20/50, support/resistance, bid/ask volume, OBV, MACD, RSI</h2>
<div class="chart">{{ daily|safe }}</div>
<p class="note">Volume panel: green = bought at the offer (buyers lifting), red = sold at the bid (sellers hitting), grey = unchanged; dotted line = 20-day average.
Solid bars use the hourly tick rule (last ~60 sessions, same proxy as the Smart Money score); faded bars are estimates from where the close sits in the day's range.
Yahoo has no true bid/ask data, so both are proxies. OBV panel: dotted line = 20-day EMA of OBV.</p>
<h2>Weekly tide: EMA 13/26, MACD histogram</h2>
<div class="chart">{{ weekly|safe }}</div>

<h2>Levels</h2>
<div class="cols"><div><h3>Resistance</h3><ul class="lv">{% for l in r.resistance %}<li><span class="dn">{{ '%.3f'|format(l.price) }}</span><span>{{ l.touches }} swings, {{ '%+.1f'|format((l.price/r.close-1)*100) }}%</span></li>{% endfor %}</ul></div>
<div><h3>Support</h3><ul class="lv">{% for l in r.support %}<li><span class="up">{{ '%.3f'|format(l.price) }}</span><span>{{ l.touches }} swings, {{ '%+.1f'|format((l.price/r.close-1)*100) }}%</span></li>{% endfor %}</ul></div></div>
{% endblock %}"""

ARCHIVE = """{% extends "base" %}{% block body %}
<p class="stamp">Every run is saved in this repository as data/runs/YYYY-MM-DD.json, and all signals are appended to data/signals_log.csv.</p>
<p class="jump"><a href="#saved">Prices &amp; saved runs</a><a href="#dualplans">Dual plans</a><a href="#track">Track record</a></p>
<h2 id="saved">Open a saved run</h2>
<p><select id="runs" aria-label="Run date"></select> &nbsp;<a id="dl-json" href="#">Download JSON</a> &nbsp;<a id="dl-px" href="#">Prices (OHLCV) CSV</a> &nbsp;<a href="data/signals_log.csv" download>Download full CSV log</a></p>
<div style="overflow-x:auto"><table class="t stack" id="run"><thead><tr><th class="l">Stock</th><th class="l">Status</th><th>Grade</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Entry</th><th>Stop</th><th>T1</th><th>T2</th><th>RSI</th><th class="l">Tide</th><th class="l">Dual</th><th>Dual entry</th><th>Dual stop</th><th>Dual T1</th><th>Dual R:R</th></tr></thead><tbody></tbody></table></div>
<p class="note">Entry / Stop / T1 / T2 = original Triple Screen plan (Status). Dual entry / stop / T1 = Dual-Score plan (SafeZone stop from v1.2). Plans are for the next session.</p>

<h2 id="dualplans">Dual-score plans: what happened</h2>
<div id="dsum"></div>
<div style="overflow-x:auto;margin-top:10px"><table class="t stack" id="dual"><thead><tr><th class="l">Signal</th><th class="l">Decision</th><th>SM / TS</th><th>Entry</th><th>Stop</th><th>T1</th><th class="l">Outcome</th><th>Filled</th><th>Closed</th><th>Days</th><th>R</th><th>MFE</th><th>MAE</th></tr></thead><tbody></tbody></table></div>
<p class="note" id="drules"></p>
<p class="note">WATCH plans were not buy signals; their rows show what would have happened if taken. One position per stock at a time. Only runs saved since dual scoring began (13 Nov 2026) appear here.</p>

<h2 id="track">Track record of past setups</h2>
<div id="summary" class="counts"></div>
<div style="overflow-x:auto;margin-top:10px"><table class="t stack" id="outcomes"><thead><tr><th class="l">Signal</th><th class="l">Side</th><th>Grade</th><th>Entry</th><th>Stop</th><th>T1</th><th class="l">Outcome</th><th>Filled</th><th>Closed</th><th>R</th></tr></thead><tbody></tbody></table></div>
<p class="note">Outcomes replay each setup against later daily bars: a fill needs the stop price traded within {{ valid }} sessions; if stop and T1 fall in the same bar the trade is counted as stopped.</p>

<script>
const f = v => (v===null||v===undefined||v==='') ? '' : Number(v).toFixed(3);
function cell(h,v,cls){return `<td data-h="${h}"${cls?` class="${cls}"`:''}>${v}</td>`}
async function loadOutcomes(){
  try{
    const o = await (await fetch('data/outcomes.json',{cache:'no-store'})).json();
    const s = o.summary||{};
    document.getElementById('summary').innerHTML =
      `<span><strong>${s.signals??0}</strong>setups logged</span><span><strong>${s.filled??0}</strong>filled</span>`+
      `<span><strong>${s.closed??0}</strong>closed</span><span><strong>${s.win_rate??'-'}${s.win_rate!=null?'%':''}</strong>hit T1</span>`+
      `<span><strong>${s.expectancy_r??'-'}</strong>avg R per closed trade</span>`;
    const tb = document.querySelector('#outcomes tbody');
    tb.innerHTML = (o.rows||[]).map(r=>`<tr><td>${r.date} <a href="stocks/${r.code}.html"><b>${r.code}</b></a></td>`+
      cell('Side',r.side,'l')+cell('Grade',r.grade)+cell('Entry',f(r.entry))+cell('Stop',f(r.stop))+cell('T1',f(r.t1))+
      cell('Outcome',r.outcome,'l '+(r.outcome==='T1 hit'?'up':r.outcome==='Stopped'?'dn':''))+cell('Filled',r.filled)+cell('Closed',r.closed)+cell('R',r.r??'')+'</tr>').join('')
      || '<tr><td colspan="10">No setups logged yet. They appear here after the first run.</td></tr>';
  }catch(e){document.getElementById('summary').textContent='Track record not available yet: data/outcomes.json is created by the first run.';}
}
async function loadDual(){
  try{
    const o = await (await fetch('data/dual_outcomes.json',{cache:'no-store'})).json();
    const box = k=>{const s=(o.summary||{})[k]||{}; return `<div class="counts"><span><strong>${k}</strong>plans</span>`+
      `<span><strong>${s.plans??0}</strong>logged</span><span><strong>${s.filled??0}</strong>filled</span><span><strong>${s.closed??0}</strong>closed</span>`+
      `<span><strong>${s.win_rate??'-'}${s.win_rate!=null?'%':''}</strong>winners</span><span><strong>${s.avg_r??'-'}</strong>avg R</span>`+
      `<span><strong>${s.avg_mfe_r??'-'} / ${s.avg_mae_r??'-'}</strong>avg MFE / MAE (R)</span><span><strong>${s.avg_days??'-'}</strong>avg days</span></div>`};
    document.getElementById('dsum').innerHTML = box('BUY') + box('WATCH');
    document.getElementById('drules').textContent = 'Rules: ' + (o.rules||'');
    const cls = x => /trail|T1/.test(x)?'up':/Stopped|Time/.test(x)?'dn':'';
    document.querySelector('#dual tbody').innerHTML = (o.rows||[]).map(r=>`<tr><td>${r.date} <a href="stocks/${r.code}.html"><b>${r.code}</b></a> <small>v${r.version}</small></td>`+
      cell('Decision',`<b class="dec-${r.decision}">${r.decision}</b>`,'l')+cell('SM / TS',`${Math.round(r.sm)} / ${Math.round(r.ts)}`)+
      cell('Entry',f(r.entry))+cell('Stop',f(r.stop))+cell('T1',f(r.t1))+cell('Outcome',r.outcome,'l '+cls(r.outcome))+
      cell('Filled',r.filled||'')+cell('Closed',r.closed||'')+cell('Days',r.days??'')+cell('R',r.r??'')+cell('MFE',r.mfe_r??'')+cell('MAE',r.mae_r??'')+'</tr>').join('')
      || '<tr><td colspan="13">No BUY or WATCH plans logged yet.</td></tr>';
  }catch(e){document.getElementById('dsum').textContent='Dual-score replay not available yet: data/dual_outcomes.json is created by the next run.';}
}
async function loadRun(d){
  document.getElementById('dl-json').href = `data/runs/${d}.json`;
  document.getElementById('dl-json').setAttribute('download', `triple-screen-${d}.json`);
  document.getElementById('dl-px').href = `data/prices/${d}.csv`;
  document.getElementById('dl-px').setAttribute('download', `prices-${d}.csv`);
  const j = await (await fetch(`data/runs/${d}.json`)).json();
  let px = {};
  try{ const t = await (await fetch(`data/prices/${d}.csv`)).text();
       const L = t.trim().split(/\\r?\\n/); const H = L[0].split(',');
       L.slice(1).forEach(l=>{const v=l.split(','); const o={}; H.forEach((h,i)=>o[h]=v[i]); px[o.ticker]=o;}); }catch(e){}
  document.querySelector('#run tbody').innerHTML = j.results.map(r=>{const p=r.plan||{}; const b=px[r.ticker]||{}; const dl=r.dual||{};
    return `<tr><td><b>${r.code}</b> ${r.name}</td>`+cell('Status',r.status,'l')+cell('Grade',p.grade||'')+
    cell('Open',f(b.open))+cell('High',f(b.high))+cell('Low',f(b.low))+cell('Close',f(r.close))+
    cell('Entry',f(p.entry))+cell('Stop',f(p.stop))+cell('T1',f(p.t1))+cell('T2',f(p.t2))+cell('RSI',r.rsi)+cell('Tide',r.tide.tide,'l')+
    cell('Dual',dl.decision?`<b class="dec-${dl.decision}">${dl.decision}</b>`:'','l')+
    cell('Dual entry',f((dl.plan||{}).entry_buy_stop))+cell('Dual stop',f((dl.plan||{}).stop))+cell('Dual T1',f((dl.plan||{}).target1))+
    cell('Dual R:R',(dl.plan||{}).rr_t1??'')+'</tr>'}).join('');
}
(async()=>{
  loadOutcomes(); loadDual();
  try{
    const dates = await (await fetch('data/runs/index.json',{cache:'no-store'})).json();
    const sel = document.getElementById('runs');
    sel.innerHTML = dates.map(d=>`<option>${d}</option>`).join('');
    sel.onchange = ()=>loadRun(sel.value);
    if(dates.length) loadRun(dates[0]);
  }catch(e){}
})();
</script>
{% endblock %}"""


METHOD = """{% extends "base" %}{% block body %}
<div class="method">
<p class="stamp">How every number on this site is produced. Spec {{ p.version }} &middot; thresholds below are read from the live settings, so this page always matches the scan.</p>
<p class="jump"><a href="#how">How it works</a><a href="#overview">Overview</a><a href="#status">Status (original)</a><a href="#sm">Smart Money</a><a href="#ts">Triple Screen score</a><a href="#gates">Gates &amp; decision</a><a href="#plan">Trade plan</a><a href="#charts">Charts</a><a href="#gloss">Glossary</a></p>

<h2 id="how">How Triple Screen works (plain English)</h2>
<p>Elder's rule: <b>trade with the tide, buy against the wave, enter only when price confirms</b>. Each screen is a filter; a stock must pass all three, in order.</p>
<div class="mt"><table class="t"><thead><tr><th class="l">Screen</th><th class="l">Question</th><th class="l">What to look for</th></tr></thead><tbody>
<tr><td><b>1 &middot; Tide</b><br>weekly chart</td><td class="l">Which way is the main trend?</td><td class="l">Weekly MACD-histogram rising and the 26-week EMA rising. Up-tide = only look for buys. Weekly Impulse red (13-week EMA and histogram both falling) = no buying.</td></tr>
<tr><td><b>2 &middot; Wave</b><br>daily chart</td><td class="l">Has price pulled back to fair value?</td><td class="l">In an up-tide, wait for a dip <b>into the value zone</b> (shaded band between the daily 13- and 26-EMA). Signs the dip is ending: RSI back to 40&ndash;50, Bear Power below zero and turning up, Force Index(2) below zero.</td></tr>
<tr><td><b>3 &middot; Entry</b><br>next session</td><td class="l">Is the dip over?</td><td class="l">Place a buy-stop 1 tick above today's high. It only fills if buyers push price up through it. Stop below the recent low; take profit at resistance.</td></tr>
</tbody></table></div>
<p><b>Pullback vs Rising vs Extended</b> (the <i>Wave</i> column). In an up-tide the daily price is in one of three states:</p>
<div class="mt"><table class="t"><tbody>
<tr><td><b>Pullback</b></td><td class="l">Price has dipped toward the EMAs, or RSI/Force Index show a dip. This is the buy zone: a setup can form.</td></tr>
<tr><td><b>Rising</b></td><td class="l">Trend up, price moving up, no dip yet. Wait.</td></tr>
<tr><td><b>Extended</b></td><td class="l">Price has already rallied and closed more than {{ c.EXTENDED_ATR }} ATR above the 20-EMA (the dotted orange line on the daily chart). Buying here means chasing: the stop is far away, reward:risk is poor, and price often drifts back to the EMAs first. Wait for it to return to the value zone.</td></tr>
</tbody></table></div>
<p class="note">Example: 20-EMA S$5.00, ATR S$0.10. Close above S${{ "%.2f"|format(5.0 + c.EXTENDED_ATR*0.10) }} = Extended. A dip back to roughly S$4.95&ndash;5.05 (the value zone) is where the next setup would come from.</p>
<p>The site runs this classic method (<b>Status</b> column) and a stricter scored version (<b>Dual</b> column) that adds volume confirmation and hard gates. Both are explained below.</p>

<h2 id="overview">Overview</h2>
<p>Every weekday after the close the scan downloads daily, weekly and hourly prices for the {{ n_univ }} STI stocks and runs <b>two systems side by side</b>:</p>
<div class="mt"><table class="t"><thead><tr><th class="l">Column</th><th class="l">System</th><th class="l">Answers</th><th class="l">Results</th></tr></thead><tbody>
<tr><td><b>Status</b> + Grade</td><td class="l">Original Elder Triple Screen (price only, long and short)</td><td class="l">Is the classic pattern there?</td><td class="l">Long/Short setup, Long/Short watch, No trade; grade A/B/C</td></tr>
<tr><td><b>Dual</b></td><td class="l">Dual-Score system: Smart Money score + Triple Screen score + hard gates (long only)</td><td class="l">Is it a disciplined buy right now?</td><td class="l">BUY / WATCH / AVOID</td></tr>
</tbody></table></div>
<p class="note">Strongest case: Status = Long setup <i>and</i> Dual = BUY. Long setup + WATCH = pattern without enough volume confirmation or a gate failing. All plans are for the <b>next</b> session.</p>

<h2 id="status">1. Status: original Elder Triple Screen</h2>
<p>Elder's idea (<i>Trading for a Living</i>, 1993): trade in the direction of the long timeframe, enter on a short-timeframe move against it, and let the market pull you in with a stop order.</p>
<div class="mt"><table class="t"><thead><tr><th class="l">Screen</th><th class="l">Rule used here</th></tr></thead><tbody>
<tr><td><b>1 &middot; Tide</b> (weekly)</td><td class="l"><b>Up</b> = weekly MACD-histogram rising and (26-week EMA rising or close above it). <b>Down</b> = histogram falling and (EMA falling or close below it). Otherwise <b>Mixed</b> &rarr; No trade. "Strong" = histogram and EMA agree.</td></tr>
<tr><td><b>2 &middot; Wave</b> (daily)</td><td class="l">Up-tide needs a pullback: Force Index(2) &lt; 0, or RSI(14) &le; {{ c.RSI_PULLBACK_LONG }}, or the low touched the 20-EMA (within 0.5%). Close must be &ge; 97% of the 50-EMA and not more than {{ c.EXTENDED_ATR }} ATR above the 20-EMA (too extended). Shorts mirror this (RSI &ge; {{ c.RSI_RALLY_SHORT }}).</td></tr>
<tr><td><b>3 &middot; Entry</b></td><td class="l">Buy-stop 1 tick above today's high, valid {{ c.ORDER_VALID_SESSIONS }} sessions (trail it down to each new high if unfilled). Stop = lower of 2-day low &minus; 1 tick and entry &minus; {{ c.MIN_STOP_ATR }} ATR. T1 = first resistance &gt; 0.25 ATR above entry, else 2R; T2 = next level, at least 2R.</td></tr>
</tbody></table></div>
<p><b>Grade</b> counts 4 checks: touched the 20-EMA value zone &middot; daily MACD-histogram turned up &middot; R:R to T1 &ge; 2 &middot; strong tide. <b>A</b> = 3+ checks and R:R &ge; 1.5; <b>B</b> = 2+ and R:R &ge; 1.2; else <b>C</b>. If R:R to T1 &lt; {{ c.MIN_RR_T1 }} the setup is downgraded to Watch.</p>

<h2 id="sm">2. Smart Money score (0&ndash;100)</h2>
<p>Asks: <i>is volume showing accumulation?</i> Only volume-based measures live here (no price oscillators), so nothing is counted twice. Each component scores 0 &rarr; full points on a straight line between the two values shown.</p>
<div class="mt"><table class="t"><thead><tr><th class="l">Component</th><th>Pts</th><th class="l">What is measured</th><th class="l">0 pts &rarr; full pts</th></tr></thead><tbody>
<tr><td><b>Successful bid/ask</b></td><td>{{ p.w_bidask|int }}</td><td class="l">Share of volume that <b>lifted the offer</b> (aggressive buyers). 70% on the last 5 sessions + 30% on improvement vs 20 sessions. Hourly tick rule as proxy (up-tick bar = buy volume).</td><td class="l">45% &rarr; 62% buy share; &minus;2 &rarr; +8 pts improvement</td></tr>
<tr><td><b>Price-volume</b></td><td>{{ p.w_pricevol|int }}</td><td class="l">Volume on up days &divide; volume on down days, last 20 sessions (log scale).</td><td class="l">0.8&times; &rarr; 1.8&times;</td></tr>
<tr><td><b>Block trades</b></td><td>{{ p.w_block|int }}</td><td class="l">Net large-trade flow, last 10 sessions. Proxy: days with &ge; 2&times; average volume, signed by the close and where it sits in the range.</td><td class="l">net &minus;20% &rarr; +60%</td></tr>
<tr><td><b>VWAP</b></td><td>{{ p.w_vwap|int }}</td><td class="l">Close vs VWAP anchored at the 60-day low (in ATR) 50% + slope of the 20-day rolling VWAP 50%.</td><td class="l">&minus;0.5 &rarr; +1.0 ATR; &minus;1% &rarr; +2%</td></tr>
<tr><td><b>OBV</b></td><td>{{ p.w_obv|int }}</td><td class="l">20-day OBV slope &divide; average volume 70% + where OBV sits in its 60-day range 30%.</td><td class="l">&minus;0.1 &rarr; +0.3</td></tr>
<tr><td><b>Closing strength</b></td><td>{{ p.w_close|int }}</td><td class="l">Average close-location value (where the close sits between low and high) over 5 sessions.</td><td class="l">0.30 &rarr; 0.75</td></tr>
</tbody></table></div>
<p class="note">Missing components are re-weighted over the rest. <b>Confidence</b> = share of the weight measured on real (not proxy) data. Yahoo has no true bid/ask feed, so the bid/ask and block components are always proxies here.</p>

<h2 id="ts">3. Triple Screen score (0&ndash;100)</h2>
<p>Asks: <i>is the price pattern right?</i> Price indicators only; each used once.</p>
<div class="mt"><table class="t"><thead><tr><th class="l">Screen</th><th>Pts</th><th class="l">Checks (points)</th></tr></thead><tbody>
<tr><td><b>1 &middot; Trend alignment</b></td><td>{{ p.w_s1|int }}</td><td class="l">Weekly MACD-histogram rising (15: 2 weeks = full, 1 week = 60%) &middot; weekly 26-EMA 4-week slope &minus;1% &rarr; +3% (15) &middot; close above a rising daily 50-EMA (10)</td></tr>
<tr><td><b>2 &middot; Pullback quality</b></td><td>{{ p.w_s2|int }}</td><td class="l">{% if p.bear_power %}RSI(14) 5-day low in 38&ndash;52 after RSI &ge; 58 within 20 days (9) &middot; 3-day low inside the <b>13&ndash;26 EMA value zone</b> (10) &middot; Fibonacci retracement of the last swing 38.2&ndash;61.8% (8) &middot; <b>Bear Power</b> below zero and turning up (8){% else %}RSI dip (12) &middot; 20-EMA zone (12) &middot; Fibonacci (11){% endif %}</td></tr>
<tr><td><b>3 &middot; Entry confirmation</b></td><td>{{ p.w_s3|int }}</td><td class="l">{% if p.drop_ha %}Close above prior high (14; above prior close = 40%) &middot; daily MACD-histogram up 2 bars (11; 1 bar = 60%){% else %}Close above prior high (10) &middot; MACD-hist upticks (8) &middot; Heikin-Ashi green (7){% endif %}</td></tr>
</tbody></table></div>

<h2 id="gates">4. Hard gates &amp; decision</h2>
<p>Gates are pass/fail filters, not scored. <b>All</b> must pass for a BUY.</p>
<div class="mt"><table class="t"><thead><tr><th class="l">Gate</th><th class="l">Rule</th></tr></thead><tbody>
<tr><td>Liquidity</td><td class="l">20-day average turnover &ge; S${{ "{:,.0f}".format(p.min_value_traded) }}</td></tr>
<tr><td>Reward:risk</td><td class="l">T1 is at least {{ p.min_rr }}R above entry</td></tr>
<tr><td>ATR band</td><td class="l">ATR is {{ p.atr_pct_range[0] }}&ndash;{{ p.atr_pct_range[1] }}% of price (not dead, not wild)</td></tr>
<tr><td>Stop width</td><td class="l">Stop no wider than {{ p.max_stop_atr }} ATR</td></tr>
{% if p.impulse_veto %}<tr><td>Weekly Impulse</td><td class="l">Not red (red = weekly 13-EMA and MACD-histogram both falling: Elder's "no buying" signal)</td></tr>{% endif %}
<tr><td>Events</td><td class="l">No results or ex-dividend within 5 sessions (when dates are supplied)</td></tr>
<tr><td>6% rule</td><td class="l">Open risk + this month's loss + new trade risk &le; {{ p.max_month_risk_pct|int }}% of equity (only when portfolio figures are supplied; always on in the backtest)</td></tr>
</tbody></table></div>
<div class="mt"><table class="t"><thead><tr><th class="l">Decision</th><th class="l">Needs</th></tr></thead><tbody>
<tr><td><b class="dec-BUY">BUY</b></td><td class="l">All gates pass &middot; TS &ge; {{ p.ts_buy|int }} &middot; SM &ge; {{ p.sm_buy|int }} &middot; bid/ask component &ge; {{ (p.bidask_floor * p.w_bidask)|round(1) }} of {{ p.w_bidask|int }}</td></tr>
<tr><td><b class="dec-WATCH">WATCH</b></td><td class="l">TS &ge; {{ (p.ts_buy - 10)|int }} and SM &ge; {{ (p.sm_buy - 15)|int }}, but not a BUY</td></tr>
<tr><td><b class="dec-AVOID">AVOID</b></td><td class="l">Everything else</td></tr>
</tbody></table></div>
<p class="note">When the STI is bearish (below a falling 50-EMA) both BUY thresholds rise by {{ p.regime_penalty|int }}. "Blocked by" on each stock lists exactly which gate or score failed.</p>

<h2 id="plan">5. Dual-score trade plan &amp; management</h2>
<div class="mt"><table class="t"><tbody>
<tr><td><b>Entry</b></td><td class="l">Buy-stop 1 tick above today's high (SGX ticks: 0.001 below S$0.20, 0.005 below S$1, 0.01 from S$1), valid 2 sessions.</td></tr>
<tr><td><b>Stop</b></td><td class="l">{% if p.stop_method == "safezone" %}<b>SafeZone</b>: today's low &minus; {{ p.safezone_coef }} &times; the average amount the low was undercut over {{ p.safezone_lookback }} sessions; never closer than {{ p.min_stop_atr }} ATR to entry.{% else %}5-day low &minus; 1 tick.{% endif %}</td></tr>
<tr><td><b>T1</b></td><td class="l">First resistance at least 1 ATR above entry (swing highs over 250 days + 52-week high, clustered), else 2R.</td></tr>
<tr><td><b>T2</b></td><td class="l">{% if p.channel_t2 %}Nearer of the 2nd resistance and the top of the price channel (22-EMA envelope holding 95% of the last 100 bars), at least T1 + 0.5 ATR.{% else %}Next resistance, else 3R.{% endif %}</td></tr>
<tr><td><b>Size</b></td><td class="l">Risk {{ p.risk_pct }}% of equity (S${{ "{:,.0f}".format(c.ACCOUNT_SIZE_SGD) }} in settings) &divide; (entry &minus; stop), in 100-share lots.</td></tr>
<tr><td><b>Manage</b></td><td class="l">Move stop to breakeven at +1R &rarr; sell half at T1 &rarr; exit the rest on a close below the 20-EMA &rarr; time stop after 7 sessions if under +0.5R &rarr; max hold 30 sessions.</td></tr>
</tbody></table></div>
<p class="note"><b>R</b> = profit or loss in units of the initial risk (entry &minus; stop). +2R = made twice what was risked. <b>MFE / MAE</b> on Saved runs = best and worst move from the fill, in R.</p>

<h2 id="charts">6. Reading the charts</h2>
<div class="mt"><table class="t"><tbody>
<tr><td><b>Price</b></td><td class="l">Candles, shaded <b>value zone</b> (band between the daily 13- and 26-EMA: where pullbacks are bought), dotted orange <b>Extended</b> line (20-EMA + {{ c.EXTENDED_ATR }} ATR: close above it = too far to chase), 20-EMA (blue: trailing exit after T1), 50-EMA (gold: daily trend), support (green) and resistance (red) levels with touch counts, original plan lines (entry/stop/T1/T2) and, for BUY/WATCH, dual plan lines (purple, "DS").</td></tr>
<tr><td><b>Vol bid/ask</b></td><td class="l">Green = bought at the offer, red = sold at the bid, grey = unchanged; dotted = 20-day average. Solid bars: hourly tick rule (last ~60 sessions); faded: estimate from the close's position in the range.</td></tr>
<tr><td><b>OBV</b></td><td class="l">On-Balance Volume with dotted 20-day EMA. Rising OBV while price pulls back = accumulation.</td></tr>
<tr><td><b>MACD</b></td><td class="l">Histogram (green above 0, red below), MACD line (blue) and signal (gold). Histogram turning up = momentum improving.</td></tr>
<tr><td><b>RSI</b></td><td class="l">14-day; 70 overbought, 30 oversold. In an up-trend, dips to 40&ndash;50 are the pullbacks this system buys.</td></tr>
<tr><td><b>Weekly</b></td><td class="l">13- and 26-week EMAs; histogram coloured by slope (green rising, red falling) = the tide.</td></tr>
</tbody></table></div>

<h2 id="gloss">7. Glossary</h2>
<dl class="gl">
<dt>EMA</dt><dd>Exponential moving average; weights recent prices more.</dd>
<dt>MACD / histogram</dt><dd>12-EMA minus 26-EMA, with a 9-period signal line; histogram = MACD minus signal. Its slope is Elder's main trend tool.</dd>
<dt>RSI</dt><dd>Relative Strength Index (14): 0&ndash;100 measure of recent gains vs losses.</dd>
<dt>ATR</dt><dd>Average True Range (14): typical daily range, used to size stops and distances.</dd>
<dt>Force Index (2)</dt><dd>2-day EMA of (price change &times; volume). Below 0 in an up-trend = pullback (original system only).</dd>
<dt>Bear Power</dt><dd>Elder-ray: daily low &minus; 13-EMA. Negative but rising in an up-trend = sellers fading.</dd>
<dt>Value zone</dt><dd>Area between the fast and slow EMAs (here the daily 13- and 26-EMA, shaded on the chart) where Elder buys pullbacks.</dd>
<dt>Extended</dt><dd>Price has run too far above value (close &gt; 20-EMA + {{ c.EXTENDED_ATR }} ATR). Not a sell signal: the trend may still be up, but a new buy has poor reward:risk. Wait for the pullback.</dd>
<dt>Impulse System</dt><dd>Green = 13-EMA and MACD-histogram both rising; red = both falling; blue = mixed.</dd>
<dt>SafeZone</dt><dd>Elder's stop placed beyond normal noise: recent average downside penetration &times; a factor.</dd>
<dt>OBV</dt><dd>On-Balance Volume: running total adding volume on up days, subtracting it on down days.</dd>
<dt>VWAP</dt><dd>Volume-weighted average price; "anchored" = measured from a chosen start (here the 60-day low).</dd>
<dt>CLV</dt><dd>Close location value: 0 = closed at the low, 1 = at the high.</dd>
<dt>Tick rule</dt><dd>A trade (or hourly bar) above the previous price counts as buying, below as selling.</dd>
<dt>Fibonacci retracement</dt><dd>How much of the last up-swing a pullback has given back; 38.2&ndash;61.8% is the classic buy zone.</dd>
<dt>R:R</dt><dd>Reward to risk: (target &minus; entry) &divide; (entry &minus; stop).</dd>
</dl>

<h2>Data &amp; limits</h2>
<p class="note">Prices: Yahoo Finance via yfinance, unadjusted, usually 10&ndash;20 min delayed intraday; a scan during trading hours uses the day's bar so far. No true bid/ask or tick data, so bid/ask and block components are proxies. The STI list is today's constituents. This site is a screening aid, not advice: verify every level on your broker terminal before placing an order.</p>
</div>
<script>
document.querySelectorAll('.method table.t').forEach(t=>{
  const h=[...t.querySelectorAll('thead th')].map(x=>x.textContent);
  if(!h.length) return;
  t.querySelectorAll('tbody tr').forEach(r=>[...r.children].forEach((c,i)=>{ if(i>0&&h[i]) c.setAttribute('data-h',h[i]); }));
});
</script>
{% endblock %}"""


def _env():
    return Environment(loader=DictLoader({"base": BASE}), autoescape=False)


def build(out: Path, meta: dict, results: list, sti: dict):
    out.mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)
    (out / "stocks").mkdir(exist_ok=True)
    (out / "assets" / "style.css").write_text(CSS)
    (out / "assets" / "theme.js").write_text(THEME_JS)
    (out / ".nojekyll").write_text("")
    env = _env()
    common = dict(site=C.SITE_TITLE, meta=meta, cls=CLS, risk_pct=C.RISK_PER_TRADE_PCT,
                  acct=C.ACCOUNT_SIZE_SGD, lot=C.BOARD_LOT, valid=C.ORDER_VALID_SESSIONS,
                  thr=meta.get("dual_thresholds", {"ts": 70, "sm": 65}), labels=LABELS)
    scored = [r for r in results if (r.get("dual") or {}).get("sm")]
    order = {"BUY": 0, "WATCH": 1, "AVOID": 2}
    scored.sort(key=lambda r: (order.get(r["dual"]["decision"], 3), -r["dual"]["combined"]))
    keep = [r for r in scored if r["dual"]["decision"] != "AVOID"]
    dual_rows = keep + [r for r in scored if r["dual"]["decision"] == "AVOID"][:max(0, 8 - len(keep))]
    dual_bear = any(r["dual"].get("regime_bearish") for r in scored)

    setups = [r for r in results if r.get("plan")]
    counts = dict(ls=sum(r["status"] == SETUP_LONG for r in results),
                  ss=sum(r["status"] == SETUP_SHORT for r in results),
                  w=sum(r["status"] in (WATCH_LONG, WATCH_SHORT) for r in results),
                  n=sum(r["status"] == "No trade" for r in results))
    html = env.from_string(INDEX).render(title=f"{C.SITE_TITLE} {meta['as_of']}", root="", page="home",
                                         plotly=None, results=results, setups=setups, counts=counts, sti=sti,
                                         rsi_l=C.RSI_PULLBACK_LONG, min_atr=C.MIN_STOP_ATR, win=C.SR_PIVOT_WINDOW,
                                         lb=C.SR_LOOKBACK, cl=C.SR_CLUSTER_ATR,
                                         dual_rows=dual_rows, dual_bear=dual_bear, **common)
    (out / "index.html").write_text(html)

    tpl = env.from_string(STOCK)
    for r in results:
        page = tpl.render(title=f"{r['code']} {r['name']} | {C.SITE_TITLE}", root="../", page="stock",
                          plotly=PLOTLY, r=r, daily=to_div(daily_chart(r), "daily"),
                          weekly=to_div(weekly_chart(r), "weekly"), **common)
        (out / "stocks" / f"{r['code']}.html").write_text(page)

    try:                                   # never let the explainer page break the scan
        from . import dualscore as _ds
        (out / "method.html").write_text(env.from_string(METHOD).render(
            title=f"Methodology | {C.SITE_TITLE}", root="", page="method", plotly=None,
            p=_ds.Params(), c=C, n_univ=len(C.UNIVERSE), **common))
    except Exception as e:
        print(f"methodology page skipped: {e}")
    (out / "archive.html").write_text(env.from_string(ARCHIVE).render(
        title=f"Saved runs | {C.SITE_TITLE}", root="", page="archive", plotly=None, **common))
