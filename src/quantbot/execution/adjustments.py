"""Translate target execution plans into netting-mode adjustment orders."""

from __future__ import annotations

from pydantic import BaseModel, Field

from quantbot.execution.models import ExecutionPlan, OrderIntent, OrderSide, OrderType


class CurrentPosition(BaseModel):
    symbol: str
    side: OrderSide
    volume_lots: float = Field(gt=0)
    price_open: float | None = None
    price_current: float | None = None
    profit: float | None = None

    @property
    def signed_volume_lots(self) -> float:
        if self.side == OrderSide.BUY:
            return self.volume_lots
        return -self.volume_lots


def signed_target_volume(order: OrderIntent) -> float:
    if order.volume_lots is None:
        raise ValueError(f"Order for {order.symbol} has no MT5 lot volume")
    if order.side == OrderSide.BUY:
        return order.volume_lots
    return -order.volume_lots


def adjustment_orders_from_positions(
    target: ExecutionPlan,
    current_positions: list[CurrentPosition],
    min_volume_lots: float = 0.01,
) -> ExecutionPlan:
    """Return MT5 netting-mode orders needed to move current positions to target."""
    current_by_symbol = {
        position.symbol.upper(): position.signed_volume_lots for position in current_positions
    }
    target_by_symbol = {
        order.symbol.upper(): signed_target_volume(order)
        for order in target.orders
        if order.volume_lots is not None
    }

    adjustments: list[OrderIntent] = []
    for symbol in sorted(set(current_by_symbol) | set(target_by_symbol)):
        current_volume = current_by_symbol.get(symbol, 0.0)
        target_volume = target_by_symbol.get(symbol, 0.0)
        delta = round(target_volume - current_volume, 2)
        if abs(delta) < min_volume_lots:
            continue

        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        target_order = next((order for order in target.orders if order.symbol.upper() == symbol), None)
        reason = (
            f"Adjust net {symbol} from {current_volume:+.2f} lots to "
            f"{target_volume:+.2f} lots"
        )
        if target_order is not None:
            reason = f"{reason}; target reason: {target_order.reason}"

        current_abs = abs(current_volume)
        target_abs = abs(target_volume)
        reduce_only = current_abs > 0 and target_abs < current_abs and current_volume * delta < 0

        adjustments.append(
            OrderIntent(
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                notional_usd=abs(delta),
                volume_lots=abs(delta),
                target_leverage=0.0,
                reduce_only=reduce_only,
                reason=reason,
            )
        )

    return ExecutionPlan(
        timestamp=target.timestamp,
        equity_usd=target.equity_usd,
        gross_leverage=target.gross_leverage,
        orders=adjustments,
    )
