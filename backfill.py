"""Seed the saved-runs archive and track record by replaying the scan on past dates.

    python backfill.py --days 120          # live Yahoo data -> docs/
    python backfill.py --days 120 --demo   # synthetic -> demo-site/

Uses today's STI list for every date (small survivorship bias). Run once, then
let the daily job keep the archive growing. Re-running replaces the same dates.
"""
import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import config as C
from sgx_ts import data
from sgx_ts.screens import analyse, sort_key, enrich_weekly, weekly_tide
from sgx_ts.history import save_run, evaluate

ap = argparse.ArgumentParser()
ap.add_argument("--days", type=int, default=120)
ap.add_argument("--demo", action="store_true")
ap.add_argument("--out", default=None)
a = ap.parse_args()
out = Path(a.out or ("demo-site" if a.demo else "docs"))

tickers = list(C.UNIVERSE) + [C.MARKET_INDEX[0]]
prices = data.demo(tickers) if a.demo else data.fetch(tickers, C.HISTORY_PERIOD)
ref = prices.get("D05.SI", next(iter(prices.values())))
dates = ref.index[-(a.days + 1):-1]          # skip the latest bar; run.py handles today
now = datetime.now(ZoneInfo(C.TIMEZONE)).strftime("%Y-%m-%d %H:%M")

for dt in dates:
    res = []
    for t, name in C.UNIVERSE.items():
        px = prices.get(t)
        if px is None:
            continue
        cut = px[px.index <= dt]
        if len(cut) >= 120 and cut.index[-1] == dt:
            try:
                res.append(analyse(t, name, cut))
            except Exception as e:
                print(t, dt.date(), e)
    if not res:
        continue
    res.sort(key=sort_key)
    sti = prices.get(C.MARKET_INDEX[0])
    tide = weekly_tide(enrich_weekly(sti[sti.index <= dt]))["tide"] if sti is not None else "Mixed"
    meta = {"as_of": dt.strftime("%Y-%m-%d"), "generated": now + " (backfill)",
            "source": "Synthetic demo data" if a.demo else "Yahoo Finance via yfinance (unadjusted daily OHLC)",
            "demo": a.demo, "universe": len(C.UNIVERSE), "analysed": len(res), "missing": [], "sti_tide": tide}
    save_run(out, meta, res)
    print(meta["as_of"], sum(1 for r in res if r.get("plan")), "setups")

print("Track record:", evaluate(out, prices)["summary"])
print("Now run: python run.py", "--demo" if a.demo else "")
