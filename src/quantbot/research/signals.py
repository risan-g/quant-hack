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
    group["realized_vol_16"] = ret.rolling(16).std(ddof=0)
    group["realized_vol_64"] = ret.rolling(64).std(ddof=0)
    group["vol_ratio_16_64"] = group["realized_vol_16"] / group["realized_vol_64"].replace(0.0, np.nan)
    group["trend_strength_32"] = close.pct_change(32).abs() / group["realized_vol_16"].replace(
        0.0, np.nan
    )
    group["spread_z_64"] = (
        group["spread_frac"] - group["spread_frac"].rolling(64).mean()
    ) / group["spread_frac"].rolling(64).std(ddof=0).replace(0.0, np.nan)

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


def regime_mask(df: pd.DataFrame, rules: dict[str, float | str | bool] | None) -> pd.Series:
    """Return True where a leg is allowed to trade."""
    mask = pd.Series(True, index=df.index)
    if not rules:
        return mask

    if rules.get("require_expanding_vol"):
        mask &= df["vol_ratio_16_64"].fillna(0.0) >= float(rules.get("min_vol_ratio", 1.0))

    if rules.get("avoid_expanding_vol"):
        mask &= df["vol_ratio_16_64"].fillna(float("inf")) <= float(rules.get("max_vol_ratio", 1.4))

    if "min_trend_strength" in rules:
        mask &= df["trend_strength_32"].fillna(0.0) >= float(rules["min_trend_strength"])

    if "max_trend_strength" in rules:
        mask &= df["trend_strength_32"].fillna(float("inf")) <= float(rules["max_trend_strength"])

    if "max_spread_z" in rules:
        mask &= df["spread_z_64"].fillna(0.0) <= float(rules["max_spread_z"])

    return mask


def filtered_strategy_returns(
    df: pd.DataFrame,
    position_col: str,
    leverage: float,
    rules: dict[str, float | str | bool] | None,
) -> pd.Series:
    work = df.copy()
    filtered_col = f"{position_col}_filtered"
    work[filtered_col] = work[position_col].where(regime_mask(work, rules), 0.0)
    return strategy_returns(work, filtered_col, leverage)
