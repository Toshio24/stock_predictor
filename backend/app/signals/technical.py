"""Technical-analysis scoring.

Reads daily bars from the DB, computes RSI(14), SMA(20/50/200), MACD,
and volume ratio, and rolls them into a single technical_score in [-1, +1]
that combines with sentiment in the composite signal."""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyBar


def _to_df(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    df["volume"] = df["volume"].astype(float)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return macd, signal, hist


def compute_indicators(df: pd.DataFrame) -> dict:
    """Computes the indicator set on the most recent bar. Returns a dict."""
    if len(df) < 30:
        return {}
    close = df["close"]
    out = {
        "close": float(close.iloc[-1]),
        "rsi_14": float(_rsi(close).iloc[-1]),
        "sma_20": float(close.rolling(20).mean().iloc[-1]),
        "sma_50": float(close.rolling(50).mean().iloc[-1]) if len(df) >= 50 else None,
        "sma_200": float(close.rolling(200).mean().iloc[-1]) if len(df) >= 200 else None,
    }
    macd, sig, hist = _macd(close)
    out["macd"] = float(macd.iloc[-1])
    out["macd_signal"] = float(sig.iloc[-1])
    out["macd_hist"] = float(hist.iloc[-1])

    vol = df["volume"]
    avg_vol_20 = vol.rolling(20).mean().iloc[-1]
    out["volume_ratio"] = float(vol.iloc[-1] / avg_vol_20) if avg_vol_20 and avg_vol_20 > 0 else 1.0
    return out


def technical_score(ind: dict) -> tuple[float, str]:
    """Combine indicators into a single score in [-1, +1] + a human-readable
    rationale. Heuristic for v1 — replace with a learned weighting later."""
    if not ind:
        return 0.0, "Not enough price history to compute technicals."

    components: list[tuple[float, str]] = []

    # RSI: oversold (<30) bullish, overbought (>70) bearish
    rsi = ind.get("rsi_14")
    if rsi is not None and not np.isnan(rsi):
        if rsi < 30:
            components.append((+0.6, f"RSI {rsi:.0f} oversold"))
        elif rsi > 70:
            components.append((-0.5, f"RSI {rsi:.0f} overbought"))
        elif rsi < 45:
            components.append((+0.2, f"RSI {rsi:.0f} mild oversold"))
        elif rsi > 55:
            components.append((-0.1, f"RSI {rsi:.0f} mild overbought"))

    # SMA trend stack: price > SMA20 > SMA50 > SMA200 is a strong uptrend
    close = ind.get("close")
    sma20, sma50, sma200 = ind.get("sma_20"), ind.get("sma_50"), ind.get("sma_200")
    if close and sma20:
        if sma50 and sma200:
            if close > sma20 > sma50 > sma200:
                components.append((+0.6, "Uptrend: price>SMA20>SMA50>SMA200"))
            elif close < sma20 < sma50 < sma200:
                components.append((-0.6, "Downtrend: price<SMA20<SMA50<SMA200"))
            elif close > sma200:
                components.append((+0.2, "Above 200-day MA"))
            else:
                components.append((-0.2, "Below 200-day MA"))
        elif close > sma20:
            components.append((+0.15, "Above 20-day MA"))
        else:
            components.append((-0.15, "Below 20-day MA"))

    # MACD histogram momentum
    macd_hist = ind.get("macd_hist")
    if macd_hist is not None and not np.isnan(macd_hist):
        if macd_hist > 0:
            components.append((+0.2, "MACD positive momentum"))
        else:
            components.append((-0.2, "MACD negative momentum"))

    # Volume anomaly — a big day with conviction (>1.8x avg) is signal
    vr = ind.get("volume_ratio")
    if vr and vr > 1.8:
        # Direction of move matters: but we don't have today's % change here.
        # Treat heavy volume as confirmation, weight small.
        components.append((+0.1, f"Volume {vr:.1f}x avg"))

    if not components:
        return 0.0, "Indicators in neutral zone."

    score = float(np.mean([c[0] for c in components]))
    score = max(-1.0, min(1.0, score))
    rationale = "; ".join(c[1] for c in components)
    return score, rationale


def score_ticker(db: Session, ticker_id: int) -> tuple[float | None, dict, str]:
    """Returns (technical_score in [-1, +1] or None, indicator dict, rationale).
    None means we don't have enough history yet — caller should fall back to
    sentiment-only."""
    rows = db.execute(
        select(DailyBar.bar_date, DailyBar.open, DailyBar.high, DailyBar.low,
               DailyBar.close, DailyBar.volume)
        .where(DailyBar.ticker_id == ticker_id)
        .order_by(DailyBar.bar_date.desc())
        .limit(260)   # ~1 year of trading days
    ).all()
    if len(rows) < 30:
        return None, {}, "Insufficient price history."

    df = _to_df(rows)
    ind = compute_indicators(df)
    score, rationale = technical_score(ind)
    return score, ind, rationale
