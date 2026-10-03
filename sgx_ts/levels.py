"""Support / resistance from clustered swing pivots."""
import pandas as pd


def find_levels(df: pd.DataFrame, atr_now: float, lookback=250, window=5,
                cluster_atr=0.6, per_side=3):
    d = df.tail(lookback)
    hi, lo = d["High"].values, d["Low"].values
    pivots = []  # (price, kind, bar_index)
    for i in range(window, len(d) - window):
        if hi[i] == hi[i - window:i + window + 1].max():
            pivots.append((float(hi[i]), "H", i))
        if lo[i] == lo[i - window:i + window + 1].min():
            pivots.append((float(lo[i]), "L", i))

    pivots.sort(key=lambda p: p[0])
    tol = max(atr_now * cluster_atr, 1e-9)
    clusters = []
    for p in pivots:
        if clusters and p[0] - clusters[-1][-1][0] <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])

    n = len(d)
    levels = []
    for c in clusters:
        price = sum(p[0] for p in c) / len(c)
        recency = max(p[2] for p in c) / max(n - 1, 1)       # 0..1, 1 = recent
        strength = len(c) + recency                           # touches + recency
        levels.append({"price": round(price, 3), "touches": len(c),
                       "strength": round(strength, 2)})

    close = float(df["Close"].iloc[-1])
    sup = sorted([l for l in levels if l["price"] < close], key=lambda l: -l["price"])
    res = sorted([l for l in levels if l["price"] > close], key=lambda l: l["price"])

    # fall back to range extremes if a side is empty
    if not res:
        res = [{"price": round(float(d["High"].max()), 3), "touches": 1, "strength": 1.0}]
    if not sup:
        sup = [{"price": round(float(d["Low"].min()), 3), "touches": 1, "strength": 1.0}]
    return sup[:per_side], res[:per_side]
