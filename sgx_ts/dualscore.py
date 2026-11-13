"""
SGX Dual-Score Buy System
=========================
Two independent scores + hard gates -> one disciplined BUY / WATCH / AVOID decision.

  1. Smart Money Score (SM, 0-100)  - who is buying (order flow / volume)
  2. Triple Screen Score (TS, 0-100) - is the chart set up (trend -> pullback -> trigger)

No-double-counting rule
-----------------------
Every input is used in exactly ONE place:
  * Volume-based signals live ONLY in Smart Money.
  * Price/oscillator signals live ONLY in Triple Screen.
  * Inside Triple Screen each indicator appears once:
      Screen 1 (trend)   : weekly MACD-hist slope, weekly 26-EMA slope, daily 50-EMA
      Screen 2 (pullback): RSI(14), 20-EMA value zone (ATR-scaled), Fibonacci retracement depth
      Screen 3 (trigger) : prior-high take-out, daily MACD-hist uptick, Heikin-Ashi candle
  * Closing-location value (CLV) is used only in SM 'Closing strength' (and to sign
    block-trade proxy days), never in TS.

Data tiers (best -> fallback). Every component reports which tier it used.
  ticks  : DataFrame [price, size, bid, ask] time-indexed (broker / SGX feed)
  hourly : 60m OHLCV bars (yfinance '.SI' gives ~730 days)
  daily  : daily OHLCV (required)
Missing components are dropped and the remaining weights re-normalised; the result
carries `confidence` = share of the weight that was measured with real (non-proxy) data.

Usage
-----
    res = evaluate("D05.SI", daily, hourly=hourly, ticks=None, equity=100_000)
    print(res["decision"], res["sm"]["score"], res["ts"]["score"], res["plan"])
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- parameters


@dataclass
class Params:
    # Smart Money weights (user-specified)
    w_bidask: float = 35
    w_pricevol: float = 25
    w_block: float = 15
    w_vwap: float = 10
    w_obv: float = 10
    w_close: float = 5
    # Triple Screen weights
    w_s1: float = 40   # trend alignment
    w_s2: float = 35   # pullback quality
    w_s3: float = 25   # entry confirmation
    # Decision thresholds
    ts_buy: float = 70
    sm_buy: float = 65
    bidask_floor: float = 0.5        # bid/ask component must be >= 50% of its weight for BUY
    regime_penalty: float = 10       # thresholds raised by this when STI regime is bearish
    # Gates
    min_value_traded: float = 1_000_000   # S$ 20-day average daily turnover
    min_rr: float = 2.0
    atr_pct_range: tuple = (0.8, 6.0)     # ATR% of price must sit in this band
    max_stop_atr: float = 2.5             # stop wider than this in ATR -> reject
    # Risk (Elder 2% / 6% rules -> we default tighter at 1%)
    risk_pct: float = 1.0
    board_lot: int = 100
    block_min_notional: float = 100_000   # S$ per trade to count as a block (ticks tier)
    pivot_k: int = 3                      # bars each side for a swing high/low to count
    pivot_lookback: int = 250             # ~1 year of resistance history
    min_res_atr: float = 1.0              # ignore resistance closer than this (ATR) above entry
    extra: dict = field(default_factory=dict)


P = Params()

# ---------------------------------------------------------------- helpers


def lin(x, lo, hi):
    """Map x linearly onto 0..1 between lo and hi (clipped)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return float("nan")
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


def band(x, full_lo, full_hi, zero_lo, zero_hi):
    """1 inside [full_lo, full_hi], tapering linearly to 0 at zero_lo / zero_hi."""
    if x is None or math.isnan(x):
        return float("nan")
    if full_lo <= x <= full_hi:
        return 1.0
    if x < full_lo:
        return lin(x, zero_lo, full_lo)
    return 1.0 - lin(x, full_hi, zero_hi)


def sgx_tick(price: float) -> float:
    """SGX minimum bid size for equities."""
    if price < 0.20:
        return 0.001
    if price < 1.00:
        return 0.005
    return 0.01


