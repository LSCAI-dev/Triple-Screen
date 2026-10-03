"""Run the SGX Triple Screen scan and rebuild the site.

    python run.py              # live data from Yahoo Finance -> docs/
    python run.py --demo       # synthetic data, offline test -> demo-site/
    python run.py --out site   # custom output folder
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import config as C
from sgx_ts import data
from sgx_ts.screens import analyse, sort_key, enrich_weekly, weekly_tide
from sgx_ts.history import save_run, evaluate
from sgx_ts.site import build


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="synthetic prices for an offline test")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out or ("demo-site" if a.demo else "docs"))

    tickers = list(C.UNIVERSE) + [C.MARKET_INDEX[0]]
    prices = data.demo(tickers) if a.demo else data.fetch(tickers, C.HISTORY_PERIOD)
    missing = [t for t in C.UNIVERSE if t not in prices]
    if missing:
        print("No / short data for:", ", ".join(missing))
    if not any(t in prices for t in C.UNIVERSE):
        sys.exit("No price data downloaded - aborting so the published site is left unchanged.")

    results = []
    for t, name in C.UNIVERSE.items():
        if t in prices:
            try:
                results.append(analyse(t, name, prices[t]))
            except Exception as e:  # one bad counter should not stop the run
                print(f"{t}: {e}")
    results.sort(key=sort_key)

    sti = {"tide": "Mixed"}
    if C.MARKET_INDEX[0] in prices:
        sti = weekly_tide(enrich_weekly(prices[C.MARKET_INDEX[0]]))

    as_of = max(r["date"] for r in results)
    meta = {
        "as_of": as_of,
        "generated": datetime.now(ZoneInfo(C.TIMEZONE)).strftime("%Y-%m-%d %H:%M"),
        "source": "Synthetic demo data" if a.demo else "Yahoo Finance via yfinance (unadjusted daily OHLC)",
        "demo": a.demo, "universe": len(C.UNIVERSE), "analysed": len(results), "missing": missing,
        "sti_tide": sti["tide"],
    }
    build(out, meta, results, sti)
    save_run(out, meta, results)
    ev = evaluate(out, prices)

    print(f"As of {as_of}: {len(results)} analysed, STI tide {sti['tide']}")
    for r in results:
        if r.get("plan"):
            p = r["plan"]
            print(f"  {r['code']:6} {r['status']:12} {p['grade']}  entry {p['entry']:.3f}  stop {p['stop']:.3f}"
                  f"  T1 {p['t1']:.3f}  T2 {p['t2']:.3f}  R:R {p['rr1']}")
    print("Track record:", ev["summary"])
    print("Site written to", out.resolve())


if __name__ == "__main__":
    main()
