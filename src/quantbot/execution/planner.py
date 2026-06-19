"""Convert decision reports into execution plans."""

from __future__ import annotations

from quantbot.execution.models import ExecutionPlan, OrderIntent, OrderSide
from quantbot.execution.sizing import SymbolSpec, lots_for_notional_usd
from quantbot.live.decision import DecisionReport


def plan_from_decision(
    report: DecisionReport,
    min_notional_usd: float = 10_000.0,
    symbol_specs: dict[str, SymbolSpec] | None = None,
) -> ExecutionPlan:
    orders: list[OrderIntent] = []
    for leg in report.legs:
        if leg.side == "flat":
            continue
        notional = abs(leg.target_notional_usd)
        if notional < min_notional_usd:
            continue
        side = OrderSide.BUY if leg.target_notional_usd > 0 else OrderSide.SELL
        volume_lots = None
        if symbol_specs is not None:
            spec = symbol_specs.get(leg.symbol)
            if spec is None:
                raise ValueError(f"Missing symbol spec for {leg.symbol}")
            volume_lots = lots_for_notional_usd(spec, notional, leg.mid_price)
            if volume_lots <= 0:
                continue
        orders.append(
            OrderIntent(
                symbol=leg.symbol,
                side=side,
                notional_usd=notional,
                volume_lots=volume_lots,
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
