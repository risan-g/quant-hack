from types import SimpleNamespace

import pandas as pd

from scripts.auto_checkpoint_loop import (
    decide,
    limit_one_step_flips,
    risk_limited_orders,
    split_large_orders,
)
from scripts.auto_m5_checkpoint_loop import (
    acknowledge_pending_live_write,
    apply_position_exit_guards,
    apply_symbol_cooldowns,
    attach_order_protection,
    require_confirmed_entries,
)
from quantbot.execution.adjustments import CurrentPosition
from quantbot.execution.models import ExecutionPlan, OrderIntent, OrderSide
from quantbot.execution.sizing import SymbolSpec


def make_plan(volume: float = 0.5, notional: float | None = None) -> ExecutionPlan:
    return ExecutionPlan(
        timestamp="2026-06-22T17:15:00+00:00",
        equity_usd=973_000,
        gross_leverage=1.0,
        orders=[
            OrderIntent(
                symbol="XAUUSD",
                side=OrderSide.BUY,
                notional_usd=volume if notional is None else notional,
                volume_lots=volume,
                target_leverage=0.0,
                reason="test",
            )
        ],
    )


def test_decide_holds_when_only_tiny_churn() -> None:
    decision, safe_plan = decide(
        make_plan(0.01),
        exported_at="2026-06-22T17:16:00+00:00",
        export_age=10,
        state={},
        max_export_age_seconds=180,
        min_action_lots=0.05,
        max_auto_order_lots=1.0,
        split_large=False,
        max_total_action_lots=30.0,
    )

    assert decision.status == "HOLD"
    assert not decision.should_write
    assert safe_plan.orders == []


def test_decide_requires_manual_for_large_order() -> None:
    decision, safe_plan = decide(
        make_plan(1.5),
        exported_at="2026-06-22T17:16:00+00:00",
        export_age=10,
        state={},
        max_export_age_seconds=180,
        min_action_lots=0.05,
        max_auto_order_lots=1.0,
        split_large=False,
        max_total_action_lots=30.0,
    )

    assert decision.status == "MANUAL_REQUIRED"
    assert not decision.should_write
    assert len(safe_plan.orders) == 1


def test_decide_writes_safe_order() -> None:
    decision, safe_plan = decide(
        make_plan(0.5),
        exported_at="2026-06-22T17:16:00+00:00",
        export_age=10,
        state={},
        max_export_age_seconds=180,
        min_action_lots=0.05,
        max_auto_order_lots=1.0,
        split_large=False,
        max_total_action_lots=30.0,
    )

    assert decision.status == "WRITE"
    assert decision.should_write
    assert safe_plan.orders[0].volume_lots == 0.5


def test_decide_splits_large_order_when_enabled() -> None:
    decision, safe_plan = decide(
        make_plan(2.5),
        exported_at="2026-06-22T17:16:00+00:00",
        export_age=10,
        state={},
        max_export_age_seconds=180,
        min_action_lots=0.05,
        max_auto_order_lots=1.0,
        split_large=True,
        max_total_action_lots=30.0,
    )

    assert decision.status == "WRITE_SPLIT"
    assert decision.should_write
    assert [order.volume_lots for order in safe_plan.orders] == [1.0, 1.0, 0.5]


def test_decide_blocks_total_action_above_limit() -> None:
    decision, safe_plan = decide(
        make_plan(31.0),
        exported_at="2026-06-22T17:16:00+00:00",
        export_age=10,
        state={},
        max_export_age_seconds=180,
        min_action_lots=0.05,
        max_auto_order_lots=1.0,
        split_large=True,
        max_total_action_lots=30.0,
    )

    assert decision.status == "BLOCKED_TOTAL_SIZE"
    assert not decision.should_write
    assert safe_plan.orders[0].volume_lots == 31.0


def test_decide_allows_reduce_only_action_above_total_limit() -> None:
    plan = make_plan(31.0)
    plan.orders[0].reduce_only = True

    decision, safe_plan = decide(
        plan,
        exported_at="2026-06-22T17:16:00+00:00",
        export_age=10,
        state={},
        max_export_age_seconds=180,
        min_action_lots=0.05,
        max_auto_order_lots=1.0,
        split_large=True,
        max_total_action_lots=6.0,
    )

    assert decision.status == "WRITE_SPLIT"
    assert decision.should_write
    assert sum(order.volume_lots or 0.0 for order in safe_plan.orders) == 31.0


