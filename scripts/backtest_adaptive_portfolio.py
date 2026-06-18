#!/usr/bin/env python3
"""Backtest a weighted portfolio with adaptive risk scaling."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quantbot.backtest.metrics import summarize_returns
from quantbot.research.portfolio import build_enriched_bars, build_unit_returns
from quantbot.risk.governor import AdaptiveRiskConfig, AdaptiveRiskGovernor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_adaptive.yaml"))
    parser.add_argument("--equity-output", type=Path, default=Path("reports/adaptive_equity.csv"))
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def main() -> None:
    args = parse_args()
    args.equity_output.parent.mkdir(parents=True, exist_ok=True)

    config = load_config(args.config)
    bars = pd.read_parquet(args.bars)
    enriched = build_enriched_bars(bars)
    aligned = build_unit_returns(enriched, config["legs"])
    unit_returns = aligned.sum(axis=1)

    risk_config = AdaptiveRiskConfig(**config["risk"])
    result = AdaptiveRiskGovernor(risk_config).run(unit_returns)
    metrics = summarize_returns(result.returns)

    output = aligned.copy()
    output["unit_portfolio_return"] = unit_returns
    output["portfolio_return"] = result.returns
    output["gross_leverage"] = result.gross_leverage
    output["drawdown_before_bar"] = result.drawdown
    output["equity"] = result.equity
    output.to_csv(args.equity_output, index_label="time")

    print("ADAPTIVE_PORTFOLIO")
    print(f"config: {args.config}")
    for key, value in metrics.items():
        print(f"{key}: {value:.6f}")
    print(f"final_equity: {result.equity.iloc[-1]:.2f}")
    print(f"avg_gross_leverage: {result.gross_leverage.mean():.3f}")
    print(f"max_gross_leverage: {result.gross_leverage.max():.3f}")
    print(f"min_gross_leverage: {result.gross_leverage.min():.3f}")
    print(f"wrote: {args.equity_output}")


if __name__ == "__main__":
    main()
