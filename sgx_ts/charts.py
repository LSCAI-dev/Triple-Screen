"""Plotly charts: daily (price + S/R + plan, MACD, RSI) and weekly (tide)."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as C

UP, DN = "#127A5F", "#B23A3A"
EMA20_C, EMA50_C, EMA13_C, EMA26_C = "#2F5FA7", "#B7862B", "#2F5FA7", "#B7862B"
SUP_C, RES_C = "#127A5F", "#B23A3A"
ENTRY_C, STOP_C, TGT_C = "#2F5FA7", "#B23A3A", "#127A5F"
GRID = "rgba(120,135,140,0.18)"


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


def daily_chart(r: dict):
    d = r["_daily"].tail(C.CHART_DAILY_BARS)
    x = d.index.strftime("%d %b %y")
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.6, 0.2, 0.2])
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

    hcol = [UP if v >= 0 else DN for v in d["MACDhist"]]
    fig.add_trace(go.Bar(x=x, y=d["MACDhist"], marker_color=hcol, name="MACD hist", showlegend=False), 2, 1)
    fig.add_trace(go.Scatter(x=x, y=d["MACD"], name="MACD", line=dict(color=EMA20_C, width=1.2), showlegend=False), 2, 1)
    fig.add_trace(go.Scatter(x=x, y=d["MACDsig"], name="Signal", line=dict(color=EMA50_C, width=1.2), showlegend=False), 2, 1)

    fig.add_trace(go.Scatter(x=x, y=d["RSI"], name="RSI 14", line=dict(color="#6B4FA0", width=1.3), showlegend=False), 3, 1)
    for lvl, c in ((70, DN), (30, UP)):
        fig.add_hline(y=lvl, line=dict(color=c, width=1, dash="dot"), row=3, col=1)
    fig.update_yaxes(range=[0, 100], row=3, col=1, tickvals=[30, 50, 70])
    fig.update_yaxes(title_text="MACD", title_font=dict(size=10), row=2, col=1)
    fig.update_yaxes(title_text="RSI", title_font=dict(size=10), row=3, col=1)
    return _layout(fig, 620)


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