def round_tick(price: float, up: bool) -> float:
    t = sgx_tick(price)
    n = price / t
    n = math.ceil(n - 1e-9) if up else math.floor(n + 1e-9)
    return round(n * t, 3)


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def macd_hist(close: pd.Series, f=12, s=26, sig=9) -> pd.Series:
    m = ema(close, f) - ema(close, s)
    return m - ema(m, sig)


def rsi(close: pd.Series, n=14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, n=14) -> pd.Series:
    pc = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def clv(df: pd.DataFrame) -> pd.Series:
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    return ((df["Close"] - df["Low"]) / rng).fillna(0.5)


def heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    ha = pd.DataFrame(index=df.index)
    ha["Close"] = df[["Open", "High", "Low", "Close"]].mean(axis=1)
    o = [(df["Open"].iloc[0] + df["Close"].iloc[0]) / 2]
    for i in range(1, len(df)):
        o.append((o[-1] + ha["Close"].iloc[i - 1]) / 2)
    ha["Open"] = o
    ha["High"] = pd.concat([df["High"], ha["Open"], ha["Close"]], axis=1).max(axis=1)
    ha["Low"] = pd.concat([df["Low"], ha["Open"], ha["Close"]], axis=1).min(axis=1)
    return ha


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna()


def lee_ready(ticks: pd.DataFrame) -> pd.Series:
    """+1 buyer-initiated (lifted the offer), -1 seller-initiated (hit the bid)."""
    mid = (ticks["bid"] + ticks["ask"]) / 2
    side = np.where(ticks["price"] >= ticks["ask"], 1,
           np.where(ticks["price"] <= ticks["bid"], -1,
           np.where(ticks["price"] > mid, 1, np.where(ticks["price"] < mid, -1, 0))))
    side = pd.Series(side, index=ticks.index, dtype=float)
    # tick rule for trades exactly at mid
    tick = np.sign(ticks["price"].diff()).replace(0, np.nan).ffill().fillna(0)
    return side.where(side != 0, tick)


def _combine(parts: dict, weights: dict) -> dict:
    """parts: name -> (fraction 0..1 or nan, tier). Re-normalises over measured parts."""
    got = {k: v for k, v in parts.items() if not math.isnan(v[0])}
    wsum = sum(weights[k] for k in got)
    total = sum(weights.values())
    score = 100 * sum(weights[k] * got[k][0] for k in got) / wsum if wsum else float("nan")
    real = sum(weights[k] for k in got if not got[k][1].endswith("proxy"))
    comps = {k: {"pts": round(weights[k] * v[0], 1) if not math.isnan(v[0]) else None,
                 "max": weights[k], "tier": v[1]} for k, v in parts.items()}
    return {"score": round(score, 1), "components": comps,
            "confidence": round(real / total, 2), "weight_measured": round(wsum / total, 2)}


# ---------------------------------------------------------------- SMART MONEY


def sm_bidask(daily, hourly=None, ticks=None):
    """35% - Share of volume that LIFTED THE OFFER (aggressive buyers) over 5 sessions,
    plus improvement vs the 20-session baseline. 'Successful' = buyers paying up."""
    if ticks is not None and len(ticks):
        side = lee_ready(ticks)
        bv = (ticks["size"] * (side > 0)).groupby(ticks.index.normalize()).sum()
        sv = (ticks["size"] * (side < 0)).groupby(ticks.index.normalize()).sum()
        tier = "ticks"
    elif hourly is not None and len(hourly) > 40:
        d = np.sign(hourly["Close"].diff()).replace(0, np.nan).ffill().fillna(0)
        bv = (hourly["Volume"] * (d > 0)).groupby(hourly.index.normalize()).sum()
        sv = (hourly["Volume"] * (d < 0)).groupby(hourly.index.normalize()).sum()
        tier = "hourly-proxy"
    else:
        return float("nan"), "missing"
    r5 = bv.iloc[-5:].sum() / max(bv.iloc[-5:].sum() + sv.iloc[-5:].sum(), 1)
    r20 = bv.iloc[-20:].sum() / max(bv.iloc[-20:].sum() + sv.iloc[-20:].sum(), 1)
    frac = 0.7 * lin(r5, 0.45, 0.62) + 0.3 * lin(r5 - r20, -0.02, 0.08)
    return frac, tier


