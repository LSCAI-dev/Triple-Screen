"""Price data. Live: Yahoo Finance via yfinance (unadjusted OHLC, to match broker quotes)."""
import numpy as np
import pandas as pd

COLS = ["Open", "High", "Low", "Close", "Volume"]


def fetch(tickers, period="2y", retries=2):
    """Batch download, then retry stragglers one by one (Yahoo throttles CI runners)."""
    import time
    import yfinance as yf
    out = _parse(yf.download(list(tickers), period=period, interval="1d", group_by="ticker",
                             auto_adjust=False, progress=False, threads=True), tickers)
    for attempt in range(retries):
        missing = [t for t in tickers if t not in out]
        if not missing:
            break
        time.sleep(5 * (attempt + 1))
        for t in missing:
            try:
                out.update(_parse(yf.download([t], period=period, interval="1d", group_by="ticker",
                                              auto_adjust=False, progress=False), [t]))
            except Exception as e:
                print(f"{t}: download failed ({e})")
    return out


def _parse(raw, tickers):
    out = {}
    for t in tickers:
        try:
            df = raw[t][COLS].dropna(subset=["Close"]).copy()
        except (KeyError, TypeError):
            continue
        df = df[df["Volume"].fillna(0) >= 0]
        df.index = pd.to_datetime(df.index).tz_localize(None)
        if len(df) >= 120:
            out[t] = df
    return out


def demo(tickers, bars=500, seed=7):
    """Synthetic OHLCV for offline testing only. Not market data."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=bars)
    bars = len(idx)
    out = {}
    for t in tickers:
        p0 = float(rng.choice([0.45, 1.2, 2.6, 5.5, 14.0, 38.0]))
        drift = rng.normal(0, 0.0008)
        rets = rng.normal(drift, 0.014, bars) + 0.004 * np.sin(np.arange(bars) / rng.uniform(8, 25))
        close = p0 * np.exp(np.cumsum(rets))
        opn = close * (1 + rng.normal(0, 0.004, bars))
        hi = np.maximum(opn, close) * (1 + np.abs(rng.normal(0, 0.006, bars)))
        lo = np.minimum(opn, close) * (1 - np.abs(rng.normal(0, 0.006, bars)))
        vol = rng.integers(200_000, 8_000_000, bars)
        out[t] = pd.DataFrame({"Open": opn, "High": hi, "Low": lo, "Close": close, "Volume": vol}, index=idx)
    return out
