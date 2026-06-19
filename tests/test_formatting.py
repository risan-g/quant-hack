from quantbot.execution.formatting import format_manual_ticket
from quantbot.execution.models import ExecutionPlan, OrderIntent, OrderSide


def test_format_manual_ticket_includes_volume() -> None:
    plan = ExecutionPlan(
        timestamp="2026-06-10T23:45:00+00:00",
        equity_usd=1_000_000,
        gross_leverage=5,
        orders=[
            OrderIntent(
                symbol="XAUUSD",
                side=OrderSide.SELL,
                notional_usd=410_000,
                volume_lots=1.0,
                target_leverage=-0.41,
                reason="test",
            )
        ],
    )
    ticket = format_manual_ticket(plan)
    assert "XAUUSD" in ticket
    assert "1.00" in ticket
    assert "SELL" in ticket