def sm_pricevol(daily):
    """25% - Up-day volume vs down-day volume over 20 sessions."""
    d = daily.iloc[-21:]
    chg = d["Close"].diff().iloc[1:]
    v = d["Volume"].iloc[1:]
    up, dn = v[chg > 0].sum(), v[chg < 0].sum()
    ratio = up / max(dn, 1)
    return lin(math.log(max(ratio, 1e-6)), math.log(0.8), math.log(1.8)), "daily"


def sm_block(daily, ticks=None, p=P):
    """15% - Net direction of block-sized prints over 10 sessions."""
    if ticks is not None and len(ticks):
        notional = ticks["price"] * ticks["size"]
        thr = max(p.block_min_notional, notional.quantile(0.99))
        side = lee_ready(ticks)
        blk = notional >= thr
        last10 = ticks.index.normalize() >= ticks.index.normalize().unique()[-10:][0]
        b = notional[blk & last10 & (side > 0)].sum()
        s = notional[blk & last10 & (side < 0)].sum()
        if b + s == 0:
            return 0.5, "ticks"
        return lin((b - s) / (b + s), -0.2, 0.6), "ticks"
    # proxy: volume-spike days (>= 2x 50d avg) in last 20 sessions, signed by close & CLV
    avg50 = daily["Volume"].rolling(50).mean()
    d = daily.iloc[-20:]
    spikes = d[d["Volume"] >= 2 * avg50.reindex(d.index)]
    if spikes.empty:
        return 0.5, "daily-proxy"
    c = clv(daily).reindex(spikes.index)
    up = daily["Close"].diff().reindex(spikes.index) > 0
    sign = np.where(up & (c >= 0.5), 1, np.where(~up & (c <= 0.5), -1, 0))
    return lin(sign.mean(), -0.5, 0.75), "daily-proxy"


def sm_vwap(daily):
    """10% - Close vs VWAP anchored at the 60-day low, + slope of rolling 20-day VWAP."""
    d = daily.iloc[-60:]
    tp = (d["High"] + d["Low"] + d["Close"]) / 3
    anchor = d["Low"].idxmin()
    a = d.loc[anchor:]
    tpa = tp.loc[anchor:]
    avwap = (tpa * a["Volume"]).sum() / max(a["Volume"].sum(), 1)
    tpd = (daily["High"] + daily["Low"] + daily["Close"]) / 3
    rv = (tpd * daily["Volume"]).rolling(20).sum() / daily["Volume"].rolling(20).sum()
    slope = (rv.iloc[-1] / rv.iloc[-6] - 1) * 100
    a_ = atr(daily).iloc[-1]
    pos = lin((daily["Close"].iloc[-1] - avwap) / a_, -0.5, 1.0)
    return 0.5 * pos + 0.5 * lin(slope, -1.0, 2.0), "daily"


def sm_obv(daily):
    """10% - OBV 20-day trend (normalised) + where OBV sits in its 60-day range."""
    obv = (np.sign(daily["Close"].diff()).fillna(0) * daily["Volume"]).cumsum()
    y = obv.iloc[-20:].values
    slope = np.polyfit(np.arange(20), y, 1)[0] / max(daily["Volume"].iloc[-20:].mean(), 1)
    w = obv.iloc[-60:]
    pct = (obv.iloc[-1] - w.min()) / max(w.max() - w.min(), 1)
    return 0.7 * lin(slope, -0.1, 0.3) + 0.3 * pct, "daily"


def sm_closing(daily):
    """5% - Average close-location-value of the last 5 sessions (closing near highs)."""
    return lin(clv(daily).iloc[-5:].mean(), 0.3, 0.75), "daily"


def smart_money(daily, hourly=None, ticks=None, p=P):
    parts = {
        "bid_ask": sm_bidask(daily, hourly, ticks),
        "price_volume": sm_pricevol(daily),
        "block_trades": sm_block(daily, ticks, p),
        "vwap": sm_vwap(daily),
        "obv": sm_obv(daily),
        "closing_strength": sm_closing(daily),
    }
    w = {"bid_ask": p.w_bidask, "price_volume": p.w_pricevol, "block_trades": p.w_block,
         "vwap": p.w_vwap, "obv": p.w_obv, "closing_strength": p.w_close}
    return _combine(parts, w)


