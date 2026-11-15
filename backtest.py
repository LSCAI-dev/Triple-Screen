"""Walk-forward backtest of the SGX dual-score system - compares spec versions.

    python backtest.py                       -> v1.1, v1.2 and v1.2-swingstop, all tickers
    python backtest.py --version v1.2        -> one version
    python backtest.py --version v1.2 D05.SI -> one version, one ticker

Versions (see scoring.Params): v1.1 = original spec; v1.2 = Elder refinements (weekly
Impulse veto, Bear Power, 13-26 EMA value zone, SafeZone stop, autoenvelope T2, no
Heikin-Ashi); v1.2-swingstop = v1.2 but with the old 5-day-low stop, to isolate SafeZone.
Elder's 6% rule is applied at portfolio level (each open trade = 1% risk; no new fill if
open risk + this month's net loss + 1% > 6%).

Phase 1 scores every stock on every day (cached in backtest\\signals.csv, slow the first time).
Phase 2 simulates trades for a grid of thresholds and reports win rate / expectancy.

IMPORTANT limits
  * Yahoo hourly data only goes back ~2 years, so the 35% bid/ask component cannot be
    measured historically. Smart Money is re-weighted over the other 65% and the bid/ask
    floor is skipped. The live scanner still requires it.
  * Uses today's STI list for all years (survivorship bias -> results look a bit better than reality).
  * Thresholds are judged on 2018-2022 (in-sample); 2023-today is the out-of-sample check.
"""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

try:                                   # local folder: scoring.py
    import scoring as sc
except ImportError:                    # GitHub repo: sgx_ts/dualscore.py
    from sgx_ts import dualscore as sc

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "backtest")
START = "2016-06-01"          # history needed before the first 2018 signal
TEST_FROM = "2018-01-01"
OOS_FROM = "2023-01-01"
COST = 0.0025                 # round-trip cost: commission + fees + slippage (0.25%)
WINDOW = 300                  # bars passed to the scorer each day
MAX_HOLD = 30
RISK_PCT, MONTH_CAP_PCT = 1.0, 6.0    # Elder 2%/6% rules (we risk 1% per trade)
VERSIONS = {"v1.1": lambda: sc.Params.v11(),
            "v1.2": lambda: sc.Params(),
            "v1.2-swingstop": lambda: sc.Params(stop_method="swing5", version="1.2-swingstop")}


def parse_args():
    args, versions = [], list(VERSIONS)
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--version":
            v = next(it)
            versions = list(VERSIONS) if v == "all" else [v]
        else:
            args.append(a)
    bad = [v for v in versions if v not in VERSIONS]
    if bad:
        sys.exit(f"Unknown version {bad}; choose from {list(VERSIONS)} or all")
    return args, versions