def test_decide_blocks_projected_risk() -> None:
    decision, safe_plan = decide(
        make_plan(0.5),
        exported_at="2026-06-22T17:16:00+00:00",
        export_age=10,
        state={},
        max_export_age_seconds=180,
        min_action_lots=0.05,
        max_auto_order_lots=1.0,
        split_large=False,
        max_total_action_lots=30.0,
        risk_block_messages=["projected gross leverage 13.00x exceeds 12.00x"],
    )

    assert decision.status == "RISK_BLOCKED"
    assert not decision.should_write
    assert safe_plan.orders[0].volume_lots == 0.5


def test_split_large_orders_preserves_total_volume() -> None:
    split_plan = split_large_orders(make_plan(2.43, notional=243_000), max_order_lots=1.0)

    assert [order.volume_lots for order in split_plan.orders] == [1.0, 1.0, 0.43]
    assert [order.notional_usd for order in split_plan.orders] == [100_000, 100_000, 43_000]


def test_risk_limited_orders_keeps_safe_partial_prefix() -> None:
    plan = ExecutionPlan(
        timestamp="2026-06-22T17:15:00+00:00",
        equity_usd=1_000_000,
        gross_leverage=1.0,
        orders=[
            OrderIntent(
                symbol="USDCHF",
                side=OrderSide.BUY,
                notional_usd=7.9,
                volume_lots=7.9,
                target_leverage=0.0,
                reason="flip would over-concentrate",
            )
        ],
    )
    current = [
        CurrentPosition(symbol="USDCAD", side=OrderSide.BUY, volume_lots=3.95),
        CurrentPosition(symbol="USDCHF", side=OrderSide.SELL, volume_lots=3.95),
    ]
    specs = {
        symbol: SymbolSpec(
            symbol=symbol,
            contract_size=100_000,
            contract_asset="USD",
            quote_currency=symbol[-3:],
            min_volume=0.01,
            max_volume=100,
            volume_step=0.01,
        )
        for symbol in ("USDCAD", "USDCHF")
    }

    limited = risk_limited_orders(
        plan,
        current,
        specs,
        {"USDCAD": 1.42, "USDCHF": 0.81},
        equity_usd=1_000_000,
        max_order_lots=1.0,
        max_gross_leverage=12.0,
        max_largest_symbol_share=0.85,
        max_net_directional_share=0.90,
        max_margin_usage=0.50,
        max_platform_leverage=30.0,
    )

    assert [order.volume_lots for order in limited.orders] == [1.0, 1.0, 1.0]


def test_limit_one_step_flips_closes_to_flat_first() -> None:
    plan = ExecutionPlan(
        timestamp="2026-06-22T17:15:00+00:00",
        equity_usd=1_000_000,
        gross_leverage=1.0,
        orders=[
            OrderIntent(
                symbol="USDCHF",
                side=OrderSide.BUY,
                notional_usd=4.9,
                volume_lots=4.9,
                target_leverage=0.0,
                reason="reverse to long",
            )
        ],
    )
    current = [CurrentPosition(symbol="USDCHF", side=OrderSide.SELL, volume_lots=0.95)]

    limited = limit_one_step_flips(plan, current)

    assert len(limited.orders) == 1
    assert limited.orders[0].symbol == "USDCHF"
    assert limited.orders[0].side == OrderSide.BUY
    assert limited.orders[0].volume_lots == 0.95
    assert limited.orders[0].reduce_only


