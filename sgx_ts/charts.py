"""Plotly charts: daily (price + S/R + plan, bid/ask volume, OBV, MACD, RSI) and weekly (tide)."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as C

UP, DN = "#127A5F", "#B23A3A"
EMA20_C, EMA50_C, EMA13_C, EMA26_C = "#2F5FA7", "#B7862B", "#2F5FA7", "#B7862B"
SUP_C, RES_C = "#127A5F", "#B23A3A"
ENTRY_C, STOP_C, TGT_C = "#2F5FA7", "#B23A3A", "#127A5F"
GRID = "rgba(120,135,140,0.18)"
DS_C = "#7A4FB0"   # dual-score plan lines


def _layout(fig, height):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Barlow Semi Condensed, Arial Narrow, sans-serif", size=12, color="#5E6B70"),
        showlegend=True, legend=dict(orientation="h", y=1.0, x=0, yanchor="bottom", font=dict(size=11)),
        hovermode="x unified", dragmode="pan", xaxis_rangeslider_visible=False,
    )
    fig.update_xaxes(type="category", showgrid=False, nticks=6, tickangle=0, showspikes=True,
                     spikemode="across", spikethickness=1, spikedash="dot")
    fig.update_yaxes(gridcolor=GRID, zeroline=False, side="right")
    return fig


def _hline(fig, y, color, text, row=1, dash="dot", width=1):
    fig.add_hline(y=y, line=dict(color=color, width=width, dash=dash), row=row, col=1,
                  annotation_text=text, annotation_position="top left",
                  annotation_font=dict(size=10, color=color))


def bidask_split(daily: pd.DataFrame, hourly: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily volume split into buyer-initiated (lifted the offer) and seller-initiated (hit the bid).
    Hourly tick rule where 60m bars exist (same proxy as the Smart Money score), scaled to the
    day's total volume; otherwise a close-location estimate: buy share = (C-L)/(H-L)."""
    v = daily["Volume"].fillna(0)
    rng = (daily["High"] - daily["Low"]).replace(0, np.nan)
    share = ((daily["Close"] - daily["Low"]) / rng).fillna(0.5).clip(0, 1)
    out = pd.DataFrame({"buy": v * share, "sell": v * (1 - share), "neutral": 0.0, "src": "est"}, index=daily.index)
    if hourly is not None and len(hourly) > 40:
        sgn = np.sign(hourly["Close"].diff()).replace(0, np.nan).ffill().fillna(0)
        day = hourly.index.normalize()
        hb = (hourly["Volume"] * (sgn > 0)).groupby(day).sum()
        hs = (hourly["Volume"] * (sgn < 0)).groupby(day).sum()
        ht = hourly["Volume"].groupby(day).sum()
        for dt in ht.index:
            if dt in out.index and ht[dt] > 0:
                k = v.loc[dt] / ht[dt] if v.loc[dt] > 0 else 1.0
                out.loc[dt, ["buy", "sell", "neutral", "src"]] = [hb[dt] * k, hs[dt] * k,
                                                                 (ht[dt] - hb[dt] - hs[dt]) * k, "hourly"]
    return out


def obv(daily: pd.DataFrame) -> pd.Series:
    return (np.sign(daily["Close"].diff()).fillna(0) * daily["Volume"].fillna(0)).cumsum()


