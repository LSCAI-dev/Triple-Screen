"""Saved results: one JSON per run, a cumulative CSV log, daily OHLCV snapshots,
and outcome tracking for both the classic setups and the dual-score plans."""
import json
import math
from pathlib import Path
import pandas as pd

import config as C
from .screens import SETUP_LONG, SETUP_SHORT

LOG_COLS = ["date", "ticker", "code", "name", "status", "grade", "close", "entry", "stop",
            "t1", "t2", "rr1", "rsi", "tide", "wave", "dual", "sm", "ts",
            "d_entry", "d_stop", "d_t1", "d_t2", "d_rr", "d_qty", "d_version"]
DUAL_COST = 0.0025          # round-trip cost charged on dual-score replays (same as backtest)


def public(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


def save_run(out_dir: Path, meta: dict, results: list):
    runs = out_dir / "data" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "results": [public(r) for r in results]}
    (runs / f"{meta['as_of']}.json").write_text(json.dumps(payload, indent=1))
    (out_dir / "data" / "latest.json").write_text(json.dumps(payload, indent=1))
    dates = sorted((p.stem for p in runs.glob("????-??-??.json")), reverse=True)
    (runs / "index.json").write_text(json.dumps(dates))

    rows = []
    for r in results:
        p = r.get("plan") or {}
        dl = r.get("dual") or {}
        dp = dl.get("plan") or {}
        rows.append({"date": meta["as_of"], "ticker": r["ticker"], "code": r["code"], "name": r["name"],
                     "status": r["status"], "grade": p.get("grade", ""), "close": r["close"],
                     "entry": p.get("entry", ""), "stop": p.get("stop", ""), "t1": p.get("t1", ""),
                     "t2": p.get("t2", ""), "rr1": p.get("rr1", ""), "rsi": r["rsi"],
                     "tide": r["tide"]["tide"], "wave": r["wave"],
                     "dual": (r.get("dual") or {}).get("decision", ""),
                     "sm": ((r.get("dual") or {}).get("sm") or {}).get("score", ""),
                     "ts": ((r.get("dual") or {}).get("ts") or {}).get("score", ""),
                     "d_entry": dp.get("entry_buy_stop", ""), "d_stop": dp.get("stop", ""),
                     "d_t1": dp.get("target1", ""), "d_t2": dp.get("target2", ""),
                     "d_rr": dp.get("rr_t1", ""), "d_qty": dp.get("shares", ""),
                     "d_version": dl.get("version", "1.1") if dl else ""})
    log = out_dir / "data" / "signals_log.csv"
    new = pd.DataFrame(rows, columns=LOG_COLS)
    if log.exists():
        old = pd.read_csv(log, dtype=str).reindex(columns=LOG_COLS)
        old = old[old["date"] != meta["as_of"]]          # re-runs replace the same day
        new = pd.concat([old, new.astype(str)], ignore_index=True)
    new.sort_values(["date", "code"]).to_csv(log, index=False)
    return log


def evaluate(out_dir: Path, prices: dict):
    """Replay every logged setup against later bars: not filled / open / T1 hit / stopped."""
    log = out_dir / "data" / "signals_log.csv"
    if not log.exists():
        return {"rows": [], "summary": {}}
    df = pd.read_csv(log)
    df = df[df["status"].isin([SETUP_LONG, SETUP_SHORT])]
    rows = []
    for _, s in df.iterrows():
        px = prices.get(s["ticker"])
        if px is None:
            continue
        after = px[px.index > pd.Timestamp(s["date"])]
        long = s["status"] == SETUP_LONG
        entry, stop, t1 = float(s["entry"]), float(s["stop"]), float(s["t1"])
        outcome, fill_date, exit_date, r_mult = "Pending", "", "", None
        window = after.head(C.ORDER_VALID_SESSIONS)
        hit = window[window["High"] >= entry] if long else window[window["Low"] <= entry]
        if hit.empty:
            outcome = "Not filled" if len(window) >= C.ORDER_VALID_SESSIONS else "Pending"
        else:
            fill = hit.index[0]
            fill_date = fill.strftime("%Y-%m-%d")
            outcome = "Open"
            risk = abs(entry - stop)
            for dt, b in after[after.index >= fill].iterrows():
                stopped = b["Low"] <= stop if long else b["High"] >= stop
                won = b["High"] >= t1 if long else b["Low"] <= t1
                if stopped:          # same-bar ambiguity resolved conservatively
                    outcome, exit_date, r_mult = "Stopped", dt.strftime("%Y-%m-%d"), -1.0
                    break
                if won:
                    outcome, exit_date = "T1 hit", dt.strftime("%Y-%m-%d")
                    r_mult = round(abs(t1 - entry) / risk, 2) if risk else 0
                    break
            if outcome == "Open":
                last = float(after["Close"].iloc[-1])
                r_mult = round(((last - entry) if long else (entry - last)) / risk, 2) if risk else 0
        rows.append({"date": s["date"], "code": s["code"], "name": s["name"], "side": "Long" if long else "Short",
                     "grade": s["grade"], "entry": entry, "stop": stop, "t1": t1, "outcome": outcome,
                     "filled": fill_date, "closed": exit_date, "r": r_mult})
    closed = [r for r in rows if r["outcome"] in ("T1 hit", "Stopped")]
    wins = [r for r in closed if r["outcome"] == "T1 hit"]
    summary = {
        "signals": len(rows), "filled": sum(1 for r in rows if r["filled"]),
        "closed": len(closed), "wins": len(wins),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
        "expectancy_r": round(sum(r["r"] for r in closed) / len(closed), 2) if closed else None,
    }
    res = {"rows": sorted(rows, key=lambda r: r["date"], reverse=True), "summary": summary}
    (out_dir / "data" / "outcomes.json").write_text(json.dumps(res, indent=1))
    return res


