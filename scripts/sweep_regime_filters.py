#!/usr/bin/env python3
"""Sweep simple per-family regime filters on the curated portfolio."""

from __future__ import annotations

import argparse
import copy
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
    parser.add_argument("--output", type=Path, default=Path("reports/regime_sweep.csv"))
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def apply_variant(config: dict[str, Any], variant: str) -> dict[str, Any]:
    trial = copy.deepcopy(config)
    for leg in trial["legs"]:
        strategy = str(leg["strategy"])
        if variant == "none":
            leg.pop("regime", None)
        elif variant == "spread_only":
            leg["regime"] = {"max_spread_z": 3.0}
        elif variant == "mr_trend_guard":
            if strategy.startswith("mean_reversion"):
                leg["regime"] = {"max_trend_strength": 9.0, "max_spread_z": 3.0}
            else:
                leg["regime"] = {"max_spread_z": 3.0}
        elif variant == "momentum_spread_guard":
            if strategy.startswith(("momentum", "breakout")):
                leg["regime"] = {"max_spread_z": 2.0}
            else:
                leg["regime"] = {"max_spread_z": 3.0}
        elif variant == "loose_vol":
            if strategy.startswith(("momentum", "breakout")):
                leg["regime"] = {
                    "require_expanding_vol": True,
                    "min_vol_ratio": 0.65,
                    "max_spread_z": 3.5,
                }
            else:
                leg["regime"] = {
                    "avoid_expanding_vol": True,
                    "max_vol_ratio": 1.8,
                    "max_spread_z": 3.5,
                }
        else:
            raise ValueError(f"Unknown variant: {variant}")
    return trial


def score(metrics: dict[str, float]) -> float:
    return metrics["return"] - 1.25 * metrics["max_drawdown"] + 3.0 * metrics["sharpe"]


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    base_config = load_config(args.config)
    bars = pd.read_parquet(args.bars)
    enriched = build_enriched_bars(bars)

    rows: list[dict[str, float | str]] = []
    for variant in ("none", "spread_only", "mr_trend_guard", "momentum_spread_guard", "loose_vol"):
        config = apply_variant(base_config, variant)
        aligned = build_unit_returns(enriched, config["legs"])
        unit_returns = aligned.sum(axis=1)
        result = AdaptiveRiskGovernor(AdaptiveRiskConfig(**config["risk"])).run(unit_returns)
        metrics = summarize_returns(result.returns)
        rows.append(
            {
                "variant": variant,
                **metrics,
                "utility": score(metrics),
                "final_equity": float(result.equity.iloc[-1]),
                "avg_gross_leverage": float(result.gross_leverage.mean()),
                "max_gross_leverage": float(result.gross_leverage.max()),
                "min_gross_leverage": float(result.gross_leverage.min()),
            }
        )

    report = pd.DataFrame(rows).sort_values(
        ["utility", "return", "max_drawdown"], ascending=[False, False, True]
    )
    report.to_csv(args.output, index=False)
    print(report.to_string(index=False))
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
