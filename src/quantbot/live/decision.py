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
        allowed = bool(regime_mask(group, leg.get("regime")).iloc[-1])
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
