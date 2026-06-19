from quantbot.execution.models import OrderSide
from quantbot.execution.planner import plan_from_decision
from quantbot.execution.sizing import SymbolSpec, lots_for_notional_usd
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


def test_lots_for_xauusd_notional() -> None:
    spec = SymbolSpec(
        symbol="XAUUSD",
        contract_size=100,
        contract_asset="XAU",
        quote_currency="USD",
        min_volume=0.01,
        max_volume=100,
        volume_step=0.01,
    )
    assert lots_for_notional_usd(spec, notional_usd=3_858_626, mid_price=4100) == 9.41


def test_lots_for_usdjpy_notional() -> None:
    spec = SymbolSpec(
        symbol="USDJPY",
        contract_size=100_000,
        contract_asset="USD",
        quote_currency="JPY",
        min_volume=0.01,
        max_volume=100,
        volume_step=0.01,
    )
    assert lots_for_notional_usd(spec, notional_usd=1_929_313, mid_price=160) == 19.29