def test_require_confirmed_entries_blocks_first_new_entry_then_confirms() -> None:
    state = {}
    snapshot = SimpleNamespace(positions=[])
    first_plan = make_plan(0.5)
    first_plan.orders[0].reason = "m15_momentum_32 long"

    first_filtered, first_message, first_changed = require_confirmed_entries(
        first_plan,
        snapshot,
        state,
    )

    assert first_filtered.orders == []
    assert first_message == "Waiting for one more M5 candle before opening: XAUUSD:BUY"
    assert first_changed

    second_plan = first_plan.model_copy(update={"timestamp": "2026-06-22T17:20:00+00:00"})
    second_filtered, second_message, second_changed = require_confirmed_entries(
        second_plan,
        snapshot,
        state,
    )

    assert second_filtered.orders == second_plan.orders
    assert second_message == "Confirmed entry signal after two M5 candles: XAUUSD:BUY"
    assert second_changed


def test_require_confirmed_entries_allows_mean_reversion_immediately() -> None:
    state = {}
    snapshot = SimpleNamespace(positions=[])
    plan = make_plan(0.5)
    plan.orders[0].reason = "mean_reversion_16 long"

    filtered, message, changed = require_confirmed_entries(plan, snapshot, state)

    assert filtered.orders == plan.orders
    assert message is None
    assert not changed


def test_require_confirmed_entries_can_be_disabled_for_sprint_mode() -> None:
    state = {"pending_entry_signal": {"key": "XAUUSD:SELL"}}
    snapshot = SimpleNamespace(positions=[])
    plan = make_plan(0.5)
    plan.orders[0].reason = "m15_momentum_32 short"

    filtered, message, changed = require_confirmed_entries(
        plan,
        snapshot,
        state,
        enabled=False,
    )

    assert filtered.orders == plan.orders
    assert message is None
    assert changed
    assert "pending_entry_signal" not in state


def test_attach_order_protection_adds_atr_stop_and_take_profit() -> None:
    rows = []
    start = pd.Timestamp("2026-06-22T17:00:00+00:00")
    for index in range(8):
        close = 100.0 + index
        rows.append(
            {
                "symbol": "XAUUSD",
                "time": start + pd.Timedelta(minutes=5 * index),
                "mid_high": close + 1.0,
                "mid_low": close - 1.0,
                "mid_close": close,
                "ask_close": close + 0.05,
                "bid_close": close - 0.05,
            }
        )
    plan = make_plan(0.5)
    plan.orders[0].reason = "m15_momentum_32 long"
    snapshot = SimpleNamespace(positions=[])

    protected = attach_order_protection(plan, pd.DataFrame(rows), snapshot, 14, 1.5, 3.0)

    order = protected.orders[0]
    assert order.stop_loss_price is not None
    assert order.take_profit_price is not None
    assert order.stop_loss_price < rows[-1]["ask_close"]
    assert order.take_profit_price > rows[-1]["ask_close"]


def test_acknowledge_pending_live_write_blocks_unreflected_orders() -> None:
    state = {
        "pending_live_write": {
            "written_at": "2026-06-22T17:15:00+00:00",
            "candle_timestamp": "2026-06-22T17:15:00+00:00",
            "expected_positions": {"USDCHF": 2.0},
        }
    }
    snapshot = SimpleNamespace(positions=[])

    decision, changed = acknowledge_pending_live_write(state, snapshot, ack_timeout_seconds=0)

    assert decision is not None
    assert decision.status == "ACK_BLOCKED"
    assert not changed
    assert "pending_live_write" in state


def test_acknowledge_pending_live_write_clears_when_positions_match() -> None:
    state = {
        "pending_live_write": {
            "written_at": "2026-06-22T17:15:00+00:00",
            "candle_timestamp": "2026-06-22T17:15:00+00:00",
            "expected_positions": {"USDCHF": 2.0},
        }
    }
    snapshot = SimpleNamespace(
        positions=[CurrentPosition(symbol="USDCHF", side=OrderSide.BUY, volume_lots=2.0)]
    )

    decision, changed = acknowledge_pending_live_write(state, snapshot, ack_timeout_seconds=0)

    assert decision is None
    assert changed
    assert "pending_live_write" not in state