# ------------------------------------------------------------------ daily price snapshots

def save_prices(out_dir: Path, prices: dict, names: dict | None = None):
    """docs/data/prices/YYYY-MM-DD.csv: one OHLCV row per stock (+ STI) for each run date.
    Missing past run dates are back-filled from the history just downloaded."""
    pdir = out_dir / "data" / "prices"
    pdir.mkdir(parents=True, exist_ok=True)
    runs = out_dir / "data" / "runs"
    dates = sorted(p.stem for p in runs.glob("????-??-??.json"))
    have = {p.stem for p in pdir.glob("????-??-??.csv")}
    latest = max((df.index[-1] for df in prices.values()), default=None)
    todo = [d for d in dates if d not in have]
    if latest is not None and latest.strftime("%Y-%m-%d") not in todo:
        todo.append(latest.strftime("%Y-%m-%d"))           # always refresh the latest day
    for d in todo:
        ts = pd.Timestamp(d)
        rows = []
        for t, df in prices.items():
            if ts in df.index:
                b = df.loc[ts]
                rows.append({"date": d, "ticker": t, "name": (names or {}).get(t, ""),
                             "open": round(float(b["Open"]), 4), "high": round(float(b["High"]), 4),
                             "low": round(float(b["Low"]), 4), "close": round(float(b["Close"]), 4),
                             "volume": int(b["Volume"]) if not pd.isna(b["Volume"]) else ""})
        if rows:
            pd.DataFrame(rows).sort_values("ticker").to_csv(pdir / f"{d}.csv", index=False)
    idx = sorted((p.stem for p in pdir.glob("????-??-??.csv")), reverse=True)
    (pdir / "index.json").write_text(json.dumps(idx))
    return len(todo)


# ------------------------------------------------------------------ dual-score replay

