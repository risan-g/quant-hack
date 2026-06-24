#!/usr/bin/env python3
"""Scan the live MT5 universe and build a candidate portfolio config."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quantbot.competition import ELIGIBLE_INSTRUMENTS
from quantbot.execution.sizing import load_symbol_specs
from quantbot.live.mt5_bridge import merge_historical_and_live_bars, read_mt5_live_bars_csv
from quantbot.research.portfolio import build_enriched_bars
from quantbot.research.selection import (
    CandidateScore,
    score_candidates_robust,
    select_diversified_candidates,
)


DEFAULT_EXCLUDED_SYMBOLS = {"XAUUSD"}
DEFAULT_RISK = {
    "base_gross_leverage": 0.80,
    "attack_gross_leverage": 0.80,
    "defend_gross_leverage": 0.35,
    "max_gross_leverage": 1.00,
    "soft_drawdown": 0.04,
    "hard_drawdown": 0.08,
    "attack_drawdown": 0.0,
    "recent_loss_window": 16,
    "recent_loss_cut": -0.006,
    "recovery_bars": 8,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--mt5-bars-csv", type=Path, required=True)
    parser.add_argument("--symbol-specs", type=Path, default=Path("configs/mt5_symbol_specs.yaml"))
    parser.add_argument("--output-config", type=Path, default=Path("configs/portfolio_scanner_candidate.yaml"))
    parser.add_argument("--output-report", type=Path, default=Path("reports/live_universe_scan.csv"))
    parser.add_argument("--assume-timezone", default="Europe/London")
    parser.add_argument("--top-n", type=int, default=4)
    parser.add_argument("--max-per-symbol", type=int, default=1)
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--max-spread-z", type=float, default=1.25)
    parser.add_argument("--min-utility", type=float, default=0.0)
    parser.add_argument("--max-symbol-weight", type=float, default=0.45)
    parser.add_argument("--leverage", type=float, default=1.0)
    parser.add_argument("--base-gross-leverage", type=float, default=0.80)
    parser.add_argument(
        "--exclude-symbol",
        action="append",
        default=sorted(DEFAULT_EXCLUDED_SYMBOLS),
        help="Symbol to exclude from candidate selection. Repeatable. Defaults to XAUUSD.",
    )
    return parser.parse_args()


def score_frame(scores: list[CandidateScore], selected: list[CandidateScore]) -> pd.DataFrame:
    selected_keys = {(score.symbol, score.strategy) for score in selected}
    rows: list[dict[str, float | str | bool]] = []
    for rank, score in enumerate(sorted(scores, key=lambda item: item.utility, reverse=True), start=1):
        rows.append(
            {
                "rank": rank,
                "selected": (score.symbol, score.strategy) in selected_keys,
                "symbol": score.symbol,
                "strategy": score.strategy,
                "utility": score.utility,
                "return": score.return_,
                "max_drawdown": score.max_drawdown,
                "sharpe": score.sharpe,
                "trades": score.trades,
            }
        )
    return pd.DataFrame(rows)


def candidate_symbols(
    historical: pd.DataFrame,
    live: pd.DataFrame,
    spec_symbols: set[str],
    excluded: set[str],
) -> set[str]:
    historical_symbols = set(historical["symbol"].astype(str).str.upper())
    live_symbols = set(live["symbol"].astype(str).str.upper())
    return (
        historical_symbols
        & live_symbols
        & spec_symbols
        & set(ELIGIBLE_INSTRUMENTS)
        - excluded
    )


def capped_weights_from_scores(
    scores: list[CandidateScore],
    *,
    max_symbol_weight: float,
) -> list[dict[str, float | str]]:
    max_symbol_weight = max(max_symbol_weight, 1.0 / len(scores))
    positive = [max(score.utility, 0.0) for score in scores]
    if sum(positive) <= 0:
        raw = [1.0 / len(scores)] * len(scores)
    else:
        total = sum(positive)
        raw = [value / total for value in positive]

    capped = [min(weight, max_symbol_weight) for weight in raw]
    free_indexes = {index for index, weight in enumerate(capped) if weight < max_symbol_weight}
    while free_indexes and sum(capped) < 1.0 - 1e-12:
        leftover = 1.0 - sum(capped)
        basis = sum(raw[index] for index in free_indexes)
        if basis <= 0:
            add_each = leftover / len(free_indexes)
            increments = {index: add_each for index in free_indexes}
        else:
            increments = {index: leftover * raw[index] / basis for index in free_indexes}

        changed = False
        for index in list(free_indexes):
            next_weight = min(max_symbol_weight, capped[index] + increments[index])
            if next_weight > capped[index]:
                changed = True
            capped[index] = next_weight
            if capped[index] >= max_symbol_weight - 1e-12:
                free_indexes.remove(index)
        if not changed:
            break

    total_capped = sum(capped)
    weights = [weight / total_capped for weight in capped]
    return [
        {"symbol": score.symbol, "strategy": score.strategy, "weight": weight}
        for score, weight in zip(scores, weights, strict=True)
    ]


def build_config(
    selected: list[CandidateScore],
    *,
    max_spread_z: float,
    base_gross_leverage: float,
    max_symbol_weight: float,
) -> dict[str, Any]:
    legs = capped_weights_from_scores(selected, max_symbol_weight=max_symbol_weight)
    for leg in legs:
        leg["regime"] = {"max_spread_z": max_spread_z}

    risk = dict(DEFAULT_RISK)
    risk["base_gross_leverage"] = base_gross_leverage
    risk["attack_gross_leverage"] = base_gross_leverage
    risk["max_gross_leverage"] = max(1.0, base_gross_leverage)

    return {
        "legs": legs,
        "risk": risk,
    }


def main() -> None:
    args = parse_args()
    excluded = {symbol.upper() for symbol in args.exclude_symbol}

    historical = pd.read_parquet(args.historical)
    historical["symbol"] = historical["symbol"].astype(str).str.upper()
    live = read_mt5_live_bars_csv(args.mt5_bars_csv, assume_timezone=args.assume_timezone)
    live["symbol"] = live["symbol"].astype(str).str.upper()
    specs = load_symbol_specs(args.symbol_specs)

    symbols = candidate_symbols(historical, live, set(specs), excluded)
    if not symbols:
        raise SystemExit("No candidate symbols have historical data, live MT5 data, and MT5 specs.")

    merged = merge_historical_and_live_bars(
        historical[historical["symbol"].isin(symbols)],
        live[live["symbol"].isin(symbols)],
    )
    enriched = build_enriched_bars(merged)
    scores = score_candidates_robust(enriched, leverage=args.leverage)
    scores = [score for score in scores if score.symbol in symbols]
    positive_scores = [score for score in scores if score.utility > args.min_utility]
    selected = select_diversified_candidates(
        positive_scores,
        top_n=args.top_n,
        max_per_symbol=args.max_per_symbol,
        min_trades=args.min_trades,
    )
    if not selected:
        raise SystemExit("No candidates passed the scanner filters.")

    config = build_config(
        selected,
        max_spread_z=args.max_spread_z,
        base_gross_leverage=args.base_gross_leverage,
        max_symbol_weight=args.max_symbol_weight,
    )

    args.output_config.parent.mkdir(parents=True, exist_ok=True)
    args.output_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    report = score_frame(scores, selected)
    report.to_csv(args.output_report, index=False)

    print("LIVE_UNIVERSE")
    print("  scanned:", ", ".join(sorted(symbols)))
    print("  excluded:", ", ".join(sorted(excluded)) if excluded else "none")
    print()
    print("SELECTED")
    for leg in config["legs"]:
        score = next(
            item for item in selected if item.symbol == leg["symbol"] and item.strategy == leg["strategy"]
        )
        print(
            f"  {leg['symbol']} {leg['strategy']} weight={float(leg['weight']):.3f} "
            f"utility={score.utility:.4f} sharpe={score.sharpe:.4f} trades={score.trades:.0f}"
        )
    print()
    print(f"Wrote {args.output_config}")
    print(f"Wrote {args.output_report}")


if __name__ == "__main__":
    main()
