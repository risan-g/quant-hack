from quantbot.execution.models import OrderSide
from quantbot.execution.planner import plan_from_decision
from quantbot.live.decision import DecisionLeg, DecisionReport


def test_plan_from_decision_skips_flat_and_maps_sides() -> None:
    report = DecisionReport(
        timestamp="2026-06-10T23:45:00+00:00",
        config_name="test.yaml",
        equity_usd=1_000_000,
        peak_equity_usd=1_000_000,
        drawdown=0,
        gross_leverage=5,
        cooldown_bars=0,
        active_legs=2,
        net_directional_leverage=1,
        gross_target_notional_usd=300_000,
        legs=[
            DecisionLeg(
                symbol="XAUUSD",
                strategy="momentum_8",
                side="long",
                raw_signal=1,
                allowed_by_regime=True,
                weight=0.3,
                mid_price=4000,
                spread_fraction=0.0001,
                spread_z=0.5,
                target_notional_usd=300_000,
                target_leverage=0.3,
            ),
            DecisionLeg(
                symbol="USDJPY",
                strategy="mean_reversion_8",
                side="flat",
                raw_signal=0,
                allowed_by_regime=True,
                weight=0.2,
                mid_price=160,
                spread_fraction=0.00001,
                spread_z=0,
                target_notional_usd=0,
                target_leverage=0,
            ),
        ],
    )

    plan = plan_from_decision(report)
    assert len(plan.orders) == 1
    assert plan.orders[0].side == OrderSide.BUY
    assert plan.orders[0].notional_usd == 300_000