def flat(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


def tickers(args):
    if args:
        return [t.upper() for t in args]
    path = os.path.join(HERE, "tickers.txt")
    if os.path.exists(path):
        with open(path) as f:
            return [l.strip() for l in f if l.strip() and not l.startswith("#")]
    import config                      # GitHub repo
    return list(config.UNIVERSE)


# ---------------------------------------------------------------- phase 1: daily scores
def score_history(sym, d, sti, p=sc.P):
    rows = []
    start_i = max(WINDOW, d.index.searchsorted(pd.Timestamp(TEST_FROM)))
    for i in range(start_i, len(d) - 1):
        w = d.iloc[i - WINDOW + 1:i + 1]
        dt = w.index[-1]
        try:
            sm = sc.smart_money(w, None, None, p)
            ts = sc.triple_screen(w, p)
            plan = sc.trade_plan(w, p)
            g, bear = sc.gates(w, plan, p, sti.loc[:dt] if sti is not None else None)
        except Exception:
            continue
        rows.append({"ticker": sym, "date": dt, "SM": sm["score"], "TS": ts["score"],
                     "bear": bear, "gates_ok": all(v[0] for v in g.values()),
                     "entry": plan["entry_buy_stop"], "stop": plan["stop"],
                     "t1": plan["target1"], "rr": plan["rr_t1"]})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- phase 2: trade simulation
def simulate(sig, prices, ts_min, sm_min, bump=10):
    """One position per ticker. Returns list of trades with result in R."""
    trades = []
    for sym, s in sig.groupby("ticker"):
        d = prices[sym]
        e20 = sc.ema(d["Close"], 20)
        idx = {dt: i for i, dt in enumerate(d.index)}
        busy_until = None
        for _, r in s.iterrows():
            if busy_until is not None and r["date"] <= busy_until:
                continue
            b = bump if r["bear"] else 0
            if not (r["gates_ok"] and r["TS"] >= ts_min + b and r["SM"] >= sm_min + b):
                continue
            i = idx[r["date"]]
            entry, stop, t1 = r["entry"], r["stop"], r["t1"]
            risk = entry - stop
            if risk <= 0:
                continue
            # buy-stop valid 2 sessions
            fill_i, fill = None, None
            for j in (i + 1, i + 2):
                if j < len(d) and d["High"].iloc[j] >= entry:
                    fill_i, fill = j, max(entry, d["Open"].iloc[j])
                    break
            if fill_i is None:
                continue
            cur_stop, half_done, realised, exit_i = stop, False, 0.0, None
            for k in range(fill_i, min(fill_i + MAX_HOLD, len(d))):
                o, h, l, c = d["Open"].iloc[k], d["High"].iloc[k], d["Low"].iloc[k], d["Close"].iloc[k]
                if l <= cur_stop:                                  # stop first (conservative)
                    px = min(cur_stop, o)
                    realised += (0.5 if half_done else 1.0) * (px - fill) / risk
                    exit_i = k
                    break
                if not half_done and h >= t1:                      # sell half at T1
                    realised += 0.5 * (max(t1, o) - fill) / risk
                    half_done = True
                    cur_stop = max(cur_stop, fill)
                if h >= fill + risk:                               # +1R -> breakeven
                    cur_stop = max(cur_stop, fill)
                if half_done and c < e20.iloc[k]:                  # trail rest under 20-EMA
                    realised += 0.5 * (c - fill) / risk
                    exit_i = k
                    break
                if not half_done and k - fill_i >= 7 and c < fill + 0.5 * risk:   # time stop
                    realised += (c - fill) / risk
                    exit_i = k
                    break
            if exit_i is None:                                     # max hold reached
                exit_i = min(fill_i + MAX_HOLD, len(d)) - 1
                realised += (0.5 if half_done else 1.0) * (d["Close"].iloc[exit_i] - fill) / risk
            realised -= COST * fill / risk
            trades.append({"ticker": sym, "signal": r["date"], "fill_date": d.index[fill_i],
                           "exit_date": d.index[exit_i], "fill": round(fill, 3), "R": round(realised, 3),
                           "TS": r["TS"], "SM": r["SM"], "days": exit_i - fill_i + 1})
            busy_until = d.index[exit_i]
    return pd.DataFrame(trades)


def six_percent(t, cap=MONTH_CAP_PCT, risk=RISK_PCT):
    """Elder 6% rule across the whole portfolio, in fill order."""
    if t.empty:
        return t
    t = t.sort_values("fill_date").reset_index(drop=True)
    keep = []
    for k, r in t.iterrows():
        acc = t.loc[keep]
        open_n = int(((acc["fill_date"] <= r["fill_date"]) & (acc["exit_date"] >= r["fill_date"])).sum())
        m0 = r["fill_date"].to_period("M").start_time
        closed = acc[(acc["exit_date"] >= m0) & (acc["exit_date"] < r["fill_date"])]
        month_loss = max(0.0, -closed["R"].sum() * risk)
        if open_n * risk + month_loss + risk <= cap:
            keep.append(k)
    return t.loc[keep].reset_index(drop=True)


def trades(sig, prices, ts_min, sm_min):
    return six_percent(simulate(sig, prices, ts_min, sm_min))


def stats(t):
    if t.empty:
        return {"trades": 0}
    r = t["R"]
    eq = r.cumsum()
    loss = -r[r <= 0].sum()
    out = {"trades": len(t), "win_rate_%": (r > 0).mean() * 100,
           "avg_R": r.mean(), "avg_win_R": r[r > 0].mean() if (r > 0).any() else 0,
           "avg_loss_R": r[r <= 0].mean() if (r <= 0).any() else 0,
           "profit_factor": r[r > 0].sum() / loss if loss > 0 else None,
           "max_drawdown_R": (eq - eq.cummax()).min(), "total_R": r.sum(),
           "avg_days": t["days"].mean()}
    return {k: (round(float(v), 2) if isinstance(v, (float, np.floating)) else v) for k, v in out.items()}


def run_version(v, syms, sti, prices):
    p = VERSIONS[v]()
    cache = os.path.join(OUT, f"signals_{v}.csv")
    legacy = os.path.join(OUT, "signals.csv")          # pre-v1.2 cache = v1.1 scores
    if v == "v1.1" and not os.path.exists(cache) and os.path.exists(legacy):
        cache_src = legacy
    else:
        cache_src = cache
    cached = pd.read_csv(cache_src, parse_dates=["date"]) if os.path.exists(cache_src) else pd.DataFrame()
    frames = []
    for n, sym in enumerate(syms, 1):
        if sym not in prices:
            continue
        d = prices[sym]
        have = cached[cached["ticker"] == sym] if not cached.empty else pd.DataFrame()
        if not have.empty and have["date"].max() >= d.index[-2] - pd.Timedelta(days=5):
            print(f"  [{v} {n}/{len(syms)}] {sym}: cached")
            frames.append(have)
            continue
        print(f"  [{v} {n}/{len(syms)}] {sym}: scoring {len(d)} days ...", flush=True)
        frames.append(score_history(sym, d, sti, p))
    sig = pd.concat(frames, ignore_index=True)
    sig.to_csv(cache, index=False)

    grid = []
    for ts_min in (60, 65, 70, 75, 80):
        for sm_min in (50, 55, 60, 65, 70):
            t = trades(sig, prices, ts_min, sm_min)
            if t.empty:
                continue
            ins = t[t["signal"] < OOS_FROM]
            oos = t[t["signal"] >= OOS_FROM]
            a, b = stats(ins), stats(oos)
            grid.append({"TS_min": ts_min, "SM_min": sm_min,
                         "IS_trades": a.get("trades", 0), "IS_win%": a.get("win_rate_%"), "IS_avgR": a.get("avg_R"),
                         "IS_PF": a.get("profit_factor"),
                         "OOS_trades": b.get("trades", 0), "OOS_win%": b.get("win_rate_%"), "OOS_avgR": b.get("avg_R"),
                         "OOS_PF": b.get("profit_factor"), "OOS_maxDD_R": b.get("max_drawdown_R")})
    g = pd.DataFrame(grid)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    g.to_csv(os.path.join(OUT, f"grid_{v}_{stamp}.csv"), index=False)

    # pick best in-sample combo with >= 30 trades, then show its untouched out-of-sample result
    ok = g[g["IS_trades"] >= 30].sort_values("IS_avgR", ascending=False) if not g.empty else g
    pd.set_option("display.width", 200)
    print(f"\n[{v}] Threshold grid (IS = 2018-2022, OOS = 2023-today, 6% rule on):")
    print(g.to_string(index=False) if not g.empty else "  no trades")
    summary = []
    cells = [("current 70/65", (70, 65))]
    if not ok.empty:
        cells.append(("best IS %d/%d" % (ok.iloc[0]["TS_min"], ok.iloc[0]["SM_min"]),
                      (ok.iloc[0]["TS_min"], ok.iloc[0]["SM_min"])))
    for label, (ts_min, sm_min) in cells:
        t = trades(sig, prices, ts_min, sm_min)
        t.to_csv(os.path.join(OUT, f"trades_{v}_{int(ts_min)}_{int(sm_min)}_{stamp}.csv"), index=False)
        print(f"\n== {v} {label} ==")
        parts = [("IS 2018-22", t[t["signal"] < OOS_FROM] if not t.empty else t),
                 ("OOS 2023+", t[t["signal"] >= OOS_FROM] if not t.empty else t), ("All", t)]
        for name, part in parts:
            st = stats(part)
            print(f"  {name:12s} {st}")
            summary.append({"version": v, "cell": label, "period": name, **st})
        if not t.empty:
            t["year"] = pd.to_datetime(t["signal"]).dt.year
            print("  By year:", t.groupby("year")["R"].agg(["count", "mean"]).round(2).to_dict("index"))
    return summary


def main():
    os.makedirs(OUT, exist_ok=True)
    args, versions = parse_args()
    syms = tickers(args)
    sti = flat(yf.download("^STI", start=START, progress=False))
    prices = {}
    for n, sym in enumerate(syms, 1):
        d = flat(yf.download(sym, start=START, auto_adjust=True, progress=False))
        if len(d) < WINDOW + 50:
            print(f"[{n}/{len(syms)}] {sym}: not enough data, skipped")
            continue
        prices[sym] = d
    allsum = []
    for v in versions:
        allsum += run_version(v, syms, sti, prices)
    comp = pd.DataFrame(allsum)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    comp.to_csv(os.path.join(OUT, f"compare_{stamp}.csv"), index=False)
    cols = [c for c in ["version", "cell", "trades", "win_rate_%", "avg_R", "profit_factor", "max_drawdown_R", "total_R"]
            if c in comp.columns]
    print("\n==== VERSION COMPARISON - out-of-sample 2023-today (judge on this) ====")
    print(comp[comp["period"] == "OOS 2023+"][cols].to_string(index=False))
    print("Under ~30 OOS trades, differences between versions are mostly noise.")
    print(f"\nSaved to backtest\\ (compare_{stamp}.csv, grid_*.csv, trades_*.csv). "
          f"Source: Yahoo Finance daily, adjusted, as of {max(d.index[-1] for d in prices.values()).date()}.")


if __name__ == "__main__":
    main()
