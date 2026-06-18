#!/usr/bin/env python3
"""Backtest a weighted multi-instrument strategy portfolio."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quantbot.backtest.metrics import equity_curve, summarize_returns
from quantbot.research.signals import add_strategy_positions, strategy_returns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_baseline.yaml"))
    parser.add_argument("--equity-output", type=Path, default=Path("reports/portfolio_equity.csv"))
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def build_enriched_bars(bars: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol, group in bars.groupby("symbol"):
        enriched = add_strategy_positions(group.drop(columns=["symbol"]))
        enriched.insert(0, "symbol", symbol)
        frames.append(enriched)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    args = parse_args()
    args.equity_output.parent.mkdir(parents=True, exist_ok=True)

    config = load_config(args.config)
    gross_leverage = float(config["gross_leverage"])
    legs = config["legs"]
    total_weight = sum(float(leg["weight"]) for leg in legs)
    if abs(total_weight - 1.0) > 1e-9:
        raise SystemExit(f"Portfolio weights must sum to 1.0, got {total_weight}")

    bars = pd.read_parquet(args.bars)
    enriched = build_enriched_bars(bars)

    leg_returns: list[pd.Series] = []
    for leg in legs:
        symbol = leg["symbol"]
        strategy = leg["strategy"]
        weight = float(leg["weight"])
        group = enriched[enriched["symbol"] == symbol].copy()
        if group.empty:
            raise SystemExit(f"No bars found for {symbol}")
        if strategy not in group.columns:
            raise SystemExit(f"Strategy {strategy} missing for {symbol}")
        returns = strategy_returns(group, strategy, gross_leverage * weight)
        returns.index = pd.to_datetime(group["time"], utc=True)
        returns.name = f"{symbol}_{strategy}"
        leg_returns.append(returns)

    aligned = pd.concat(leg_returns, axis=1, sort=False).sort_index().fillna(0.0)
    portfolio_returns = aligned.sum(axis=1)
    metrics = summarize_returns(portfolio_returns)
    curve = equity_curve(portfolio_returns, initial_equity=1_000_000.0)

    output = aligned.copy()
    output["portfolio_return"] = portfolio_returns
    output["equity"] = curve
    output.to_csv(args.equity_output, index_label="time")

    print("PORTFOLIO")
    print(f"config: {args.config}")
    for key, value in metrics.items():
        print(f"{key}: {value:.6f}")
    print(f"final_equity: {curve.iloc[-1]:.2f}")
    print(f"wrote: {args.equity_output}")


if __name__ == "__main__":
    main()
