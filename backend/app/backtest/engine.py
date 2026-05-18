"""Backtest engine — replays the technical scorer across history.

How it works
------------
For each tracked ticker, for each historical date D (with enough lookback):
  1. Slice daily_bars up to D (inclusive)  — NO future bars
  2. Compute the technical_score from that slice (RSI / SMA / MACD / vol)
  3. Read the realized close at D+1, D+5, D+21
  4. Compute forward returns and bucket by score

We use only past-as-of-D bars for the indicators — this is the look-ahead
guard. Today's adjusted close from Yahoo includes future splits/dividends,
which IS a small look-ahead source; for v1 we accept it and document it.

What this measures
------------------
Whether the technical_score we compute today actually predicts forward
returns. Output:
  - Hit rate per score bucket (does score >+0.3 → more often-positive
    forward returns than score <-0.3?)
  - Mean forward return per bucket
  - Simple long-only P&L if you'd bought when score >= threshold
  - Sample size per bucket (so you know if the result is statistically meaningful)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyBar, Ticker
from app.signals.technical import _to_df, compute_indicators, technical_score

log = logging.getLogger(__name__)


@dataclass
class Trade:
    ticker: str
    date: pd.Timestamp
    score: float            # [-1, +1]
    entry: float
    ret_1d: float | None
    ret_5d: float | None
    ret_21d: float | None


# Need at least this many bars before the FIRST signal we record (so SMA-200
# is defined). Bars before the warm-up are still used to compute indicators
# — we just don't emit a trade.
WARMUP_BARS = 210


def _bars_for_ticker(db: Session, ticker_id: int) -> pd.DataFrame:
    rows = db.execute(
        select(DailyBar.bar_date, DailyBar.open, DailyBar.high, DailyBar.low,
               DailyBar.close, DailyBar.volume)
        .where(DailyBar.ticker_id == ticker_id)
        .order_by(DailyBar.bar_date.asc())
    ).all()
    if not rows:
        return pd.DataFrame()
    return _to_df(rows)


def replay_ticker(db: Session, ticker: Ticker, stride: int = 1) -> Iterable[Trade]:
    """Walk forward through the daily bars, emitting a Trade at every
    eligible date. stride > 1 samples every Nth day to control compute.

    Important: the indicator window passed to compute_indicators() is
    `df.iloc[:i+1]` — only bars up to and including the signal day. The
    forward return is then read from `df.iloc[i+1 .. i+21]`, which we
    never feed back into the indicator math. That's the look-ahead guard."""
    df = _bars_for_ticker(db, ticker.id)
    if len(df) < WARMUP_BARS + 21:
        return

    for i in range(WARMUP_BARS, len(df) - 21, stride):
        window = df.iloc[: i + 1]
        ind = compute_indicators(window)
        if not ind:
            continue
        score, _ = technical_score(ind)
        entry = float(df["close"].iloc[i])
        c_1d = float(df["close"].iloc[i + 1])
        c_5d = float(df["close"].iloc[i + 5]) if i + 5 < len(df) else None
        c_21d = float(df["close"].iloc[i + 21]) if i + 21 < len(df) else None

        yield Trade(
            ticker=ticker.symbol,
            date=df["date"].iloc[i],
            score=score,
            entry=entry,
            ret_1d=((c_1d - entry) / entry * 100) if c_1d else None,
            ret_5d=((c_5d - entry) / entry * 100) if c_5d else None,
            ret_21d=((c_21d - entry) / entry * 100) if c_21d else None,
        )


def replay_all(db: Session, stride: int = 5) -> list[Trade]:
    """Default stride=5 (one signal per trading week) keeps the sample
    size of the backtest manageable while still giving statistically
    meaningful coverage across 1 year × 50 tickers ≈ 2,600 trades."""
    tickers = db.execute(select(Ticker).where(Ticker.is_active.is_(True))).scalars().all()
    out: list[Trade] = []
    for t in tickers:
        try:
            ticker_trades = list(replay_ticker(db, t, stride=stride))
            out.extend(ticker_trades)
            log.info(f"replayed {t.symbol}: {len(ticker_trades)} trades")
        except Exception:
            log.exception(f"replay failed for {t.symbol}")
    return out