def _replay(px: pd.DataFrame, e20: pd.Series, sig_date, entry, stop0, t1):
    """Live v1.2 management rules: buy-stop valid 2 sessions; stop checked first on each
    bar; BE at +1R; sell half at T1; rest exits on a close under the 20-EMA; time stop
    after 7 sessions if under +0.5R; max hold 30 sessions."""
    after = px[px.index > pd.Timestamp(sig_date)]
    win = after.head(2)
    hit = win[win["High"] >= entry]
    if hit.empty:
        return {"outcome": "Not filled" if len(win) >= 2 else "Pending"}
    fdt = hit.index[0]
    fill = max(entry, float(hit["Open"].iloc[0]))
    risk = fill - stop0
    if risk <= 0:
        return {"outcome": "Invalid plan"}
    bars = after[after.index >= fdt]
    stop, half, realised, reason, xdt = stop0, False, 0.0, None, None
    hi, lo, n = fill, fill, 0
    for dt, b in bars.iterrows():
        n += 1
        o, h, l, c = (float(b[k]) for k in ("Open", "High", "Low", "Close"))
        if l <= stop:
            px_ = stop if dt == fdt else min(stop, o)
            lo = min(lo, px_)
            realised += (0.5 if half else 1.0) * (px_ - fill) / risk
            reason = ("T1 then breakeven" if half else "Breakeven stop") if stop >= fill else "Stopped"
            xdt = dt
            break
        hi, lo = max(hi, h), min(lo, l)
        if not half and h >= t1:
            realised += 0.5 * ((t1 if dt == fdt else max(t1, o)) - fill) / risk
            half = True
            stop = max(stop, fill)
        if h >= fill + risk:
            stop = max(stop, fill)
        if half and c < float(e20.loc[dt]):
            realised += 0.5 * (c - fill) / risk
            reason, xdt = "T1 then trail", dt
            break
        if not half and n >= 7 and c < fill + 0.5 * risk:
            realised += (c - fill) / risk
            reason, xdt = "Time stop", dt
            break
        if n >= 30:
            realised += (0.5 if half else 1.0) * (c - fill) / risk
            reason, xdt = "Max hold", dt
            break
    out = {"filled": fdt.strftime("%Y-%m-%d"), "fill": round(fill, 3), "days": n,
           "mfe_r": round((hi - fill) / risk, 2), "mae_r": round((lo - fill) / risk, 2), "t1_hit": half}
    if reason is None:                                       # still running
        last = float(bars["Close"].iloc[-1])
        out.update({"outcome": "Open (T1 taken)" if half else "Open", "closed": "",
                    "r": round(realised + (0.5 if half else 1.0) * (last - fill) / risk, 2)})
    else:
        out.update({"outcome": reason, "closed": xdt.strftime("%Y-%m-%d"),
                    "r": round(realised - DUAL_COST * fill / risk, 2)})
    return out


def evaluate_dual(out_dir: Path, prices: dict):
    """Replay every dual-score BUY and WATCH plan saved in data/runs/*.json.
    One position per stock: a new plan is ignored while a filled one is still running.
    WATCH plans were not buy signals - their rows show what would have happened."""
    runs = sorted((out_dir / "data" / "runs").glob("????-??-??.json"))
    sigs = []
    for f in runs:
        for r in json.loads(f.read_text()).get("results", []):
            dl = r.get("dual") or {}
            pl = dl.get("plan") or {}
            if dl.get("decision") in ("BUY", "WATCH") and pl.get("entry_buy_stop"):
                sigs.append({"date": f.stem, "ticker": r["ticker"], "code": r["code"], "name": r["name"],
                             "decision": dl["decision"], "version": dl.get("version") or "1.1",
                             "sm": dl["sm"]["score"], "ts": dl["ts"]["score"],
                             "entry": pl["entry_buy_stop"], "stop": pl["stop"], "t1": pl["target1"],
                             "t2": pl.get("target2"), "rr": pl.get("rr_t1"), "qty": pl.get("shares")})
    rows, busy = [], {}
    for s in sorted(sigs, key=lambda x: (x["date"], x["code"])):
        px = prices.get(s["ticker"])
        if px is None:
            continue
        if busy.get(s["ticker"]) and s["date"] <= busy[s["ticker"]]:
            continue
        e20 = px["Close"].ewm(span=20, adjust=False).mean()
        res = _replay(px, e20, s["date"], s["entry"], s["stop"], s["t1"])
        if res.get("filled"):
            busy[s["ticker"]] = res.get("closed") or "9999-12-31"
        rows.append({**s, **res})

    def summ(rs):
        closed = [r for r in rs if r.get("closed")]
        filled = [r for r in rs if r.get("filled")]
        avg = lambda k, xs: round(sum(x[k] for x in xs) / len(xs), 2) if xs else None
        return {"plans": len(rs), "filled": len(filled), "closed": len(closed),
                "win_rate": round(100 * sum(r["r"] > 0 for r in closed) / len(closed), 1) if closed else None,
                "avg_r": avg("r", closed), "total_r": round(sum(r["r"] for r in closed), 2) if closed else None,
                "avg_mfe_r": avg("mfe_r", filled), "avg_mae_r": avg("mae_r", filled), "avg_days": avg("days", closed)}

    res = {"rows": sorted(rows, key=lambda r: (r["date"], r["code"]), reverse=True),
           "summary": {"BUY": summ([r for r in rows if r["decision"] == "BUY"]),
                       "WATCH": summ([r for r in rows if r["decision"] == "WATCH"])},
           "rules": "Buy-stop 2 sessions; stop first; BE at +1R; half at T1; rest out on close < EMA20; "
                    "time stop day 7 if < +0.5R; max 30 sessions; R net of 0.25% round trip. "
                    "MFE/MAE = best/worst excursion from fill, in R."}
    (out_dir / "data" / "dual_outcomes.json").write_text(json.dumps(res, indent=1, default=str))
    return res
