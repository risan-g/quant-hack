from quantbot.execution.adjustments import CurrentPosition, adjustment_orders_from_positions
from quantbot.execution.models import ExecutionPlan, OrderIntent, OrderSide


def test_adjustment_orders_are_empty_when_current_matches_target() -> None:
    target = ExecutionPlan(
        timestamp="2026-06-21T23:45:00+00:00",
        equity_usd=1_000_000,
        gross_leverage=6,
        orders=[
            OrderIntent(
                symbol="USDJPY",
                side=OrderSide.SELL,
                notional_usd=2_100_000,
                volume_lots=21,
                target_leverage=-2.1,
                reason="test",
            )
        ],
    )
    current = [CurrentPosition(symbol="USDJPY", side=OrderSide.SELL, volume_lots=21)]

    adjustment = adjustment_orders_from_positions(target, current)

    assert adjustment.orders == []


def test_adjustment_orders_handle_flip_in_netting_mode() -> None:
    target = ExecutionPlan(
        timestamp="2026-06-21T23:30:00+00:00",
        equity_usd=1_000_000,
        gross_leverage=6,
        orders=[
            OrderIntent(
                symbol="USDCHF",
                side=OrderSide.BUY,
                notional_usd=1_500_000,
                volume_lots=15,
                target_leverage=1.5,
                reason="test",
            )
        ],
    )
    current = [CurrentPosition(symbol="USDCHF", side=OrderSide.SELL, volume_lots=15)]

    adjustment = adjustment_orders_from_positions(target, current)

    assert len(adjustment.orders) == 1
    assert adjustment.orders[0].symbol == "USDCHF"
    assert adjustment.orders[0].side == OrderSide.BUY
    assert adjustment.orders[0].volume_lots == 30


def test_adjustment_orders_close_missing_target_symbol() -> None:
    target = ExecutionPlan(
        timestamp="2026-06-21T23:45:00+00:00",
        equity_usd=1_000_000,
        gross_leverage=6,
        orders=[],
    )
    current = [CurrentPosition(symbol="USDCAD", side=OrderSide.BUY, volume_lots=12)]

    adjustment = adjustment_orders_from_positions(target, current)

    assert len(adjustment.orders) == 1
    assert adjustment.orders[0].symbol == "USDCAD"
    assert adjustment.orders[0].side == OrderSide.SELL
    assert adjustment.orders[0].volume_lots == 12
    assert adjustment.orders[0].reduce_only


def test_adjustment_orders_mark_partial_reduction_reduce_only() -> None:
    target = ExecutionPlan(
        timestamp="2026-06-21T23:45:00+00:00",
        equity_usd=1_000_000,
        gross_leverage=6,
        orders=[
            OrderIntent(
                symbol="USDJPY",
                side=OrderSide.BUY,
                notional_usd=600_000,
                volume_lots=6,
                target_leverage=0.6,
                reason="test",
            )
        ],
    )
    current = [CurrentPosition(symbol="USDJPY", side=OrderSide.BUY, volume_lots=10)]

    adjustment = adjustment_orders_from_positions(target, current)

    assert len(adjustment.orders) == 1
    assert adjustment.orders[0].side == OrderSide.SELL
    assert adjustment.orders[0].volume_lots == 4
    assert adjustment.orders[0].reduce_only
