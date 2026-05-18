"""CLI entrypoint:

    docker compose run --rm api python -m app.backtest.run [--stride N]

Runs the technical-only backtest over everything in `daily_bars`, prints
per-bucket metrics for the 1d / 5d / 21d horizons, and dumps the full
trade tape to `backtest_trades.csv`.

This is the v1 measurement — once historical news is backfilled (Phase B),
the same engine will replay the full composite signal, not just technicals."""
import argparse
import logging
import sys

import pandas as pd

from app.db import session_scope
from app.backtest.engine import replay_all
from app.backtest.metrics import (
    overall_summary, per_bucket_metrics, long_only_pnl, trades_to_df,
)


def _print_section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stride", type=int, default=5,
                   help="Sample every Nth trading day (default 5 = one per week)")
    p.add_argument("--csv", default="backtest_trades.csv",
                   help="Output CSV for the full trade tape")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [backtest] %(message)s")

    with session_scope() as db:
        trades = replay_all(db, stride=args.stride)

    df = trades_to_df(trades)
    if df.empty:
        print("No trades produced — do you have daily_bars data? "
              "Run the price worker first: python -m app.workers.prices")
        return 1

    print(f"\nReplayed {len(df)} trades across {df['ticker'].nunique()} tickers "
          f"({df['date'].min().date()} → {df['date'].max().date()})")

    for horizon in ("ret_1d", "ret_5d", "ret_21d"):
        _print_section(f"Horizon: {horizon}")
        summary = overall_summary(df, horizon=horizon)
        print(f"  score↔return correlation:  {summary.get('score_vs_return_corr')}")
        print(f"  baseline mean return:      {summary.get('baseline_mean_%')}%")
        print(f"  strong_bullish mean:       {summary.get('long_only_mean_%')}% (n={summary.get('long_only_n')})")
        print(f"  strong_bearish mean:       {summary.get('short_signal_mean_%')}% (n={summary.get('short_signal_n')})")
        print()
        print(per_bucket_metrics(df, horizon=horizon).to_string(index=False))
        print()
        for thresh in (0.20, 0.40, 0.60):
            pnl = long_only_pnl(df, horizon=horizon, threshold=thresh)
            if pnl.get("n_trades"):
                print(f"  long-only PnL (threshold ≥ {thresh:+.2f}): "
                      f"mean={pnl['mean_return_%']}%  win_rate={pnl['win_rate_%']}%  "
                      f"sharpe={pnl['sharpe_annualized']}  n={pnl['n_trades']}")

    df.to_csv(args.csv, index=False)
    print(f"\nFull trade tape → {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
