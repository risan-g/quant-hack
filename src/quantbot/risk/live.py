"""Live position risk assessment helpers."""

from __future__ import annotations

from pydantic import BaseModel, Field

from quantbot.execution.adjustments import CurrentPosition
from quantbot.execution.models import OrderIntent, OrderSide
from quantbot.execution.sizing import SymbolSpec, usd_notional_per_lot


class PositionRisk(BaseModel):
    symbol: str
    side: OrderSide
    volume_lots: float
    mid_price: float
    notional_usd: float
    signed_notional_usd: float
    leverage: float


class LiveRiskReport(BaseModel):
    equity_usd: float = Field(gt=0)
    gross_notional_usd: float
    gross_leverage: float
    net_directional_notional_usd: float
    net_directional_leverage: float
    net_directional_share: float
    largest_symbol: str | None
    largest_symbol_share: float
    warnings: list[str]
    positions: list[PositionRisk]


def _signed_notional(position: CurrentPosition, notional: float) -> float:
    if position.side == OrderSide.BUY:
        return notional
    return -notional


def _signed_order_volume(order: OrderIntent) -> float:
    if order.volume_lots is None:
        raise ValueError(f"Order for {order.symbol} has no MT5 lot volume")
    if order.side == OrderSide.BUY:
        return order.volume_lots
    return -order.volume_lots


def projected_positions_after_orders(
    current_positions: list[CurrentPosition],
    orders: list[OrderIntent],
    min_volume_lots: float = 0.01,
) -> list[CurrentPosition]:
    """Project MT5 netting-mode positions after applying proposed adjustment orders."""
    signed_by_symbol = {
        position.symbol.upper(): position.signed_volume_lots for position in current_positions
    }
    for order in orders:
        symbol = order.symbol.upper()
        signed_by_symbol[symbol] = signed_by_symbol.get(symbol, 0.0) + _signed_order_volume(order)

    projected: list[CurrentPosition] = []
    for symbol, signed_volume in sorted(signed_by_symbol.items()):
        signed_volume = round(signed_volume, 2)
        if abs(signed_volume) < min_volume_lots:
            continue
        projected.append(
            CurrentPosition(
                symbol=symbol,
                side=OrderSide.BUY if signed_volume > 0 else OrderSide.SELL,
                volume_lots=abs(signed_volume),
            )
        )
    return projected


def assess_live_positions(
    positions: list[CurrentPosition],
    specs: dict[str, SymbolSpec],
    mid_prices: dict[str, float],
    equity_usd: float,
    gross_leverage_warn: float = 10.0,
    gross_leverage_danger: float = 20.0,
    symbol_share_warn: float = 0.70,
    net_directional_warn: float = 0.85,
) -> LiveRiskReport:
    rows: list[PositionRisk] = []
    for position in positions:
        symbol = position.symbol.upper()
        spec = specs.get(symbol)
        if spec is None:
            raise ValueError(f"Missing symbol spec for {symbol}")
        mid_price = mid_prices.get(symbol)
        if mid_price is None:
            raise ValueError(f"Missing mid price for {symbol}")
        notional = position.volume_lots * usd_notional_per_lot(spec, mid_price, mid_prices)
        signed_notional = _signed_notional(position, notional)
        rows.append(
            PositionRisk(
                symbol=symbol,
                side=position.side,
                volume_lots=position.volume_lots,
                mid_price=mid_price,
                notional_usd=notional,
                signed_notional_usd=signed_notional,
                leverage=notional / equity_usd,
            )
        )

    gross_notional = sum(row.notional_usd for row in rows)
    net_directional = sum(row.signed_notional_usd for row in rows)
    largest = max(rows, key=lambda row: row.notional_usd, default=None)
    largest_share = (
        0.0 if gross_notional == 0 else (largest.notional_usd / gross_notional if largest else 0.0)
    )
    net_directional_share = 0.0 if gross_notional == 0 else abs(net_directional) / gross_notional

    warnings: list[str] = []
    gross_leverage = gross_notional / equity_usd
    net_directional_leverage = abs(net_directional) / equity_usd
    if gross_leverage >= gross_leverage_danger:
        warnings.append(f"DANGER gross leverage {gross_leverage:.2f}x")
    elif gross_leverage >= gross_leverage_warn:
        warnings.append(f"WARN gross leverage {gross_leverage:.2f}x")
    if largest_share >= symbol_share_warn and largest is not None:
        warnings.append(
            f"WARN largest symbol {largest.symbol} is {largest_share:.1%} of gross exposure"
        )
    if net_directional_leverage >= net_directional_warn:
        warnings.append(f"WARN net directional leverage {net_directional_leverage:.2f}x")

    return LiveRiskReport(
        equity_usd=equity_usd,
        gross_notional_usd=gross_notional,
        gross_leverage=gross_leverage,
        net_directional_notional_usd=net_directional,
        net_directional_leverage=net_directional_leverage,
        net_directional_share=net_directional_share,
        largest_symbol=None if largest is None else largest.symbol,
        largest_symbol_share=largest_share,
        warnings=warnings,
        positions=rows,
    )


def live_risk_block_reasons(
    report: LiveRiskReport,
    max_gross_leverage: float = 12.0,
    max_largest_symbol_share: float = 0.85,
    max_net_directional_share: float = 0.90,
    max_margin_usage: float = 0.50,
    max_platform_leverage: float = 30.0,
) -> list[str]:
    """Return hard-block reasons for projected live exposure."""
    reasons: list[str] = []
    if report.gross_leverage > max_gross_leverage:
        reasons.append(
            f"projected gross leverage {report.gross_leverage:.2f}x exceeds "
            f"{max_gross_leverage:.2f}x"
        )
    if report.largest_symbol_share > max_largest_symbol_share:
        reasons.append(
            f"projected largest symbol share {report.largest_symbol_share:.1%} exceeds "
            f"{max_largest_symbol_share:.1%}"
        )
    if report.net_directional_share > max_net_directional_share:
        reasons.append(
            f"projected net directional share {report.net_directional_share:.1%} exceeds "
            f"{max_net_directional_share:.1%}"
        )
    if max_platform_leverage <= 0:
        raise ValueError("max_platform_leverage must be positive")
    projected_margin_usage = report.gross_leverage / max_platform_leverage
    if projected_margin_usage > max_margin_usage:
        reasons.append(
            f"projected margin usage {projected_margin_usage:.1%} exceeds "
            f"{max_margin_usage:.1%}"
        )
    return reasons
