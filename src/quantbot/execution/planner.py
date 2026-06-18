"""Convert decision reports into execution plans."""

from __future__ import annotations

from quantbot.execution.models import ExecutionPlan, OrderIntent, OrderSide
from quantbot.live.decision import DecisionReport


def plan_from_decision(
    report: DecisionReport,
    min_notional_usd: float = 10_000.0,
) -> ExecutionPlan:
    orders: list[OrderIntent] = []
    for leg in report.legs:
        if leg.side == "flat":
            continue
        notional = abs(leg.target_notional_usd)
        if notional < min_notional_usd:
            continue
        side = OrderSide.BUY if leg.target_notional_usd > 0 else OrderSide.SELL
        orders.append(
            OrderIntent(
                symbol=leg.symbol,
                side=side,
                notional_usd=notional,
                target_leverage=leg.target_leverage,
                reason=(
                    f"{leg.strategy} {leg.side}; regime_allowed={leg.allowed_by_regime}; "
                    f"spread_z={leg.spread_z}"
                ),
            )
        )

    return ExecutionPlan(
        timestamp=report.timestamp,
        equity_usd=report.equity_usd,
        gross_leverage=report.gross_leverage,
        orders=orders,
    )
