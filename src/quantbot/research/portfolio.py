"""Portfolio construction helpers for research scripts."""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantbot.research.signals import add_strategy_positions, filtered_strategy_returns, strategy_returns


def build_enriched_bars(bars: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol, group in bars.groupby("symbol"):
        enriched = add_strategy_positions(group.drop(columns=["symbol"]))
        enriched.insert(0, "symbol", symbol)
        frames.append(enriched)
    return pd.concat(frames, ignore_index=True)


def build_unit_returns(enriched: pd.DataFrame, legs: list[dict[str, Any]]) -> pd.DataFrame:
    total_weight = sum(float(leg["weight"]) for leg in legs)
    if abs(total_weight - 1.0) > 1e-9:
        raise ValueError(f"Portfolio weights must sum to 1.0, got {total_weight}")

    leg_returns: list[pd.Series] = []
    for leg in legs:
        symbol = leg["symbol"]
        strategy = leg["strategy"]
        weight = float(leg["weight"])
        group = enriched[enriched["symbol"] == symbol].copy()
        if group.empty:
            raise ValueError(f"No bars found for {symbol}")
        if strategy not in group.columns:
            raise ValueError(f"Strategy {strategy} missing for {symbol}")
        regime = leg.get("regime")
        if regime:
            returns = filtered_strategy_returns(group, strategy, leverage=weight, rules=regime)
        else:
            returns = strategy_returns(group, strategy, leverage=weight)
        returns.index = pd.to_datetime(group["time"], utc=True)
        returns.name = f"{symbol}_{strategy}"
        leg_returns.append(returns)

    return pd.concat(leg_returns, axis=1, sort=False).sort_index().fillna(0.0)
