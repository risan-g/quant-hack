#!/usr/bin/env python3
"""Evaluate the adaptive portfolio over calendar subperiods."""

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
    parser.add_argument("--output", type=Path, default=Path("reports/period_evaluation.csv"))
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def period_label(timestamp: pd.Timestamp) -> str:
    date = timestamp.date().isoformat()
    if date <= "2026-05-20":
        return "early_2026-05-11_2026-05-20"
    if date <= "2026-05-29":
        return "middle_2026-05-21_2026-05-29"
    return "late_2026-05-31_2026-06-10"


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    config = load_config(args.config)
    bars = pd.read_parquet(args.bars)
    enriched = build_enriched_bars(bars)
    aligned = build_unit_returns(enriched, config["legs"])
    unit_returns = aligned.sum(axis=1)

    risk_config = AdaptiveRiskConfig(**config["risk"])
    rows: list[dict[str, float | str]] = []
    for label, period_returns in unit_returns.groupby(unit_returns.index.map(period_label)):
        result = AdaptiveRiskGovernor(risk_config).run(period_returns)
        metrics = summarize_returns(result.returns)
        rows.append(
            {
                "period": label,
                **metrics,
                "final_equity": float(result.equity.iloc[-1]),
                "avg_gross_leverage": float(result.gross_leverage.mean()),
                "max_gross_leverage": float(result.gross_leverage.max()),
                "min_gross_leverage": float(result.gross_leverage.min()),
            }
        )

    report = pd.DataFrame(rows).sort_values("period")
    report.to_csv(args.output, index=False)
    print(report.to_string(index=False))
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
