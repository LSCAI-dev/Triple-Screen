"""Builds the GitHub Pages site into docs/."""
from pathlib import Path
from jinja2 import Environment, DictLoader

import config as C
from .assets import CSS, THEME_JS
from .charts import daily_chart, weekly_chart, to_div
from .screens import SETUP_LONG, SETUP_SHORT, WATCH_LONG, WATCH_SHORT

PLOTLY = "https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.2/plotly.min.js"
CLS = {SETUP_LONG: "st-long", SETUP_SHORT: "st-short", WATCH_LONG: "st-lwatch", WATCH_SHORT: "st-swatch"}

BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{{ title }}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>📈</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{{ root }}assets/style.css">
{% if plotly %}<script src="{{ plotly }}"></script>{% endif %}
</head><body><div class="wrap">
<header class="top"><h1>{{ site }}</h1>
<nav><a href="{{ root }}index.html" {% if page=='home' %}aria-current="page"{% endif %}>Today</a><a href="{{ root }}archive.html" {% if page=='archive' %}aria-current="page"{% endif %}>Saved runs</a></nav></header>
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
<div class="s">{{ r.status }}</div></a>{% endfor %}</div>

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

<div class="screens">
<div><h3>Screen 1, weekly tide</h3><p><b>{{ r.tide.tide }}</b>. MACD-H {{ 'rising' if r.tide.hist_rising else 'falling' }}, EMA26w {{ 'rising' if r.tide.ema26_rising else 'falling' }}, price {{ 'above' if r.tide.above_ema26 else 'below' }} EMA26w. Impulse {{ r.tide.impulse }}.</p></div>
<div><h3>Screen 2, daily wave</h3><p><b>{{ r.wave }}</b>. RSI {{ r.rsi }}, Force(2) {{ '{:,.0f}'.format(r.fi2) }}, EMA20 {{ '%.3f'|format(r.ema20) }}, EMA50 {{ '%.3f'|format(r.ema50) }}.</p></div>
<div><h3>Screen 3, trigger</h3><p>Daily MACD-H {{ 'turning up' if r.macd_hist_rising else 'turning down' }} ({{ r.macd_hist }}). ATR {{ '%.3f'|format(r.atr) }}.</p></div>
</div>

<h2>Daily: EMA 20/50, support/resistance, MACD, RSI</h2>
<div class="chart">{{ daily|safe }}</div>
<h2>Weekly tide: EMA 13/26, MACD histogram</h2>
<div class="chart">{{ weekly|safe }}</div>

<h2>Levels</h2>
<div class="cols"><div><h3>Resistance</h3><ul class="lv">{% for l in r.resistance %}<li><span class="dn">{{ '%.3f'|format(l.price) }}</span><span>{{ l.touches }} swings, {{ '%+.1f'|format((l.price/r.close-1)*100) }}%</span></li>{% endfor %}</ul></div>
<div><h3>Support</h3><ul class="lv">{% for l in r.support %}<li><span class="up">{{ '%.3f'|format(l.price) }}</span><span>{{ l.touches }} swings, {{ '%+.1f'|format((l.price/r.close-1)*100) }}%</span></li>{% endfor %}</ul></div></div>
{% endblock %}"""

ARCHIVE = """{% extends "base" %}{% block body %}
<p class="stamp">Every run is saved in this repository as data/runs/YYYY-MM-DD.json, and all signals are appended to data/signals_log.csv.</p>
<h2>Track record of past setups</h2>
<div id="summary" class="counts"></div>
<div style="overflow-x:auto;margin-top:10px"><table class="t stack" id="outcomes"><thead><tr><th class="l">Signal</th><th class="l">Side</th><th>Grade</th><th>Entry</th><th>Stop</th><th>T1</th><th class="l">Outcome</th><th>Filled</th><th>Closed</th><th>R</th></tr></thead><tbody></tbody></table></div>
<p class="note">Outcomes replay each setup against later daily bars: a fill needs the stop price traded within {{ valid }} sessions; if stop and T1 fall in the same bar the trade is counted as stopped.</p>

<h2>Open a saved run</h2>
<p><select id="runs" aria-label="Run date"></select> &nbsp;<a id="dl-json" href="#">Download JSON</a> &nbsp;<a href="data/signals_log.csv" download>Download full CSV log</a></p>
<div style="overflow-x:auto"><table class="t stack" id="run"><thead><tr><th class="l">Stock</th><th class="l">Status</th><th>Grade</th><th>Close</th><th>Entry</th><th>Stop</th><th>T1</th><th>T2</th><th>RSI</th><th class="l">Tide</th></tr></thead><tbody></tbody></table></div>
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
async function loadRun(d){
  document.getElementById('dl-json').href = `data/runs/${d}.json`;
  document.getElementById('dl-json').setAttribute('download', `triple-screen-${d}.json`);
  const j = await (await fetch(`data/runs/${d}.json`)).json();
  document.querySelector('#run tbody').innerHTML = j.results.map(r=>{const p=r.plan||{};
    return `<tr><td><b>${r.code}</b> ${r.name}</td>`+cell('Status',r.status,'l')+cell('Grade',p.grade||'')+cell('Close',f(r.close))+
    cell('Entry',f(p.entry))+cell('Stop',f(p.stop))+cell('T1',f(p.t1))+cell('T2',f(p.t2))+cell('RSI',r.rsi)+cell('Tide',r.tide.tide,'l')+'</tr>'}).join('');
}
(async()=>{
  loadOutcomes();
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
                  acct=C.ACCOUNT_SIZE_SGD, lot=C.BOARD_LOT, valid=C.ORDER_VALID_SESSIONS)

    setups = [r for r in results if r.get("plan")]
    counts = dict(ls=sum(r["status"] == SETUP_LONG for r in results),
                  ss=sum(r["status"] == SETUP_SHORT for r in results),
                  w=sum(r["status"] in (WATCH_LONG, WATCH_SHORT) for r in results),
                  n=sum(r["status"] == "No trade" for r in results))
    html = env.from_string(INDEX).render(title=f"{C.SITE_TITLE} {meta['as_of']}", root="", page="home",
                                         plotly=None, results=results, setups=setups, counts=counts, sti=sti,
                                         rsi_l=C.RSI_PULLBACK_LONG, min_atr=C.MIN_STOP_ATR, win=C.SR_PIVOT_WINDOW,
                                         lb=C.SR_LOOKBACK, cl=C.SR_CLUSTER_ATR, **common)
    (out / "index.html").write_text(html)

    tpl = env.from_string(STOCK)
    for r in results:
        page = tpl.render(title=f"{r['code']} {r['name']} | {C.SITE_TITLE}", root="../", page="stock",
                          plotly=PLOTLY, r=r, daily=to_div(daily_chart(r), "daily"),
                          weekly=to_div(weekly_chart(r), "weekly"), **common)
        (out / "stocks" / f"{r['code']}.html").write_text(page)

    (out / "archive.html").write_text(env.from_string(ARCHIVE).render(
        title=f"Saved runs | {C.SITE_TITLE}", root="", page="archive", plotly=None, **common))
