"""Strategy selection utilities."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantbot.backtest.metrics import summarize_returns
from quantbot.research.signals import strategy_returns


@dataclass(frozen=True)
class CandidateScore:
    symbol: str
    strategy: str
    utility: float
    return_: float
    max_drawdown: float
    sharpe: float
    trades: float


def strategy_columns(df: pd.DataFrame) -> list[str]:
    return [
        column
        for column in df.columns
        if column.startswith(("momentum_", "breakout_", "mean_reversion_"))
    ]


def tournament_utility(metrics: dict[str, float]) -> float:
    """Rough utility for choosing candidates before true rank information exists."""
    return metrics["return"] - 1.25 * metrics["max_drawdown"] + 3.0 * metrics["sharpe"]


def score_candidates(enriched: pd.DataFrame, leverage: float = 1.0) -> list[CandidateScore]:
    scores: list[CandidateScore] = []
    columns = strategy_columns(enriched)
    for symbol, group in enriched.groupby("symbol"):
        for strategy in columns:
            if strategy not in group:
                continue
            returns = strategy_returns(group, strategy, leverage=leverage)
            metrics = summarize_returns(returns)
            trades = float((group[strategy].diff().abs().fillna(group[strategy].abs()) > 0).sum())
            scores.append(
                CandidateScore(
                    symbol=symbol,
                    strategy=strategy,
                    utility=tournament_utility(metrics),
                    return_=metrics["return"],
                    max_drawdown=metrics["max_drawdown"],
                    sharpe=metrics["sharpe"],
                    trades=trades,
                )
            )
    return scores


def score_candidates_robust(
    enriched: pd.DataFrame,
    leverage: float = 1.0,
) -> list[CandidateScore]:
    """Score candidates using full-period and daily stability metrics."""
    scores: list[CandidateScore] = []
    columns = strategy_columns(enriched)
    for symbol, group in enriched.groupby("symbol"):
        group = group.copy()
        group["date"] = pd.to_datetime(group["time"], utc=True).dt.date
        for strategy in columns:
            if strategy not in group:
                continue
            returns = strategy_returns(group, strategy, leverage=leverage)
            full_metrics = summarize_returns(returns)
            daily_utilities: list[float] = []
            daily_returns: list[float] = []
            daily_drawdowns: list[float] = []
            for _, daily_group in group.groupby("date"):
                daily_returns_series = strategy_returns(daily_group, strategy, leverage=leverage)
                daily_metrics = summarize_returns(daily_returns_series)
                daily_utilities.append(tournament_utility(daily_metrics))
                daily_returns.append(daily_metrics["return"])
                daily_drawdowns.append(daily_metrics["max_drawdown"])

            if daily_utilities:
                median_daily_utility = float(pd.Series(daily_utilities).median())
                worst_daily_return = min(daily_returns)
                worst_daily_drawdown = max(daily_drawdowns)
            else:
                median_daily_utility = 0.0
                worst_daily_return = 0.0
                worst_daily_drawdown = 0.0

            full_utility = tournament_utility(full_metrics)
            robust_utility = (
                0.35 * full_utility
                + 0.65 * median_daily_utility
                + 2.0 * min(worst_daily_return, 0.0)
                - 0.50 * worst_daily_drawdown
            )
            trades = float((group[strategy].diff().abs().fillna(group[strategy].abs()) > 0).sum())
            scores.append(
                CandidateScore(
                    symbol=symbol,
                    strategy=strategy,
                    utility=robust_utility,
                    return_=full_metrics["return"],
                    max_drawdown=full_metrics["max_drawdown"],
                    sharpe=full_metrics["sharpe"],
                    trades=trades,
                )
            )
    return scores


def select_diversified_candidates(
    scores: list[CandidateScore],
    top_n: int,
    max_per_symbol: int = 1,
    min_trades: int = 20,
) -> list[CandidateScore]:
    selected: list[CandidateScore] = []
    symbol_counts: dict[str, int] = {}
    ranked = sorted(scores, key=lambda item: item.utility, reverse=True)
    for score in ranked:
        if score.trades < min_trades:
            continue
        if symbol_counts.get(score.symbol, 0) >= max_per_symbol:
            continue
        selected.append(score)
        symbol_counts[score.symbol] = symbol_counts.get(score.symbol, 0) + 1
        if len(selected) >= top_n:
            break
    return selected


def weights_from_scores(scores: list[CandidateScore]) -> list[dict[str, float | str]]:
    positive = [max(score.utility, 0.0) for score in scores]
    if sum(positive) <= 0:
        weight = 1.0 / len(scores)
        return [
            {"symbol": score.symbol, "strategy": score.strategy, "weight": weight}
            for score in scores
        ]
    total = sum(positive)
    return [
        {
            "symbol": score.symbol,
            "strategy": score.strategy,
            "weight": positive_score / total,
        }
        for score, positive_score in zip(scores, positive, strict=True)
    ]