# ---------------------------------------------------------------- TRIPLE SCREEN


def screen1_trend(daily):
    """Trend alignment (40). Weekly tide + daily 50-EMA wave."""
    wk = to_weekly(daily)
    h = macd_hist(wk["Close"])
    rising = (h.iloc[-1] > h.iloc[-2]) + (h.iloc[-2] > h.iloc[-3])
    f_macd = {0: 0.0, 1: 0.6, 2: 1.0}[int(rising)] if h.iloc[-1] > h.iloc[-2] else 0.0
    e26 = ema(wk["Close"], 26)
    f_e26 = lin((e26.iloc[-1] / e26.iloc[-5] - 1) * 100, -1.0, 3.0)
    e50 = ema(daily["Close"], 50)
    above = daily["Close"].iloc[-1] > e50.iloc[-1]
    up = e50.iloc[-1] > e50.iloc[-6]
    f_e50 = 1.0 if (above and up) else 0.5 if (above or up) else 0.0
    frac = (15 * f_macd + 15 * f_e26 + 10 * f_e50) / 40
    detail = {"wk_macd_hist_rising": bool(h.iloc[-1] > h.iloc[-2]), "wk_ema26_slope_pct": round((e26.iloc[-1] / e26.iloc[-5] - 1) * 100, 2),
              "above_ema50": bool(above), "ema50_rising": bool(up)}
    return frac, detail


def _swing(daily):
    """Last swing high (20d) and the swing low before it (40d window)."""
    hi_idx = daily["High"].iloc[-20:].idxmax()
    pos = daily.index.get_loc(hi_idx)
    pre = daily.iloc[max(0, pos - 40):pos + 1]
    lo = pre["Low"].min()
    after = daily.iloc[pos:]
    pull_low = after["Low"].min()
    return daily["High"].loc[hi_idx], lo, pull_low, pos


def screen2_pullback(daily):
    """Pullback quality (35). RSI dip, 20-EMA value zone, Fib depth."""
    r = rsi(daily["Close"])
    r_min5, r_max20 = r.iloc[-5:].min(), r.iloc[-20:].max()
    f_rsi = band(r_min5, 38, 52, 28, 62) * (1.0 if r_max20 >= 58 else 0.5)
    e20 = ema(daily["Close"], 20)
    a = atr(daily).iloc[-1]
    low3 = daily["Low"].iloc[-3:].min()
    zone = (low3 - e20.iloc[-1]) / a
    f_zone = band(zone, -1.0, 0.5, -2.0, 1.5)
    sh, sl, pl, pos = _swing(daily)
    has_pull = pos < len(daily) - 1 and pl < sh
    retr = (sh - pl) / (sh - sl) if (sh - sl) > 0 and has_pull else float("nan")
    f_fib = band(retr, 0.382, 0.618, 0.20, 0.786) if has_pull else 0.0
    frac = (12 * f_rsi + 12 * f_zone + 11 * f_fib) / 35
    detail = {"rsi_min5": round(r_min5, 1), "rsi_max20": round(r_max20, 1),
              "dist_ema20_atr": round(zone, 2), "fib_retrace": None if math.isnan(retr) else round(retr, 3)}
    return frac, detail


