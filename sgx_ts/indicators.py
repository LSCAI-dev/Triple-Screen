"""Indicators and SGX price helpers."""
import math
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def rsi(close: pd.Series, n=14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, 1e-12)
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, n=14) -> pd.Series:
    pc = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - pc).abs(),
                    (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def force_index(df: pd.DataFrame, n=2) -> pd.Series:
    return ema(df["Close"].diff() * df["Volume"], n)


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min",
                                     "Close": "last", "Volume": "sum"}).dropna()


# --- SGX tick sizes (securities): <0.20 -> 0.001, <1.00 -> 0.005, else 0.01
def tick(p: float) -> float:
    return 0.001 if p < 0.20 else 0.005 if p < 1.00 else 0.01


def to_tick(p: float, how: str = "nearest") -> float:
    t = tick(p)
    x = round(p / t, 6)
    x = math.ceil(x) if how == "up" else math.floor(x) if how == "down" else round(x)
    return round(x * t, 3)
