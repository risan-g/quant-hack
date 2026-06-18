#!/usr/bin/env python3
"""Run fast first-pass strategy research on compact 15-minute bars."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from quantbot.backtest.metrics import summarize_returns
from quantbot.research.signals import add_strategy_positions, strategy_returns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--output", type=Path, default=Path("reports/signal_research.csv"))
    parser.add_argument("--leverage", type=float, default=5.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    bars = pd.read_parquet(args.bars)
    frames: list[pd.DataFrame] = []
    for symbol, group in bars.groupby("symbol"):
        enriched_group = add_strategy_positions(group.drop(columns=["symbol"]))
        enriched_group.insert(0, "symbol", symbol)
        frames.append(enriched_group)
    enriched = pd.concat(frames, ignore_index=True)

    position_cols = [
        col
        for col in enriched.columns
        if col.startswith(("momentum_", "breakout_", "mean_reversion_"))
    ]

    rows: list[dict[str, float | str]] = []
    for symbol, group in enriched.groupby("symbol"):
        for position_col in position_cols:
            returns = strategy_returns(group, position_col, args.leverage)
            metrics = summarize_returns(returns)
            trades = float((group[position_col].diff().abs().fillna(group[position_col].abs()) > 0).sum())
            rows.append(
                {
                    "symbol": symbol,
                    "strategy": position_col,
                    "leverage": args.leverage,
                    "trades": trades,
                    **metrics,
                }
            )

    report = pd.DataFrame(rows).sort_values(
        ["return", "sharpe", "max_drawdown"], ascending=[False, False, True]
    )
    report.to_csv(args.output, index=False)
    print(report.head(30).to_string(index=False))
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
