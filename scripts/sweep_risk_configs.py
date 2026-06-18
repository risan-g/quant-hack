#!/usr/bin/env python3
"""Sweep adaptive risk settings over a fixed strategy portfolio."""

from __future__ import annotations

import argparse
import itertools
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
    parser.add_argument("--output", type=Path, default=Path("reports/risk_sweep.csv"))
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def score_row(metrics: dict[str, float]) -> float:
    """A rough tournament utility for comparing risk configs."""
    return metrics["return"] - 1.50 * metrics["max_drawdown"] + 4.0 * metrics["sharpe"]


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    config = load_config(args.config)
    bars = pd.read_parquet(args.bars)
    enriched = build_enriched_bars(bars)
    aligned = build_unit_returns(enriched, config["legs"])
    unit_returns = aligned.sum(axis=1)

    rows: list[dict[str, float]] = []
    grid = itertools.product(
        [5.0, 6.0, 7.0],
        [6.0, 8.0, 10.0],
        [1.0, 2.0, 3.0],
        [0.06, 0.08, 0.10],
        [0.14, 0.18, 0.22],
        [-0.015, -0.025, -0.04],
    )
    for base, attack, defend, soft_dd, hard_dd, recent_loss_cut in grid:
        if attack < base or hard_dd <= soft_dd:
            continue
        risk_config = AdaptiveRiskConfig(
            base_gross_leverage=base,
            attack_gross_leverage=attack,
            defend_gross_leverage=defend,
            max_gross_leverage=12.0,
            soft_drawdown=soft_dd,
            hard_drawdown=hard_dd,
            attack_drawdown=0.02,
            recent_loss_window=16,
            recent_loss_cut=recent_loss_cut,
            recovery_bars=8,
        )
        result = AdaptiveRiskGovernor(risk_config).run(unit_returns)
        metrics = summarize_returns(result.returns)
        rows.append(
            {
                **metrics,
                "utility": score_row(metrics),
                "avg_gross_leverage": float(result.gross_leverage.mean()),
                "min_gross_leverage": float(result.gross_leverage.min()),
                "max_gross_leverage": float(result.gross_leverage.max()),
                "base_gross_leverage": base,
                "attack_gross_leverage": attack,
                "defend_gross_leverage": defend,
                "soft_drawdown": soft_dd,
                "hard_drawdown": hard_dd,
                "recent_loss_cut": recent_loss_cut,
            }
        )

    report = pd.DataFrame(rows).sort_values(
        ["utility", "return", "max_drawdown"], ascending=[False, False, True]
    )
    report.to_csv(args.output, index=False)
    print(report.head(25).to_string(index=False))
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
