"""Elder Triple Screen.

Screen 1  Weekly tide   : slope of weekly MACD histogram, confirmed by 26-wk EMA.
Screen 2  Daily wave    : trade against the tide - pullbacks in an up-tide
                          (Force Index(2) < 0 or RSI low), rallies in a down-tide.
Screen 3  Entry         : trailing buy-stop one tick above the prior day's high
                          (sell-stop below the low for shorts), stop beyond the
                          recent swing, targets at resistance / support and 2R.
"""
import math
import pandas as pd

import config as C
from .indicators import ema, macd, rsi, atr, force_index, to_weekly, tick, to_tick
from .levels import find_levels

SETUP_LONG, WATCH_LONG = "Long setup", "Long watch"
SETUP_SHORT, WATCH_SHORT = "Short setup", "Short watch"
NO_TRADE = "No trade"
STATUS_ORDER = {SETUP_LONG: 0, SETUP_SHORT: 1, WATCH_LONG: 2, WATCH_SHORT: 3, NO_TRADE: 4}


def enrich_daily(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["EMA20"] = ema(d["Close"], C.D_EMA_FAST)
    d["EMA50"] = ema(d["Close"], C.D_EMA_SLOW)
    d["MACD"], d["MACDsig"], d["MACDhist"] = macd(d["Close"], C.MACD_FAST, C.MACD_SLOW, C.MACD_SIGNAL)
    d["RSI"] = rsi(d["Close"], C.RSI_LEN)
    d["ATR"] = atr(d, C.ATR_LEN)
    d["FI2"] = force_index(d, C.FORCE_LEN)
    return d


def enrich_weekly(df: pd.DataFrame) -> pd.DataFrame:
    w = to_weekly(df)
    w["EMA13"] = ema(w["Close"], C.W_EMA_FAST)
    w["EMA26"] = ema(w["Close"], C.W_EMA_SLOW)
    w["MACD"], w["MACDsig"], w["MACDhist"] = macd(w["Close"], C.MACD_FAST, C.MACD_SLOW, C.MACD_SIGNAL)
    return w


def weekly_tide(w: pd.DataFrame) -> dict:
    h_up = w["MACDhist"].iloc[-1] > w["MACDhist"].iloc[-2]
    e_up = w["EMA26"].iloc[-1] > w["EMA26"].iloc[-2]
    above = w["Close"].iloc[-1] > w["EMA26"].iloc[-1]
    if h_up and (e_up or above):
        tide = "Up"
    elif (not h_up) and ((not e_up) or (not above)):
        tide = "Down"
    else:
        tide = "Mixed"
    # Elder impulse colour on the weekly bar
    e13_up = w["EMA13"].iloc[-1] > w["EMA13"].iloc[-2]
    impulse = "green" if (e13_up and h_up) else "red" if (not e13_up and not h_up) else "blue"
    return {"tide": tide, "hist_rising": bool(h_up), "ema26_rising": bool(e_up),
            "above_ema26": bool(above), "impulse": impulse,
            "strong": bool(h_up == e_up)}


def _shares(entry, stop):
    risk_cash = C.ACCOUNT_SIZE_SGD * C.RISK_PER_TRADE_PCT / 100
    per_share = abs(entry - stop)
    if per_share <= 0:
        return 0, 0.0
    lots = math.floor(risk_cash / per_share / C.BOARD_LOT)
    qty = lots * C.BOARD_LOT
    return qty, round(qty * per_share, 2)


def _plan_long(d, sup, res, a):
    hi1 = float(d["High"].iloc[-1])
    entry = to_tick(hi1 + tick(hi1), "up")
    swing_low = float(d["Low"].iloc[-2:].min())
    stop = to_tick(min(swing_low - tick(swing_low), entry - C.MIN_STOP_ATR * a), "down")
    r = entry - stop
    above = [l["price"] for l in res if l["price"] > entry + 0.25 * a]
    t1 = to_tick(above[0] if above else entry + 2 * r, "down")
    t2 = to_tick(max(above[1] if len(above) > 1 else 0, entry + 2 * r), "down")
    if t2 <= t1:
        t2 = to_tick(t1 + r, "down")
    return entry, stop, t1, t2


def _plan_short(d, sup, res, a):
    lo1 = float(d["Low"].iloc[-1])
    entry = to_tick(lo1 - tick(lo1), "down")
    swing_hi = float(d["High"].iloc[-2:].max())
    stop = to_tick(max(swing_hi + tick(swing_hi), entry + C.MIN_STOP_ATR * a), "up")
    r = stop - entry
    below = [l["price"] for l in sup if l["price"] < entry - 0.25 * a]
    t1 = to_tick(below[0] if below else entry - 2 * r, "up")
    t2 = to_tick(min(below[1] if len(below) > 1 else 1e9, entry - 2 * r), "up")
    if t2 >= t1:
        t2 = to_tick(t1 - r, "up")
    return entry, stop, t1, max(t2, tick(entry))


def analyse(ticker: str, name: str, raw: pd.DataFrame) -> dict:
    d = enrich_daily(raw)
    w = enrich_weekly(raw)
    last = d.iloc[-1]
    close, a = float(last["Close"]), float(last["ATR"])
    s1 = weekly_tide(w)
    sup, res = find_levels(d, a, C.SR_LOOKBACK, C.SR_PIVOT_WINDOW, C.SR_CLUSTER_ATR, C.SR_LEVELS_EACH_SIDE)

    fi2, r14 = float(last["FI2"]), float(last["RSI"])
    hist_turn_up = d["MACDhist"].iloc[-1] > d["MACDhist"].iloc[-2]
    hist_turn_dn = not hist_turn_up
    ema20, ema50 = float(last["EMA20"]), float(last["EMA50"])
    touched_vz_long = float(last["Low"]) <= ema20 * 1.005
    touched_vz_short = float(last["High"]) >= ema20 * 0.995
    extended_up = close > ema20 + C.EXTENDED_ATR * a
    extended_dn = close < ema20 - C.EXTENDED_ATR * a

    status, wave, notes = NO_TRADE, "-", []
    if s1["tide"] == "Up":
        pullback = fi2 < 0 or r14 <= C.RSI_PULLBACK_LONG or touched_vz_long
        intact = close >= ema50 * 0.97
        wave = "Extended" if extended_up else ("Pullback" if pullback else "Rising")
        if pullback and intact and not extended_up:
            status = SETUP_LONG
        else:
            status = WATCH_LONG
            if not intact:
                notes.append("Close is >3% under EMA50: daily structure broken")
            elif extended_up:
                notes.append("Extended above EMA20: wait for a pullback")
            else:
                notes.append("Wait for Force Index(2) < 0 or RSI <= %d" % C.RSI_PULLBACK_LONG)
    elif s1["tide"] == "Down" and C.ALLOW_SHORTS:
        rally = fi2 > 0 or r14 >= C.RSI_RALLY_SHORT or touched_vz_short
        intact = close <= ema50 * 1.03
        wave = "Extended" if extended_dn else ("Rally" if rally else "Falling")
        if rally and intact and not extended_dn:
            status = SETUP_SHORT
        else:
            status = WATCH_SHORT
            if not intact:
                notes.append("Close is >3% over EMA50: daily structure broken")
            elif extended_dn:
                notes.append("Extended below EMA20: wait for a rally")
            else:
                notes.append("Wait for Force Index(2) > 0 or RSI >= %d" % C.RSI_RALLY_SHORT)
    else:
        notes.append("Weekly tide is mixed: stand aside")

    plan = None
    if status in (SETUP_LONG, SETUP_SHORT):
        long = status == SETUP_LONG
        entry, stop, t1, t2 = (_plan_long if long else _plan_short)(d, sup, res, a)
        risk = abs(entry - stop)
        rr1 = abs(t1 - entry) / risk if risk else 0
        rr2 = abs(t2 - entry) / risk if risk else 0
        qty, cash_risk = _shares(entry, stop)
        points = sum([
            (touched_vz_long if long else touched_vz_short),
            (hist_turn_up if long else hist_turn_dn),
            rr1 >= 2,
            s1["strong"],
        ])
        grade = "A" if points >= 3 and rr1 >= 1.5 else "B" if points >= 2 and rr1 >= 1.2 else "C"
        plan = {
            "side": "Long" if long else "Short",
            "order": ("Buy stop" if long else "Sell stop") + f" {entry:.3f}, valid {C.ORDER_VALID_SESSIONS} sessions; "
                     "trail it to 1 tick beyond each new day's " + ("high" if long else "low") + " if not filled",
            "entry": entry, "stop": stop, "t1": t1, "t2": t2,
            "risk_per_share": round(risk, 3), "rr1": round(rr1, 2), "rr2": round(rr2, 2),
            "qty": qty, "cash_risk": cash_risk, "grade": grade,
            "stop_pct": round(risk / entry * 100, 2),
        }
        if rr1 < C.MIN_RR_T1:
            notes.append(f"Passed screens 1-2 but T1 ({t1:.3f}) is only {rr1:.1f}R away: "
                         "resistance too close, no trade")
            status, plan = (WATCH_LONG if long else WATCH_SHORT), None
        elif rr1 < 1.5:
            notes.append("Reward:risk to T1 below 1.5 - consider skipping")

    return {
        "ticker": ticker, "code": ticker.replace(".SI", ""), "name": name,
        "date": d.index[-1].strftime("%Y-%m-%d"),
        "close": round(close, 3), "chg_pct": round((close / float(d["Close"].iloc[-2]) - 1) * 100, 2),
        "status": status, "wave": wave, "tide": s1,
        "ema20": round(ema20, 3), "ema50": round(ema50, 3),
        "rsi": round(r14, 1), "fi2": round(fi2, 0), "atr": round(a, 3),
        "macd": round(float(last["MACD"]), 4), "macd_hist": round(float(last["MACDhist"]), 4),
        "macd_hist_rising": bool(hist_turn_up),
        "support": sup, "resistance": res, "plan": plan, "notes": notes,
        "_daily": d, "_weekly": w,
    }


def sort_key(r):
    g = {"A": 0, "B": 1, "C": 2}.get((r.get("plan") or {}).get("grade"), 3)
    rr = -((r.get("plan") or {}).get("rr1") or 0)
    return (STATUS_ORDER[r["status"]], g, rr, r["code"])
