"""Adaptive portfolio risk governor."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class AdaptiveRiskConfig:
    """Rules for scaling portfolio gross leverage through time."""

    base_gross_leverage: float = 6.0
    attack_gross_leverage: float = 8.0
    defend_gross_leverage: float = 2.0
    max_gross_leverage: float = 12.0
    soft_drawdown: float = 0.08
    hard_drawdown: float = 0.16
    attack_drawdown: float = 0.02
    recent_loss_window: int = 16
    recent_loss_cut: float = -0.015
    recovery_bars: int = 8

    def __post_init__(self) -> None:
        if self.hard_drawdown <= self.soft_drawdown:
            raise ValueError("hard_drawdown must exceed soft_drawdown")
        if self.max_gross_leverage < self.attack_gross_leverage:
            raise ValueError("max_gross_leverage must be >= attack_gross_leverage")


@dataclass(frozen=True)
class AdaptiveRiskResult:
    returns: pd.Series
    equity: pd.Series
    gross_leverage: pd.Series
    drawdown: pd.Series


@dataclass(frozen=True)
class RiskState:
    equity: float
    peak_equity: float
    drawdown: float
    gross_leverage: float
    cooldown_bars: int


class AdaptiveRiskGovernor:
    """Apply competition-aware gross leverage scaling to raw portfolio returns."""

    def __init__(self, config: AdaptiveRiskConfig) -> None:
        self.config = config

    def run(
        self,
        raw_unit_returns: pd.Series,
        initial_equity: float = 1_000_000.0,
    ) -> AdaptiveRiskResult:
        clean = raw_unit_returns.fillna(0.0)
        equity_values: list[float] = []
        return_values: list[float] = []
        leverage_values: list[float] = []
        drawdown_values: list[float] = []

        equity = initial_equity
        peak = initial_equity
        cooldown = 0
        realized_returns: list[float] = []

        for raw_return in clean:
            peak = max(peak, equity)
            drawdown = 0.0 if peak <= 0 else (peak - equity) / peak
            leverage = self._leverage_for_state(drawdown, realized_returns, cooldown)

            scaled_return = float(raw_return) * leverage
            equity *= 1.0 + scaled_return

            if scaled_return < 0:
                recent = realized_returns[-self.config.recent_loss_window :]
                if sum(recent) + scaled_return <= self.config.recent_loss_cut:
                    cooldown = self.config.recovery_bars
            else:
                cooldown = max(0, cooldown - 1)

            realized_returns.append(scaled_return)
            return_values.append(scaled_return)
            equity_values.append(equity)
            leverage_values.append(leverage)
            drawdown_values.append(drawdown)

        index = clean.index
        return AdaptiveRiskResult(
            returns=pd.Series(return_values, index=index, name="portfolio_return"),
            equity=pd.Series(equity_values, index=index, name="equity"),
            gross_leverage=pd.Series(leverage_values, index=index, name="gross_leverage"),
            drawdown=pd.Series(drawdown_values, index=index, name="drawdown"),
        )

    def current_state(
        self,
        raw_unit_returns: pd.Series,
        initial_equity: float = 1_000_000.0,
    ) -> RiskState:
        """Return risk state for the next decision after realized returns."""
        clean = raw_unit_returns.fillna(0.0)
        equity = initial_equity
        peak = initial_equity
        cooldown = 0
        realized_returns: list[float] = []

        for raw_return in clean:
            peak = max(peak, equity)
            drawdown = 0.0 if peak <= 0 else (peak - equity) / peak
            leverage = self._leverage_for_state(drawdown, realized_returns, cooldown)
            scaled_return = float(raw_return) * leverage
            equity *= 1.0 + scaled_return

            if scaled_return < 0:
                recent = realized_returns[-self.config.recent_loss_window :]
                if sum(recent) + scaled_return <= self.config.recent_loss_cut:
                    cooldown = self.config.recovery_bars
            else:
                cooldown = max(0, cooldown - 1)

            realized_returns.append(scaled_return)

        peak = max(peak, equity)
        drawdown = 0.0 if peak <= 0 else (peak - equity) / peak
        leverage = self._leverage_for_state(drawdown, realized_returns, cooldown)
        return RiskState(
            equity=equity,
            peak_equity=peak,
            drawdown=drawdown,
            gross_leverage=leverage,
            cooldown_bars=cooldown,
        )

    def _leverage_for_state(
        self,
        drawdown: float,
        realized_returns: list[float],
        cooldown: int,
    ) -> float:
        cfg = self.config
        if drawdown >= cfg.hard_drawdown:
            return 0.0

        if drawdown >= cfg.soft_drawdown:
            progress = (drawdown - cfg.soft_drawdown) / (cfg.hard_drawdown - cfg.soft_drawdown)
            leverage = cfg.base_gross_leverage - progress * (
                cfg.base_gross_leverage - cfg.defend_gross_leverage
            )
        elif drawdown <= cfg.attack_drawdown:
            leverage = cfg.attack_gross_leverage
        else:
            leverage = cfg.base_gross_leverage

        if cooldown > 0:
            leverage = min(leverage, cfg.defend_gross_leverage)

        if len(realized_returns) >= cfg.recent_loss_window:
            recent = sum(realized_returns[-cfg.recent_loss_window :])
            if recent <= cfg.recent_loss_cut:
                leverage = min(leverage, cfg.defend_gross_leverage)

        return max(0.0, min(leverage, cfg.max_gross_leverage))
