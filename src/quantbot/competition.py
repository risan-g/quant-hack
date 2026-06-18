"""Competition constants and scoring helpers."""

from __future__ import annotations

from dataclasses import dataclass


INITIAL_EQUITY_USD = 1_000_000.0

ELIGIBLE_INSTRUMENTS = {
    "AUDUSD",
    "EURCHF",
    "EURGBP",
    "EURUSD",
    "GBPUSD",
    "USDCAD",
    "USDCHF",
    "USDJPY",
    "XAGUSD",
    "XAUUSD",
    "BARUSD",
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "XRPUSD",
}


@dataclass(frozen=True)
class CompetitionScore:
    """Proxy score using already-normalized rank components."""

    return_rank: float
    drawdown_rank: float
    sharpe_rank: float
    risk_discipline: float

    @property
    def final_score(self) -> float:
        return (
            0.70 * self.return_rank
            + 0.15 * self.drawdown_rank
            + 0.10 * self.sharpe_rank
            + 0.05 * self.risk_discipline
        )


def max_drawdown(equity: list[float]) -> float:
    """Return peak-to-trough drawdown as a fraction of peak equity."""
    peak = float("-inf")
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def sharpe_from_returns(returns: list[float]) -> float:
    """Competition-style non-annualized Sharpe from interval returns."""
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((ret - mean) ** 2 for ret in returns) / len(returns)
    std = variance**0.5
    if std == 0:
        return 0.0
    return mean / std
