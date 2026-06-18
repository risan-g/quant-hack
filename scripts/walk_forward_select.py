#!/usr/bin/env python3
"""Walk-forward strategy selection and adaptive-risk evaluation."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from quantbot.backtest.metrics import summarize_returns
from quantbot.research.portfolio import build_enriched_bars, build_unit_returns
from quantbot.research.selection import (
    score_candidates,
    score_candidates_robust,
    select_diversified_candidates,
    weights_from_scores,
)
from quantbot.risk.governor import AdaptiveRiskConfig, AdaptiveRiskGovernor


SPLITS = [
    ("early_to_middle", "2026-05-11", "2026-05-20", "2026-05-21", "2026-05-29"),
    ("middle_to_late", "2026-05-21", "2026-05-29", "2026-05-31", "2026-06-10"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--output", type=Path, default=Path("reports/walk_forward.csv"))
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--robust", action="store_true", help="Use daily-stability candidate scoring.")
    return parser.parse_args()


def slice_by_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    time = pd.to_datetime(df["time"], utc=True)
    mask = (time.dt.date >= pd.Timestamp(start).date()) & (
        time.dt.date <= pd.Timestamp(end).date()
    )
    return df[mask].copy()


def format_legs(legs: list[dict[str, float | str]]) -> str:
    return "; ".join(
        f"{leg['symbol']}:{leg['strategy']}:{float(leg['weight']):.3f}" for leg in legs
    )


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    bars = pd.read_parquet(args.bars)
    risk_config = AdaptiveRiskConfig(
        base_gross_leverage=7.0,
        attack_gross_leverage=10.0,
        defend_gross_leverage=1.0,
        max_gross_leverage=12.0,
        soft_drawdown=0.10,
        hard_drawdown=0.14,
        attack_drawdown=0.02,
        recent_loss_window=16,
        recent_loss_cut=-0.015,
        recovery_bars=8,
    )

    rows: list[dict[str, float | str]] = []
    for split_name, train_start, train_end, test_start, test_end in SPLITS:
        train_bars = slice_by_date(bars, train_start, train_end)
        test_bars = slice_by_date(bars, test_start, test_end)

        train_enriched = build_enriched_bars(train_bars)
        if args.robust:
            scores = score_candidates_robust(train_enriched, leverage=1.0)
        else:
            scores = score_candidates(train_enriched, leverage=1.0)
        selected = select_diversified_candidates(scores, top_n=args.top_n)
        legs = weights_from_scores(selected)

        test_enriched = build_enriched_bars(test_bars)
        unit_returns = build_unit_returns(test_enriched, legs).sum(axis=1)
        result = AdaptiveRiskGovernor(risk_config).run(unit_returns)
        metrics = summarize_returns(result.returns)

        rows.append(
            {
                "split": split_name,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "legs": format_legs(legs),
                **metrics,
                "final_equity": float(result.equity.iloc[-1]),
                "avg_gross_leverage": float(result.gross_leverage.mean()),
                "max_gross_leverage": float(result.gross_leverage.max()),
                "min_gross_leverage": float(result.gross_leverage.min()),
            }
        )

    report = pd.DataFrame(rows)
    report.to_csv(args.output, index=False)
    print(report.to_string(index=False))
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