def screen3_trigger(daily):
    """Entry confirmation (25). Take-out of prior high, MACD-hist uptick, HA candle."""
    c, h = daily["Close"], daily["High"]
    f_take = 1.0 if c.iloc[-1] > h.iloc[-2] else 0.4 if c.iloc[-1] > c.iloc[-2] else 0.0
    mh = macd_hist(c)
    up1, up2 = mh.iloc[-1] > mh.iloc[-2], mh.iloc[-2] > mh.iloc[-3]
    f_macd = 1.0 if (up1 and up2) else 0.6 if up1 else 0.0
    ha = heikin_ashi(daily.iloc[-60:])
    green = ha["Close"].iloc[-1] > ha["Open"].iloc[-1]
    no_lower = abs(ha["Low"].iloc[-1] - min(ha["Open"].iloc[-1], ha["Close"].iloc[-1])) < 1e-9
    f_ha = 1.0 if (green and no_lower) else 0.55 if green else 0.0
    frac = (10 * f_take + 8 * f_macd + 7 * f_ha) / 25
    detail = {"close_above_prior_high": bool(c.iloc[-1] > h.iloc[-2]),
              "d_macd_hist_upticks": int(up1) + int(up1 and up2), "ha_green": bool(green), "ha_no_lower_wick": bool(no_lower)}
    return frac, detail


def triple_screen(daily, p=P):
    f1, d1 = screen1_trend(daily)
    f2, d2 = screen2_pullback(daily)
    f3, d3 = screen3_trigger(daily)
    score = p.w_s1 * f1 + p.w_s2 * f2 + p.w_s3 * f3
    return {"score": round(score, 1),
            "components": {"trend_alignment": {"pts": round(p.w_s1 * f1, 1), "max": p.w_s1, **d1},
                           "pullback_quality": {"pts": round(p.w_s2 * f2, 1), "max": p.w_s2, **d2},
                           "entry_confirmation": {"pts": round(p.w_s3 * f3, 1), "max": p.w_s3, **d3}}}


# ---------------------------------------------------------------- LEVELS & PLAN


def pivots(daily, lookback=250, k=3):
    """Swing highs/lows: bar is the max/min of the k bars either side (vectorised)."""
    h = daily["High"].values[-lookback:]
    l = daily["Low"].values[-lookback:]
    if len(h) < 2 * k + 1:
        return [], []
    from numpy.lib.stride_tricks import sliding_window_view as swv
    wh, wl = swv(h, 2 * k + 1), swv(l, 2 * k + 1)
    hs = h[k:-k][h[k:-k] == wh.max(axis=1)]
    ls = l[k:-k][l[k:-k] == wl.min(axis=1)]
    return sorted(set(map(float, hs))), sorted(set(map(float, ls)))


def cluster(levels, tol):
    out = []
    for lv in sorted(levels):
        if out and lv - out[-1][-1] <= tol:
            out[-1].append(lv)
        else:
            out.append([lv])
    return [round(float(np.mean(c)), 3) for c in out]


def trade_plan(daily, p=P, equity=None):
    a = atr(daily).iloc[-1]
    last = daily.iloc[-1]
    entry = round_tick(last["High"] + sgx_tick(last["High"]), up=True)          # buy-stop above today's high
    pull_low = daily["Low"].iloc[-5:].min()
    stop = round_tick(pull_low - sgx_tick(pull_low), up=False)
    stop_atr = (entry - stop) / a
    hs, ls = pivots(daily, p.pivot_lookback, p.pivot_k)
    yr_high = float(daily["High"].iloc[-250:].max())
    res = [r for r in cluster(hs + [yr_high], 0.75 * a) if r >= entry + p.min_res_atr * a]
    sup = [s for s in cluster(ls, 0.75 * a) if s < entry]
    risk = entry - stop
    t1 = round_tick(res[0] - sgx_tick(res[0]), up=False) if res else round_tick(entry + 2 * risk, up=False)
    t2 = round_tick(res[1] - sgx_tick(res[1]), up=False) if len(res) > 1 else round_tick(entry + 3 * risk, up=False)
    rr = (t1 - entry) / risk if risk > 0 else 0
    plan = {"entry_buy_stop": entry, "stop": stop, "risk_per_share": round(risk, 3),
            "stop_in_atr": round(stop_atr, 2), "target1": t1, "target2": t2, "rr_t1": round(rr, 2),
            "supports": sup[-3:], "resistances": res[:3], "atr": round(a, 4),
            "management": ["Order valid 2 sessions; cancel if not filled",
                           "At +1R: move stop to breakeven",
                           "At T1: sell half; trail rest under 20-EMA or 2-bar low",
                           "Time stop: exit if < +0.5R after 7 sessions"]}
    if equity and risk > 0:
        sh = math.floor(equity * p.risk_pct / 100 / risk / p.board_lot) * p.board_lot
        plan["shares"] = int(sh)
        plan["capital"] = round(sh * entry, 2)
    return plan


