"""Generate executable trade decisions from latest bars and portfolio config."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from quantbot.research.portfolio import build_enriched_bars, build_unit_returns
from quantbot.research.signals import regime_mask
from quantbot.risk.governor import AdaptiveRiskConfig, AdaptiveRiskGovernor


Side = Literal["long", "short", "flat"]


class DecisionLeg(BaseModel):
    symbol: str
    strategy: str
    side: Side
    raw_signal: float
    allowed_by_regime: bool
    weight: float
    mid_price: float
    spread_fraction: float
    spread_z: float | None
    target_notional_usd: float
    target_leverage: float


class DecisionReport(BaseModel):
    timestamp: str
    config_name: str
    equity_usd: float
    peak_equity_usd: float
    drawdown: float
    gross_leverage: float
    cooldown_bars: int
    active_legs: int
    net_directional_leverage: float
    gross_target_notional_usd: float
    legs: list[DecisionLeg] = Field(default_factory=list)


@dataclass(frozen=True)
class BuiltDecisionInputs:
    enriched: pd.DataFrame
    unit_returns: pd.Series


def side_from_signal(signal: float) -> Side:
    if signal > 0:
        return "long"
    if signal < 0:
        return "short"
    return "flat"


def strategy_window(strategy: str) -> int | None:
    try:
        return int(strategy.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        return None


def m15_trend_bias(
    group: pd.DataFrame,
    fast_span: int = 12,
    slow_span: int = 48,
) -> pd.Series:
    """Approximate higher-timeframe trend from M5 bars resampled to M15."""
    if group.empty:
        return pd.Series(0.0, index=group.index)

    indexed = group.sort_values("time").set_index("time")
    m15_close = indexed["mid_close"].resample("15min").last().dropna()
    if len(m15_close) < slow_span:
        return pd.Series(0.0, index=group.index)

    fast = m15_close.ewm(span=fast_span, adjust=False, min_periods=fast_span).mean()
    slow = m15_close.ewm(span=slow_span, adjust=False, min_periods=slow_span).mean()
    bias = (fast - slow).apply(lambda value: 1.0 if value > 0 else (-1.0 if value < 0 else 0.0))
    aligned = bias.reindex(indexed.index, method="ffill").fillna(0.0)
    return pd.Series(aligned.to_numpy(), index=group.sort_values("time").index)


def high_conviction_mask(group: pd.DataFrame, strategy: str, rules: dict[str, Any] | None) -> pd.Series:
    """Return True where a configured signal is strong enough to execute live."""
    mask = pd.Series(True, index=group.index)
    if not rules:
        return mask

    window = strategy_window(strategy)
    if window is None:
        return mask

    if "min_abs_move_strength" in rules and strategy.startswith(
        ("momentum", "breakout", "m15_momentum")
    ):
        column = (
            f"m15_move_strength_{window}"
            if strategy.startswith("m15_momentum")
            else f"move_strength_{window}"
        )
        if column in group:
            mask &= group[column].fillna(0.0) >= float(rules["min_abs_move_strength"])

    if "min_abs_reversion_z" in rules and strategy.startswith("mean_reversion"):
        column = f"mean_reversion_z_{window}"
        if column in group:
            mask &= group[column].abs().fillna(0.0) >= float(rules["min_abs_reversion_z"])

    if "min_tick_volume_mult" in rules and "ticks" in group:
        median_ticks = group["ticks"].rolling(20).median()
        mask &= group["ticks"].fillna(0.0) >= median_ticks.fillna(float("inf")) * float(
            rules["min_tick_volume_mult"]
        )

    if "min_vol_ratio" in rules and "vol_ratio_16_64" in group:
        mask &= group["vol_ratio_16_64"].fillna(0.0) >= float(rules["min_vol_ratio"])

    if "session_utc" in rules:
        session_mask = pd.Series(False, index=group.index)
        hours = pd.to_datetime(group["time"], utc=True).dt.hour
        for window in rules["session_utc"]:
            start, end = int(window[0]), int(window[1])
            if start <= end:
                session_mask |= (hours >= start) & (hours < end)
            else:
                session_mask |= (hours >= start) | (hours < end)
        mask &= session_mask

    if rules.get("require_m15_trend_align"):
        bias = m15_trend_bias(
            group,
            fast_span=int(rules.get("m15_ema_fast", 12)),
            slow_span=int(rules.get("m15_ema_slow", 48)),
        )
        signal = group[strategy].fillna(0.0)
        mask &= (signal == 0.0) | (bias == 0.0) | (signal * bias > 0.0)

    return mask


def build_decision_inputs(bars: pd.DataFrame, legs: list[dict[str, Any]]) -> BuiltDecisionInputs:
    enriched = build_enriched_bars(bars)
    aligned = build_unit_returns(enriched, legs)
    return BuiltDecisionInputs(enriched=enriched, unit_returns=aligned.sum(axis=1))


def generate_decision_report(
    bars: pd.DataFrame,
    config: dict[str, Any],
    config_name: str,
    initial_equity: float = 1_000_000.0,
) -> DecisionReport:
    inputs = build_decision_inputs(bars, config["legs"])
    governor = AdaptiveRiskGovernor(AdaptiveRiskConfig(**config["risk"]))
    risk_state = governor.current_state(inputs.unit_returns, initial_equity=initial_equity)

    latest_time = pd.to_datetime(inputs.enriched["time"], utc=True).max()
    decision_legs: list[DecisionLeg] = []
    net_directional_leverage = 0.0
    gross_target_notional = 0.0

    for leg in config["legs"]:
        symbol = str(leg["symbol"])
        strategy = str(leg["strategy"])
        weight = float(leg["weight"])
        group = inputs.enriched[inputs.enriched["symbol"] == symbol].sort_values("time")
        if group.empty:
            raise ValueError(f"No data available for {symbol}")
        latest = group.iloc[-1]
        raw_signal = float(latest[strategy])
        rules = leg.get("regime")
        allowed = bool((regime_mask(group, rules) & high_conviction_mask(group, strategy, rules)).iloc[-1])
        filtered_signal = raw_signal if allowed else 0.0
        target_leverage = risk_state.gross_leverage * weight * filtered_signal
        target_notional = risk_state.equity * target_leverage
        gross_target_notional += abs(target_notional)
        net_directional_leverage += target_leverage

        spread_z = latest.get("spread_z_64")
        decision_legs.append(
            DecisionLeg(
                symbol=symbol,
                strategy=strategy,
                side=side_from_signal(filtered_signal),
                raw_signal=raw_signal,
                allowed_by_regime=allowed,
                weight=weight,
                mid_price=float(latest["mid_close"]),
                spread_fraction=float(latest["spread_frac"]),
                spread_z=None if pd.isna(spread_z) else float(spread_z),
                target_notional_usd=target_notional,
                target_leverage=target_leverage,
            )
        )

    active_legs = sum(1 for leg in decision_legs if leg.side != "flat")
    return DecisionReport(
        timestamp=latest_time.isoformat(),
        config_name=config_name,
        equity_usd=risk_state.equity,
        peak_equity_usd=risk_state.peak_equity,
        drawdown=risk_state.drawdown,
        gross_leverage=risk_state.gross_leverage,
        cooldown_bars=risk_state.cooldown_bars,
        active_legs=active_legs,
        net_directional_leverage=net_directional_leverage,
        gross_target_notional_usd=gross_target_notional,
        legs=decision_legs,
    )


def rescale_decision_report(report: DecisionReport, execution_equity_usd: float) -> DecisionReport:
    """Rescale target notionals to actual execution equity while preserving leverage."""
    legs = [
        leg.model_copy(
            update={"target_notional_usd": execution_equity_usd * leg.target_leverage}
        )
        for leg in report.legs
    ]
    return report.model_copy(
        update={
            "equity_usd": execution_equity_usd,
            "gross_target_notional_usd": sum(abs(leg.target_notional_usd) for leg in legs),
            "legs": legs,
        }
    )
