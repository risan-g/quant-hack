from quantbot.execution.models import ExecutionPlan, OrderIntent, OrderSide
from quantbot.execution.proposed_orders import proposed_orders_frame


def test_proposed_orders_frame_contains_dry_run_actions() -> None:
    plan = ExecutionPlan(
        timestamp="2026-06-22T13:15:00+00:00",
        equity_usd=995_721.44,
        gross_leverage=7.0,
        orders=[
            OrderIntent(
                symbol="XAUUSD",
                side=OrderSide.SELL,
                notional_usd=3.09,
                volume_lots=3.09,
                target_leverage=0.0,
                reason="adjust",
            )
        ],
    )

    frame = proposed_orders_frame(plan)

    assert frame.to_dict("records") == [
        {
            "timestamp": "2026-06-22T13:15:00+00:00",
            "symbol": "XAUUSD",
            "side": "sell",
            "volume_lots": 3.09,
            "order_type": "market",
            "dry_run": True,
            "reason": "adjust",
        }
    ]


def test_proposed_orders_frame_encodes_optional_protection_in_reason() -> None:
    plan = ExecutionPlan(
        timestamp="2026-06-22T13:15:00+00:00",
        equity_usd=995_721.44,
        gross_leverage=7.0,
        orders=[
            OrderIntent(
                symbol="XAUUSD",
                side=OrderSide.SELL,
                notional_usd=3.09,
                volume_lots=3.09,
                target_leverage=0.0,
                stop_loss_price=4075.25,
                take_profit_price=4045.75,
                reason="adjust",
            )
        ],
    )

    frame = proposed_orders_frame(plan, dry_run=False)

    assert frame.to_dict("records")[0]["reason"] == (
        "adjust; sl_price=4075.25; tp_price=4045.75"
    )