# ---------------------------------------------------------------- GATES & DECISION


def gates(daily, plan, p=P, sti_daily=None, days_to_event=None):
    a_pct = plan["atr"] / daily["Close"].iloc[-1] * 100
    val = (daily["Close"] * daily["Volume"]).iloc[-20:].mean()
    g = {
        "liquidity": (val >= p.min_value_traded, f"S${val/1e6:.2f}M/day"),
        "reward_risk": (plan["rr_t1"] >= p.min_rr, f"{plan['rr_t1']}R to T1"),
        "atr_band": (p.atr_pct_range[0] <= a_pct <= p.atr_pct_range[1], f"ATR {a_pct:.2f}%"),
        "stop_width": (plan["stop_in_atr"] <= p.max_stop_atr, f"{plan['stop_in_atr']} ATR"),
    }
    if days_to_event is not None:   # results / ex-div within 5 sessions -> stand aside
        g["no_event_5d"] = (days_to_event > 5, f"{days_to_event} sessions to event")
    regime_bear = False
    if sti_daily is not None and len(sti_daily) > 60:
        e = ema(sti_daily["Close"], 50)
        regime_bear = bool(sti_daily["Close"].iloc[-1] < e.iloc[-1] and e.iloc[-1] < e.iloc[-6])
    return g, regime_bear


def evaluate(symbol, daily, hourly=None, ticks=None, sti_daily=None, equity=None,
             days_to_event=None, p=P):
    daily = daily.dropna().copy()
    if len(daily) < 200:
        return {"symbol": symbol, "decision": "INSUFFICIENT_DATA"}
    sm = smart_money(daily, hourly, ticks, p)
    ts = triple_screen(daily, p)
    plan = trade_plan(daily, p, equity)
    g, bear = gates(daily, plan, p, sti_daily, days_to_event)
    bump = p.regime_penalty if bear else 0
    ts_ok = ts["score"] >= p.ts_buy + bump
    sm_ok = sm["score"] >= p.sm_buy + bump
    ba = sm["components"]["bid_ask"]["pts"]
    ba_ok = ba is not None and ba >= p.bidask_floor * p.w_bidask
    gates_ok = all(v[0] for v in g.values())
    if gates_ok and ts_ok and sm_ok and ba_ok:
        decision = "BUY"
    elif ts["score"] >= p.ts_buy - 10 and sm["score"] >= p.sm_buy - 15:
        decision = "WATCH"
    else:
        decision = "AVOID"
    reasons = [k for k, v in g.items() if not v[0]]
    if not ts_ok: reasons.append(f"TS<{p.ts_buy + bump}")
    if not sm_ok: reasons.append(f"SM<{p.sm_buy + bump}")
    if not ba_ok: reasons.append("bid/ask below floor")
    return {"symbol": symbol, "date": str(daily.index[-1].date()), "close": float(daily["Close"].iloc[-1]),
            "decision": decision, "blocked_by": reasons, "regime_bearish": bear,
            "combined": round(0.5 * sm["score"] + 0.5 * ts["score"], 1),
            "sm": sm, "ts": ts, "gates": {k: {"pass": bool(v[0]), "value": v[1]} for k, v in g.items()},
            "plan": plan}


if __name__ == "__main__":  # quick demo with yfinance
    import json
    import sys
    import yfinance as yf
    sym = sys.argv[1] if len(sys.argv) > 1 else "D05.SI"
    d = yf.download(sym, period="2y", interval="1d", auto_adjust=False, progress=False)
    h = yf.download(sym, period="60d", interval="60m", auto_adjust=False, progress=False)
    sti = yf.download("^STI", period="2y", interval="1d", progress=False)
    for x in (d, h, sti):
        if isinstance(x.columns, pd.MultiIndex):
            x.columns = x.columns.get_level_values(0)
    print(json.dumps(evaluate(sym, d, hourly=h, sti_daily=sti, equity=100_000), indent=2, default=str))