def test_symbol_cooldown_blocks_entries_but_allows_reductions() -> None:
    state = {
        "symbol_cooldowns": {
            "USDCHF": {"bars_remaining": 3, "last_candle": "2026-06-22T17:15:00+00:00"}
        }
    }
    snapshot = SimpleNamespace(
        positions=[CurrentPosition(symbol="USDCHF", side=OrderSide.BUY, volume_lots=1.0)]
    )
    entry_plan = ExecutionPlan(
        timestamp="2026-06-22T17:20:00+00:00",
        equity_usd=973_000,
        gross_leverage=1.0,
        orders=[
            OrderIntent(
                symbol="USDCHF",
                side=OrderSide.BUY,
                notional_usd=1.0,
                volume_lots=1.0,
                target_leverage=0.0,
                reason="increase",
            )
        ],
    )
    reduce_plan = entry_plan.model_copy(
        update={
            "orders": [
                entry_plan.orders[0].model_copy(
                    update={"side": OrderSide.SELL, "reason": "reduce"}
                )
            ]
        }
    )

    assert apply_symbol_cooldowns(entry_plan, snapshot, state).orders == []
    assert apply_symbol_cooldowns(reduce_plan, snapshot, state).orders == reduce_plan.orders


def test_position_exit_time_stop_counts_completed_candles_only() -> None:
    state = {}
    snapshot = SimpleNamespace(
        positions=[
            CurrentPosition(
                symbol="USDCHF",
                side=OrderSide.BUY,
                volume_lots=2.0,
                profit=-50.0,
            )
        ]
    )
    plan = make_plan(0.5)
    plan = plan.model_copy(update={"orders": []})

    first, _ = apply_position_exit_guards(plan, snapshot, state, 1, 1500, 500, 100, 300, 900, 0.33, 500, 6)
    same_candle, _ = apply_position_exit_guards(plan, snapshot, state, 1, 1500, 500, 100, 300, 900, 0.33, 500, 6)
    next_plan = plan.model_copy(update={"timestamp": "2026-06-22T17:20:00+00:00"})
    next_candle, _ = apply_position_exit_guards(next_plan, snapshot, state, 1, 1500, 500, 100, 300, 900, 0.33, 500, 6)

    assert first.orders == []
    assert same_candle.orders == []
    assert len(next_candle.orders) == 1
    assert next_candle.orders[0].reduce_only
    assert "Losing time stop" in next_candle.orders[0].reason


def test_position_exit_profit_lock_closes_after_giveback() -> None:
    state = {
        "position_seen": {
            "USDCHF": {
                "key": "USDCHF:buy:2.00",
                "bars": 2,
                "last_candle": "2026-06-22T17:15:00+00:00",
                "max_profit": 700.0,
            }
        }
    }
    snapshot = SimpleNamespace(
        positions=[
            CurrentPosition(
                symbol="USDCHF",
                side=OrderSide.BUY,
                volume_lots=2.0,
                profit=350.0,
            )
        ]
    )
    plan = make_plan(0.5).model_copy(update={"orders": []})

    guarded, changed = apply_position_exit_guards(plan, snapshot, state, 8, 1500, 500, 100, 300, 900, 0.33, 500, 6)

    assert changed
    assert len(guarded.orders) == 1
    assert guarded.orders[0].side == OrderSide.SELL
    assert "Profit lock stop" in guarded.orders[0].reason


def test_position_exit_scales_winner_once() -> None:
    state = {
        "position_seen": {
            "USDCHF": {
                "key": "USDCHF:buy:3.00",
                "bars": 2,
                "last_candle": "2026-06-22T17:15:00+00:00",
                "max_profit": 950.0,
                "last_profit": 950.0,
                "scaled_once": False,
            }
        }
    }
    snapshot = SimpleNamespace(
        positions=[
            CurrentPosition(
                symbol="USDCHF",
                side=OrderSide.BUY,
                volume_lots=3.0,
                profit=950.0,
            )
        ]
    )
    plan = make_plan(0.5).model_copy(update={"orders": []})

    guarded, changed = apply_position_exit_guards(plan, snapshot, state, 8, 1500, 500, 100, 300, 900, 0.33, 500, 6)

    assert changed
    assert len(guarded.orders) == 1
    assert guarded.orders[0].reduce_only
    assert guarded.orders[0].volume_lots == 0.99
    assert "Partial winner lock" in guarded.orders[0].reason
    assert state["position_seen"]["USDCHF"]["scaled_once"]
