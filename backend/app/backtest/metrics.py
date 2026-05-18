"""Backtest metrics: hit rate, mean return, P&L, calibration."""
from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

import numpy as np
import pandas as pd

from app.backtest.engine import Trade


# Score buckets we'll report. Match the human reads:
#   ≤ -0.6 = strong bearish, -0.6..-0.2 = weak bearish, -0.2..+0.2 = neutral,
#   +0.2..+0.6 = weak bullish, ≥ +0.6 = strong bullish.
BUCKETS = [
    ("strong_bearish", -1.01, -0.60),
    ("weak_bearish",   -0.60, -0.20),
    ("neutral",        -0.20,  0.20),
    ("weak_bullish",    0.20,  0.60),
    ("strong_bullish",  0.60,  1.01),
]


def _bucket_of(score: float) -> str:
    for name, lo, hi in BUCKETS:
        if lo <= score < hi:
            return name
    return "neutral"


def trades_to_df(trades: Iterable[Trade]) -> pd.DataFrame:
    rows = [asdict(t) for t in trades]
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["bucket"] = df["score"].apply(_bucket_of)
    return df


def per_bucket_metrics(df: pd.DataFrame, horizon: str = "ret_5d") -> pd.DataFrame:
    """For each score bucket, return:
      - n: sample size
      - hit_rate: % of trades with positive forward return (50% = no edge)
      - mean_return: average forward return (%)
      - median_return: median forward return (%)
      - std_return: standard deviation
    """
    rows = []
    for name, lo, hi in BUCKETS:
        sub = df[(df["score"] >= lo) & (df["score"] < hi)]
        sub = sub.dropna(subset=[horizon])
        n = len(sub)
        if n == 0:
            rows.append({"bucket": name, "n": 0, "hit_rate_%": None,
                         "mean_return_%": None, "median_return_%": None, "std_%": None})
            continue
        rets = sub[horizon]
        rows.append({
            "bucket": name,
            "n": n,
            "hit_rate_%": round(float((rets > 0).mean() * 100), 1),
            "mean_return_%": round(float(rets.mean()), 3),
            "median_return_%": round(float(rets.median()), 3),
            "std_%": round(float(rets.std()), 3),
        })
    return pd.DataFrame(rows)


def overall_summary(df: pd.DataFrame, horizon: str = "ret_5d") -> dict:
    """Single-line summary: did the score predict anything overall?"""
    df = df.dropna(subset=[horizon])
    if df.empty:
        return {}
    # Pearson correlation between score and forward return
    corr = float(df["score"].corr(df[horizon]))
    # If you bought only strong_bullish, what would mean return be?
    longs = df[df["bucket"] == "strong_bullish"][horizon]
    shorts = df[df["bucket"] == "strong_bearish"][horizon]
    return {
        "n_trades": len(df),
        "score_vs_return_corr": round(corr, 4),
        "long_only_mean_%": round(float(longs.mean()), 3) if len(longs) else None,
        "long_only_n": len(longs),
        "short_signal_mean_%": round(float(shorts.mean()), 3) if len(shorts) else None,
        "short_signal_n": len(shorts),
        "baseline_mean_%": round(float(df[horizon].mean()), 3),
    }


def long_only_pnl(df: pd.DataFrame, horizon: str = "ret_5d",
                  threshold: float = 0.20) -> dict:
    """Simulate: buy 1 unit every time score >= threshold, hold for horizon,
    exit. No fees, no slippage, no position sizing — illustrative only."""
    df = df.dropna(subset=[horizon])
    sub = df[df["score"] >= threshold]
    if sub.empty:
        return {"n_trades": 0}
    rets = sub[horizon] / 100  # convert % to fraction
    # cumulative product compounding (each trade is independent — this is
    # equivalent to equal-weight averaging not actual compounding, but
    # works as a quick scoreboard)
    avg = float(rets.mean())
    win_rate = float((rets > 0).mean() * 100)
    # Sharpe-ish: mean / std × sqrt(periods_per_year)
    periods_per_year = 52 if horizon == "ret_5d" else (252 if horizon == "ret_1d" else 12)
    sharpe = float(rets.mean() / rets.std() * (periods_per_year ** 0.5)) if rets.std() > 0 else 0.0
    return {
        "n_trades": len(sub),
        "threshold": threshold,
        "horizon": horizon,
        "mean_return_%": round(avg * 100, 3),
        "win_rate_%": round(win_rate, 1),
        "sharpe_annualized": round(sharpe, 2),
    }
