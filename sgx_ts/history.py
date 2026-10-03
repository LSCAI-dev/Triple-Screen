"""Saved results: one JSON per run, a cumulative CSV log, and outcome tracking."""
import json
from pathlib import Path
import pandas as pd

import config as C
from .screens import SETUP_LONG, SETUP_SHORT

LOG_COLS = ["date", "ticker", "code", "name", "status", "grade", "close", "entry", "stop",
            "t1", "t2", "rr1", "rsi", "tide", "wave"]


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
        rows.append({"date": meta["as_of"], "ticker": r["ticker"], "code": r["code"], "name": r["name"],
                     "status": r["status"], "grade": p.get("grade", ""), "close": r["close"],
                     "entry": p.get("entry", ""), "stop": p.get("stop", ""), "t1": p.get("t1", ""),
                     "t2": p.get("t2", ""), "rr1": p.get("rr1", ""), "rsi": r["rsi"],
                     "tide": r["tide"]["tide"], "wave": r["wave"]})
    log = out_dir / "data" / "signals_log.csv"
    new = pd.DataFrame(rows, columns=LOG_COLS)
    if log.exists():
        old = pd.read_csv(log, dtype=str)
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
