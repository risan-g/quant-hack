"""Simple signal families for first-pass research."""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_strategy_positions(group: pd.DataFrame) -> pd.DataFrame:
    group = group.sort_values("time").copy()
    close = group["mid_close"]
    ret = close.pct_change()
    group["asset_return"] = ret
    group["spread_frac"] = group["spread_mean"] / close

    for window in (4, 8, 16, 32):
        mom = close.pct_change(window)
        group[f"momentum_{window}"] = np.sign(mom).fillna(0.0)

        rolling_high = close.shift(1).rolling(window).max()
        rolling_low = close.shift(1).rolling(window).min()
        breakout = pd.Series(0.0, index=group.index)
        breakout = breakout.mask(close > rolling_high, 1.0)
        breakout = breakout.mask(close < rolling_low, -1.0)
        group[f"breakout_{window}"] = breakout.fillna(0.0)

        rolling_mean = close.shift(1).rolling(window).mean()
        rolling_std = close.shift(1).rolling(window).std(ddof=0)
        zscore = (close - rolling_mean) / rolling_std.replace(0.0, np.nan)
        mean_revert = pd.Series(0.0, index=group.index)
        mean_revert = mean_revert.mask(zscore > 1.0, -1.0)
        mean_revert = mean_revert.mask(zscore < -1.0, 1.0)
        group[f"mean_reversion_{window}"] = mean_revert.fillna(0.0)

    return group


def strategy_returns(df: pd.DataFrame, position_col: str, leverage: float) -> pd.Series:
    position = df[position_col].clip(-1.0, 1.0)
    previous_position = position.shift(1).fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    spread_cost = turnover * df["spread_frac"].fillna(0.0) / 2.0
    return leverage * (previous_position * df["asset_return"].fillna(0.0) - spread_cost)
