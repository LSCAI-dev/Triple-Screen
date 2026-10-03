# SGX Triple Screen

Alexander Elder's Triple Screen applied to the 30 STI stocks. Runs after every SGX close on GitHub Actions, publishes a mobile-friendly site on GitHub Pages, and keeps every run in the repo for later retrieval.

## What it does

| Screen | Timeframe | Rule |
|---|---|---|
| 1. Tide | Weekly | Slope of weekly MACD histogram (12/26/9), confirmed by 26-wk EMA rising or price above it. Up = longs only, Down = shorts only, Mixed = stand aside. |
| 2. Wave | Daily | Trade against the wave: in an up-tide, Force Index(2) < 0, RSI(14) ≤ 45 or low touching EMA20, price within 3% of EMA50. Mirror for shorts. Too extended (> 1 ATR above EMA20) = wait. |
| 3. Entry | Next session | Buy stop 1 SGX tick above the last high (trail daily, 3 sessions). Stop 1 tick under the 2-day low, at least 0.75 ATR. T1 = nearest resistance cluster, T2 = next level or 2R. |

Support/resistance are clustered swing pivots over 250 sessions. Position size uses fixed-fractional risk (default 1% of S$100k) rounded to 100-share lots. Setups are graded A/B/C; anything under 1R to T1 is dropped to "watch".

Pages: **Today** (STI tide, setup table with entry/stop/T1/T2/qty, 30-stock board), one **stock page** each (daily candles + EMA20/50 + S/R + plan lines + MACD + RSI, weekly tide chart), and **Saved runs** (any past day's scan, CSV/JSON download, and a track record of how every past setup played out).

## Set up on GitHub (about 10 minutes)

1. Create a new repository, e.g. `sgx-triple-screen` (public, or private on a plan that allows Pages for private repos).
2. Upload everything in this folder, including the hidden `.github` folder. Easiest: `git init && git add . && git commit -m init && git remote add origin <url> && git push -u origin main`.
3. **Settings > Actions > General > Workflow permissions**: select *Read and write permissions*. Save.
4. **Actions** tab > *SGX Triple Screen* > **Run workflow**. Wait ~2 min; it creates `docs/`.
5. **Settings > Pages**: Source *Deploy from a branch*, branch `main`, folder `/docs`. Save.
6. Your site: `https://<username>.github.io/sgx-triple-screen/`. Bookmark it on laptop and phone (on iPhone: Share > Add to Home Screen).

From then on it runs Mon–Fri at 18:30 SGT. GitHub's scheduler can start 5–30 min late.

### Optional: seed the track record

Run once on your PC to replay the last ~6 months so *Saved runs* has history straight away:

```bash
pip install -r requirements.txt
python backfill.py --days 120
python run.py
git add docs && git commit -m "backfill" && git push
```

## Run locally

```bash
pip install -r requirements.txt
python run.py            # live Yahoo data -> docs/, open docs/index.html
python run.py --demo     # synthetic prices, offline test -> demo-site/
```

## Where results are saved

| File | Contents |
|---|---|
| `docs/data/runs/YYYY-MM-DD.json` | Full scan for that day: every stock's screens, levels, plan |
| `docs/data/signals_log.csv` | One row per stock per day; open in Excel |
| `docs/data/outcomes.json` | Every past setup replayed: not filled / open / T1 hit / stopped, with R multiple |
| `docs/data/latest.json` | Most recent scan (handy for other tools/dashboards) |

All of it is in git history too, so nothing is ever overwritten silently. Charts are rebuilt for the latest day only; past days keep their numbers in JSON.

## Tuning

Everything is in `config.py`: universe, EMA/RSI/MACD lengths, pullback thresholds, ATR stop floor, S/R clustering, account size and risk %, shorts on/off. Check the STI list after each quarterly review (next: December 2026).

## Caveats

- Data is Yahoo Finance end-of-day via `yfinance`, unofficial and occasionally late or wrong. The site shows source and bar date on every page. Verify prices and levels on your broker terminal before placing orders.
- Unadjusted prices are used so levels match broker charts; dividends and corporate actions cause gaps in the indicators.
- Short setups assume CFDs or SBL; most retail SGX accounts cannot short cash equities.
- The track record replays signals with simple rules (same-bar stop/target counted as a loss, no slippage or fees). It is a sanity check, not a backtest.
- Not investment advice.
