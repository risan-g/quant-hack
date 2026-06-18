"""Typed execution models shared by API, MT5, and manual adapters."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"


class OrderIntent(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    notional_usd: float = Field(gt=0)
    target_leverage: float
    reduce_only: bool = False
    reason: str


class ExecutionPlan(BaseModel):
    timestamp: str
    equity_usd: float
    gross_leverage: float
    orders: list[OrderIntent]

    @property
    def gross_notional_usd(self) -> float:
        return sum(order.notional_usd for order in self.orders)


class ExecutionReceipt(BaseModel):
    adapter: str
    accepted: bool
    message: str
    order_count: int