def daily_chart(r: dict):
    full = r["_daily"]
    d = full.tail(C.CHART_DAILY_BARS)
    x = d.index.strftime("%d %b %y")
    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.025,
                        row_heights=[0.46, 0.14, 0.12, 0.14, 0.14])
    fig.add_trace(go.Candlestick(x=x, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
                                 name="Price", increasing_line_color=UP, decreasing_line_color=DN,
                                 increasing_fillcolor=UP, decreasing_fillcolor=DN, showlegend=False), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=d["EMA20"], name="EMA 20", line=dict(color=EMA20_C, width=1.4)), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=d["EMA50"], name="EMA 50", line=dict(color=EMA50_C, width=1.4)), 1, 1)

    for l in r["support"]:
        _hline(fig, l["price"], SUP_C, f"S {l['price']:.3f} ({l['touches']}x)")
    for l in r["resistance"]:
        _hline(fig, l["price"], RES_C, f"R {l['price']:.3f} ({l['touches']}x)")

    p = r.get("plan")
    if p:
        _hline(fig, p["entry"], ENTRY_C, f"Entry {p['entry']:.3f}", dash="solid", width=1.6)
        _hline(fig, p["stop"], STOP_C, f"Stop {p['stop']:.3f}", dash="solid", width=1.6)
        _hline(fig, p["t1"], TGT_C, f"T1 {p['t1']:.3f}", dash="dash", width=1.6)
        _hline(fig, p["t2"], TGT_C, f"T2 {p['t2']:.3f}", dash="dash", width=1.2)

    dl = r.get("dual") or {}
    dp = dl.get("plan")
    if dp and dl.get("decision") in ("BUY", "WATCH"):
        tag = "DS " + dl["decision"]
        _hline(fig, dp["entry_buy_stop"], DS_C, f"{tag} entry {dp['entry_buy_stop']:.3f}", dash="dashdot", width=1.4)
        _hline(fig, dp["stop"], DS_C, f"{tag} stop {dp['stop']:.3f}", dash="dashdot", width=1.2)
        _hline(fig, dp["target1"], DS_C, f"{tag} T1 {dp['target1']:.3f}", dash="dashdot", width=1.2)

    # ---- volume: lifted offer vs hit bid
    ba = bidask_split(full, r.get("_hourly")).loc[d.index]
    hr = (ba["src"] == "hourly").values
    tot = (ba["buy"] + ba["sell"] + ba["neutral"]).replace(0, np.nan)
    bpct = (100 * ba["buy"] / tot).round(0).fillna(0)
    src = np.where(hr, "hourly tick rule", "estimate (close in range)")
    for col_, nm, c in (("buy", "Lifted offer (buy)", UP), ("sell", "Hit bid (sell)", DN), ("neutral", "Unchanged", "#9AA5A8")):
        fig.add_trace(go.Bar(x=x, y=ba[col_], name=nm, marker_color=c, marker_opacity=np.where(hr, 0.9, 0.35),
                             customdata=np.c_[bpct, src], showlegend=False,
                             hovertemplate=f"{nm}: %{{y:,.0f}} (buy %{{customdata[0]}}%%, %{{customdata[1]}})<extra></extra>"
                             if col_ == "buy" else f"{nm}: %{{y:,.0f}}<extra></extra>"), 2, 1)
    fig.add_trace(go.Scatter(x=x, y=full["Volume"].rolling(20).mean().loc[d.index], name="Vol 20d avg",
                             line=dict(color="#5E6B70", width=1, dash="dot"), showlegend=False), 2, 1)
    fig.update_layout(barmode="relative")
    # ---- OBV
    o = obv(full)
    fig.add_trace(go.Scatter(x=x, y=o.loc[d.index], name="OBV", line=dict(color="#2F5FA7", width=1.3), showlegend=False), 3, 1)
    fig.add_trace(go.Scatter(x=x, y=o.ewm(span=20, adjust=False).mean().loc[d.index], name="OBV EMA20",
                             line=dict(color=EMA50_C, width=1, dash="dot"), showlegend=False), 3, 1)
    fig.update_yaxes(title_text="Vol bid/ask", title_font=dict(size=10), row=2, col=1)
    fig.update_yaxes(title_text="OBV", title_font=dict(size=10), row=3, col=1)

    hcol = [UP if v >= 0 else DN for v in d["MACDhist"]]
    fig.add_trace(go.Bar(x=x, y=d["MACDhist"], marker_color=hcol, name="MACD hist", showlegend=False), 4, 1)
    fig.add_trace(go.Scatter(x=x, y=d["MACD"], name="MACD", line=dict(color=EMA20_C, width=1.2), showlegend=False), 4, 1)
    fig.add_trace(go.Scatter(x=x, y=d["MACDsig"], name="Signal", line=dict(color=EMA50_C, width=1.2), showlegend=False), 4, 1)

    fig.add_trace(go.Scatter(x=x, y=d["RSI"], name="RSI 14", line=dict(color="#6B4FA0", width=1.3), showlegend=False), 5, 1)
    for lvl, c in ((70, DN), (30, UP)):
        fig.add_hline(y=lvl, line=dict(color=c, width=1, dash="dot"), row=5, col=1)
    fig.update_yaxes(range=[0, 100], row=5, col=1, tickvals=[30, 50, 70])
    fig.update_yaxes(title_text="MACD", title_font=dict(size=10), row=4, col=1)
    fig.update_yaxes(title_text="RSI", title_font=dict(size=10), row=5, col=1)
    return _layout(fig, 860)


def weekly_chart(r: dict):
    w = r["_weekly"].tail(C.CHART_WEEKLY_BARS)
    x = w.index.strftime("%d %b %y")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.68, 0.32])
    fig.add_trace(go.Candlestick(x=x, open=w["Open"], high=w["High"], low=w["Low"], close=w["Close"],
                                 increasing_line_color=UP, decreasing_line_color=DN,
                                 increasing_fillcolor=UP, decreasing_fillcolor=DN, showlegend=False, name="Week"), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=w["EMA13"], name="EMA 13w", line=dict(color=EMA13_C, width=1.3)), 1, 1)
    fig.add_trace(go.Scatter(x=x, y=w["EMA26"], name="EMA 26w", line=dict(color=EMA26_C, width=1.3)), 1, 1)
    h = w["MACDhist"]
    col = [UP if i > 0 and h.iloc[i] > h.iloc[i - 1] else DN if i > 0 else "#999" for i in range(len(h))]
    fig.add_trace(go.Bar(x=x, y=h, marker_color=col, name="Weekly MACD hist (slope colour)", showlegend=False), 2, 1)
    fig.update_yaxes(title_text="MACD-H", title_font=dict(size=10), row=2, col=1)
    return _layout(fig, 400)


def to_div(fig, div_id):
    return fig.to_html(include_plotlyjs=False, full_html=False, div_id=div_id,
                       config={"displaylogo": False, "responsive": True, "scrollZoom": True,
                               "modeBarButtonsToRemove": ["select2d", "lasso2d", "autoScale2d"]})
