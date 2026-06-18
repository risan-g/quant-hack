"""Backtest metrics aligned with competition scoring."""

from __future__ import annotations

import numpy as np
import pandas as pd


def equity_curve(returns: pd.Series, initial_equity: float = 1.0) -> pd.Series:
    return initial_equity * (1.0 + returns.fillna(0.0)).cumprod()


def max_drawdown_from_equity(equity: pd.Series) -> float:
    peak = equity.cummax()
    drawdown = (peak - equity) / peak
    return float(drawdown.max()) if len(drawdown) else 0.0


def sharpe(returns: pd.Series) -> float:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return 0.0
    std = clean.std(ddof=0)
    if std == 0 or np.isnan(std):
        return 0.0
    return float(clean.mean() / std)


def summarize_returns(returns: pd.Series) -> dict[str, float]:
    curve = equity_curve(returns)
    return {
        "periods": float(returns.dropna().shape[0]),
        "return": float(curve.iloc[-1] - 1.0) if len(curve) else 0.0,
        "max_drawdown": max_drawdown_from_equity(curve),
        "sharpe": sharpe(returns),
        "mean_return": float(returns.mean()) if len(returns) else 0.0,
        "std_return": float(returns.std(ddof=0)) if len(returns) else 0.0,
    }
