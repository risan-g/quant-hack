#!/usr/bin/env python3
"""Supervised M5 MT5 checkpoint loop for fast dry/live experimentation."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from auto_checkpoint_loop import (
        LoopDecision,
        decide,
        latest_mid_prices,
        limit_one_step_flips,
        log_line,
        meaningful_orders,
        risk_limited_orders,
        write_ticket_files,
        split_large_orders,
    )
except ModuleNotFoundError:
    from scripts.auto_checkpoint_loop import (
        LoopDecision,
        decide,
        latest_mid_prices,
        limit_one_step_flips,
        log_line,
        meaningful_orders,
        risk_limited_orders,
        write_ticket_files,
        split_large_orders,
    )
from quantbot.execution.adjustments import adjustment_orders_from_positions
from quantbot.execution.models import ExecutionPlan, OrderIntent, OrderSide
from quantbot.execution.planner import plan_from_decision
from quantbot.execution.proposed_orders import write_proposed_orders_csv
from quantbot.execution.sizing import load_symbol_specs
from quantbot.live.decision import generate_decision_report, rescale_decision_report
from quantbot.live.mt5_bridge import read_mt5_live_bars_csv
from quantbot.live.mt5_positions import read_mt5_positions_csv
from quantbot.risk.live import (
    assess_live_positions,
    live_risk_block_reasons,
    projected_positions_after_orders,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mt5-bars-csv", type=Path, required=True)
    parser.add_argument("--mt5-positions-csv", type=Path, required=True)
    parser.add_argument("--proposed-orders-csv", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_scanner_attack.yaml"))
    parser.add_argument("--symbol-specs", type=Path, default=Path("configs/mt5_symbol_specs.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/execution_tickets"))
    parser.add_argument("--state-file", type=Path, default=Path("reports/auto_m5_checkpoint_state.json"))
    parser.add_argument("--log-file", type=Path, default=Path("reports/auto_m5_checkpoint_loop.log"))
    parser.add_argument("--kill-switch", type=Path, default=Path("M5_STOP_AUTO_TRADING"))
    parser.add_argument("--assume-timezone", default="Europe/London")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--max-export-age-seconds", type=int, default=120)
    parser.add_argument("--min-action-lots", type=float, default=0.05)
    parser.add_argument("--max-auto-order-lots", type=float, default=1.0)
    parser.add_argument("--max-total-action-lots", type=float, default=12.0)
    parser.add_argument("--max-projected-gross-leverage", type=float, default=2.0)
    parser.add_argument("--max-projected-symbol-share", type=float, default=1.0)
    parser.add_argument("--max-projected-net-directional-share", type=float, default=1.0)
    parser.add_argument("--max-projected-margin-usage", type=float, default=0.50)
    parser.add_argument("--max-platform-leverage", type=float, default=30.0)
    parser.add_argument("--equity-floor", type=float, default=950_000.0)
    parser.add_argument("--equity-ceiling", type=float, default=1_000_500.0)
    parser.add_argument("--time-stop-bars", type=int, default=8)
    parser.add_argument("--max-position-loss-usd", type=float, default=1_500.0)
    parser.add_argument("--profit-lock-trigger-usd", type=float, default=500.0)
    parser.add_argument("--profit-lock-floor-usd", type=float, default=100.0)
    parser.add_argument("--profit-lock-giveback-usd", type=float, default=300.0)
    parser.add_argument("--disable-order-protection", action="store_true")
    parser.add_argument("--split-large-orders", action="store_true")
    parser.add_argument("--stop-atr-window", type=int, default=14)
    parser.add_argument("--stop-atr-mult", type=float, default=1.5)
    parser.add_argument("--take-profit-atr-mult", type=float, default=3.0)
    parser.add_argument("--disable-entry-confirmation", action="store_true")
    parser.add_argument("--mode", choices=["dry-run", "live"], default="dry-run")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def configured_symbols(config: dict[str, Any]) -> set[str]:
    return {str(leg["symbol"]).upper() for leg in config["legs"]}


def filter_config_to_available_symbols(
    config: dict[str, Any],
    available_symbols: set[str],
) -> dict[str, Any]:
    legs = [leg for leg in config["legs"] if str(leg["symbol"]).upper() in available_symbols]
    if not legs:
        raise ValueError("None of the configured symbols are available in the MT5 export")
    total_weight = sum(float(leg["weight"]) for leg in legs)
    adjusted_legs = [
        {**leg, "weight": float(leg["weight"]) / total_weight}
        for leg in legs
    ]
    return {**config, "legs": adjusted_legs}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def export_age_seconds(exported_at: str) -> float:
    exported = datetime.fromisoformat(exported_at)
    if exported.tzinfo is None:
        exported = exported.replace(tzinfo=UTC)
    return (datetime.now(UTC) - exported.astimezone(UTC)).total_seconds()


def signed_order_lots(order: OrderIntent) -> float:
    lots = order.volume_lots or 0.0
    return lots if order.side == OrderSide.BUY else -lots


def current_signed_lots_by_symbol(snapshot) -> dict[str, float]:
    return {
        position.symbol.upper(): position.signed_volume_lots
        for position in snapshot.positions
    }


def order_opens_or_increases(order: OrderIntent, current_signed_lots: float) -> bool:
    signed = signed_order_lots(order)
    if signed == 0:
        return False
    if current_signed_lots == 0:
        return True
    return current_signed_lots * signed > 0


def plan_with_orders(plan: ExecutionPlan, orders: list[OrderIntent]) -> ExecutionPlan:
    return ExecutionPlan(
        timestamp=plan.timestamp,
        equity_usd=plan.equity_usd,
        gross_leverage=plan.gross_leverage,
        orders=orders,
    )


def entry_key(orders: list[OrderIntent]) -> str:
    return "|".join(
        sorted(f"{order.symbol.upper()}:{order.side.value.upper()}" for order in orders)
    )


def order_requires_confirmation(order: OrderIntent) -> bool:
    reason = order.reason.lower()
    return "momentum" in reason and "mean_reversion" not in reason


def require_confirmed_entries(
    plan: ExecutionPlan,
    snapshot,
    state: dict[str, Any],
    *,
    enabled: bool = True,
) -> tuple[ExecutionPlan, str | None, bool]:
    """Require new/increased entries to persist across two completed M5 candles."""
    if not enabled:
        if "pending_entry_signal" in state:
            state.pop("pending_entry_signal", None)
            return plan, None, True
        return plan, None, False

    current_by_symbol = current_signed_lots_by_symbol(snapshot)
    immediate_orders: list[OrderIntent] = []
    entry_orders: list[OrderIntent] = []

    for order in plan.orders:
        current = current_by_symbol.get(order.symbol.upper(), 0.0)
        if order_opens_or_increases(order, current) and order_requires_confirmation(order):
            entry_orders.append(order)
        else:
            immediate_orders.append(order)

    if not entry_orders:
        if "pending_entry_signal" in state:
            state.pop("pending_entry_signal", None)
            return plan, None, True
        return plan, None, False

    key = entry_key(entry_orders)
    pending = state.get("pending_entry_signal", {})
    if pending.get("key") == key and pending.get("last_seen_candle") != plan.timestamp:
        state.pop("pending_entry_signal", None)
        return plan, f"Confirmed entry signal after two M5 candles: {key}", True

    state["pending_entry_signal"] = {
        "key": key,
        "first_seen_candle": pending.get("first_seen_candle", plan.timestamp)
        if pending.get("key") == key
        else plan.timestamp,
        "last_seen_candle": plan.timestamp,
        "blocked_action": "; ".join(
            f"{order.side.value.upper()} {order.symbol} {order.volume_lots:.2f}"
            for order in entry_orders
            if order.volume_lots is not None
        ),
    }
    return (
        plan_with_orders(plan, immediate_orders),
        f"Waiting for one more M5 candle before opening: {key}",
        True,
    )


def m15_atr_prices(bars: pd.DataFrame, window: int = 14) -> dict[str, float]:
    atr_by_symbol: dict[str, float] = {}
    for symbol, group in bars.sort_values("time").groupby("symbol"):
        m15 = (
            group.set_index("time")
            .resample("15min")
            .agg({"mid_high": "max", "mid_low": "min", "mid_close": "last"})
            .dropna()
        )
        if len(m15) < 2:
            continue

        previous_close = m15["mid_close"].shift(1)
        true_range = pd.concat(
            [
                m15["mid_high"] - m15["mid_low"],
                (m15["mid_high"] - previous_close).abs(),
                (m15["mid_low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        latest_atr = true_range.dropna().tail(window).mean()
        if pd.notna(latest_atr) and latest_atr > 0:
            atr_by_symbol[str(symbol).upper()] = float(latest_atr)
    return atr_by_symbol


def latest_bar_by_symbol(bars: pd.DataFrame) -> dict[str, Any]:
    latest = bars.sort_values("time").groupby("symbol").tail(1)
    return {str(row.symbol).upper(): row for row in latest.itertuples(index=False)}


def attach_order_protection(
    plan: ExecutionPlan,
    bars: pd.DataFrame,
    snapshot,
    stop_atr_window: int,
    stop_atr_mult: float,
    take_profit_atr_mult: float,
) -> ExecutionPlan:
    if stop_atr_mult <= 0 or take_profit_atr_mult <= 0:
        return plan

    atr_by_symbol = m15_atr_prices(bars, stop_atr_window)
    latest_by_symbol = latest_bar_by_symbol(bars)
    current_by_symbol = current_signed_lots_by_symbol(snapshot)
    protected_orders: list[OrderIntent] = []

    for order in plan.orders:
        symbol = order.symbol.upper()
        current = current_by_symbol.get(symbol, 0.0)
        atr_price = atr_by_symbol.get(symbol)
        latest_bar = latest_by_symbol.get(symbol)
        should_protect = (
            order.volume_lots is not None
            and not order.reduce_only
            and order_opens_or_increases(order, current)
            and atr_price is not None
            and latest_bar is not None
        )
        if not should_protect:
            protected_orders.append(order)
            continue

        entry_price = (
            float(latest_bar.ask_close)
            if order.side == OrderSide.BUY
            else float(latest_bar.bid_close)
        )
        stop_distance = atr_price * stop_atr_mult
        take_profit_distance = atr_price * take_profit_atr_mult
        if order.side == OrderSide.BUY:
            stop_loss_price = entry_price - stop_distance
            take_profit_price = entry_price + take_profit_distance
        else:
            stop_loss_price = entry_price + stop_distance
            take_profit_price = entry_price - take_profit_distance

        if stop_loss_price <= 0 or take_profit_price <= 0:
            protected_orders.append(order)
            continue

        protected_orders.append(
            order.model_copy(
                update={
                    "stop_loss_price": round(stop_loss_price, 6),
                    "take_profit_price": round(take_profit_price, 6),
                }
            )
        )

    return plan_with_orders(plan, protected_orders)


def close_positions_plan(
    snapshot,
    timestamp: str,
    reason: str,
) -> ExecutionPlan:
    orders: list[OrderIntent] = []
    for position in snapshot.positions:
        close_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY
        orders.append(
            OrderIntent(
                symbol=position.symbol,
                side=close_side,
                notional_usd=position.volume_lots,
                volume_lots=position.volume_lots,
                target_leverage=0.0,
                reduce_only=True,
                reason=reason,
            )
        )
    return ExecutionPlan(
        timestamp=timestamp,
        equity_usd=snapshot.equity,
        gross_leverage=0.0,
        orders=orders,
    )


def enforce_symbol_lot_caps(
    plan: ExecutionPlan,
    snapshot,
    config: dict[str, Any],
) -> ExecutionPlan:
    caps = {
        str(leg["symbol"]).upper(): float(leg["max_lots"])
        for leg in config["legs"]
        if "max_lots" in leg
    }
    if not caps:
        return plan

    current_by_symbol = current_signed_lots_by_symbol(snapshot)
    capped_orders: list[OrderIntent] = []
    for order in plan.orders:
        cap = caps.get(order.symbol.upper())
        if cap is None or order.volume_lots is None:
            capped_orders.append(order)
            continue

        current = current_by_symbol.get(order.symbol.upper(), 0.0)
        signed = signed_order_lots(order)
        projected = current + signed
        if abs(projected) <= cap or not order_opens_or_increases(order, current):
            capped_orders.append(order)
            continue

        allowed_delta = max(0.0, cap - abs(current))
        if allowed_delta < 0.01:
            continue
        capped_orders.append(
            order.model_copy(
                update={
                    "volume_lots": round(allowed_delta, 2),
                    "notional_usd": round(order.notional_usd * allowed_delta / order.volume_lots, 2),
                    "reason": f"{order.reason}; capped_position_lots={cap:.2f}",
                }
            )
        )

    return plan_with_orders(plan, capped_orders)


def apply_position_exit_guards(
    plan: ExecutionPlan,
    snapshot,
    state: dict[str, Any],
    time_stop_bars: int,
    max_position_loss_usd: float,
    profit_lock_trigger_usd: float,
    profit_lock_floor_usd: float,
    profit_lock_giveback_usd: float,
) -> tuple[ExecutionPlan, bool]:
    state_changed = False
    position_seen = state.setdefault("position_seen", {})
    current_symbols = {position.symbol.upper() for position in snapshot.positions}
    for symbol in list(position_seen):
        if symbol not in current_symbols:
            position_seen.pop(symbol, None)
            state_changed = True

    close_orders: list[OrderIntent] = []
    for position in snapshot.positions:
        symbol = position.symbol.upper()
        key = f"{symbol}:{position.side.value}:{position.volume_lots:.2f}"
        profit = position.profit or 0.0
        seen = position_seen.get(symbol)
        if seen is None or seen.get("key") != key:
            position_seen[symbol] = {
                "key": key,
                "bars": 0,
                "last_candle": plan.timestamp,
                "max_profit": profit,
            }
            state_changed = True
            continue

        if seen.get("last_candle") != plan.timestamp:
            seen["bars"] = int(seen.get("bars", 0)) + 1
            seen["last_candle"] = plan.timestamp
            state_changed = True

        max_profit = max(float(seen.get("max_profit", profit)), profit)
        if max_profit != seen.get("max_profit"):
            seen["max_profit"] = max_profit
            state_changed = True

        profit_lock_stop = (
            max_profit >= profit_lock_trigger_usd
            and profit <= max(profit_lock_floor_usd, max_profit - profit_lock_giveback_usd)
        )
        hard_loss_stop = profit <= -max_position_loss_usd
        losing_time_stop = int(seen.get("bars", 0)) >= time_stop_bars and profit < 0
        if hard_loss_stop or profit_lock_stop or losing_time_stop:
            close_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY
            if hard_loss_stop:
                reason = f"Hard position loss stop pnl={profit:.2f}"
            elif profit_lock_stop:
                reason = (
                    f"Profit lock stop pnl={profit:.2f}; "
                    f"max_profit={max_profit:.2f}"
                )
            else:
                reason = (
                    f"Losing time stop after {seen['bars']} completed M5 bars; "
                    f"pnl={profit:.2f}"
                )
            close_orders.append(
                OrderIntent(
                    symbol=position.symbol,
                    side=close_side,
                    notional_usd=position.volume_lots,
                    volume_lots=position.volume_lots,
                    target_leverage=0.0,
                    reduce_only=True,
                    reason=reason,
                )
            )

    if not close_orders:
        return plan, state_changed

    stop_symbols = {order.symbol.upper() for order in close_orders}
    kept_orders = [order for order in plan.orders if order.symbol.upper() not in stop_symbols]
    return plan_with_orders(plan, [*kept_orders, *close_orders]), True


def build_adjustment(args: argparse.Namespace):
    config = load_config(args.config)
    symbols = configured_symbols(config)
    bars = read_mt5_live_bars_csv(args.mt5_bars_csv, args.assume_timezone, symbols)
    config = filter_config_to_available_symbols(config, set(bars["symbol"].unique()))
    mid_prices = latest_mid_prices(bars)
    snapshot = read_mt5_positions_csv(args.mt5_positions_csv, args.assume_timezone)
    specs = load_symbol_specs(args.symbol_specs)
    report = generate_decision_report(bars, config, config_name=f"{args.config.name}:M5")
    report = rescale_decision_report(report, snapshot.equity)
    target = plan_from_decision(report, symbol_specs=specs)
    adjustment = adjustment_orders_from_positions(target, snapshot.positions)
    adjustment = limit_one_step_flips(adjustment, snapshot.positions)
    adjustment = enforce_symbol_lot_caps(adjustment, snapshot, config)
    age = export_age_seconds(snapshot.exported_at)
    return adjustment, snapshot.exported_at, age, snapshot, mid_prices, bars


def run_once(args: argparse.Namespace):
    if args.kill_switch.exists():
        decision = LoopDecision(
            status="KILL_SWITCH",
            message=f"Kill switch exists at {args.kill_switch}; no action",
            candle_timestamp=None,
            should_write=False,
        )
        log_line(args.log_file, f"{decision.status}: {decision.message}")
        return decision

    state = load_state(args.state_file)
    adjustment, exported_at, export_age, snapshot, mid_prices, bars = build_adjustment(args)
    state_changed = False
    if snapshot.equity < args.equity_floor or snapshot.equity >= args.equity_ceiling:
        adjustment = close_positions_plan(
            snapshot,
            adjustment.timestamp,
            (
                f"Equity bound hit equity={snapshot.equity:.2f}; "
                f"floor={args.equity_floor:.2f}; ceiling={args.equity_ceiling:.2f}"
            ),
        )
    else:
        adjustment, exit_state_changed = apply_position_exit_guards(
            adjustment,
            snapshot,
            state,
            args.time_stop_bars,
            args.max_position_loss_usd,
            args.profit_lock_trigger_usd,
            args.profit_lock_floor_usd,
            args.profit_lock_giveback_usd,
        )
        state_changed = exit_state_changed
    adjustment, entry_confirmation_message, entry_state_changed = require_confirmed_entries(
        adjustment,
        snapshot,
        state,
        enabled=not args.disable_entry_confirmation,
    )
    state_changed = state_changed or entry_state_changed
    specs = load_symbol_specs(args.symbol_specs)
    projected_positions = projected_positions_after_orders(snapshot.positions, adjustment.orders)
    projected_risk = assess_live_positions(projected_positions, specs, mid_prices, snapshot.equity)
    risk_block_messages = live_risk_block_reasons(
        projected_risk,
        max_gross_leverage=args.max_projected_gross_leverage,
        max_largest_symbol_share=args.max_projected_symbol_share,
        max_net_directional_share=args.max_projected_net_directional_share,
        max_margin_usage=args.max_projected_margin_usage,
        max_platform_leverage=args.max_platform_leverage,
    )
    if risk_block_messages and adjustment.orders:
        risk_limited = meaningful_orders(
            risk_limited_orders(
                adjustment,
                snapshot.positions,
                specs,
                mid_prices,
                snapshot.equity,
                args.max_auto_order_lots,
                args.max_projected_gross_leverage,
                args.max_projected_symbol_share,
                args.max_projected_net_directional_share,
                args.max_projected_margin_usage,
                args.max_platform_leverage,
            ),
            args.min_action_lots,
        )
        if risk_limited.orders:
            adjustment = risk_limited
            risk_block_messages = None

    decision, safe_plan = decide(
        adjustment,
        exported_at,
        export_age,
        state,
        args.max_export_age_seconds,
        args.min_action_lots,
        args.max_auto_order_lots,
        True,
        args.max_total_action_lots,
        risk_block_messages,
    )
    if entry_confirmation_message and not decision.should_write and not safe_plan.orders:
        decision = LoopDecision(
            status="ENTRY_CONFIRMING",
            message=entry_confirmation_message,
            candle_timestamp=adjustment.timestamp,
            should_write=False,
        )

    if not args.disable_order_protection:
        safe_plan = attach_order_protection(
            safe_plan,
            bars,
            snapshot,
            args.stop_atr_window,
            args.stop_atr_mult,
            args.take_profit_atr_mult,
        )

    if args.split_large_orders:
        safe_plan = split_large_orders(safe_plan, args.max_auto_order_lots)

    write_ticket_files(safe_plan, args.output_dir)
    if decision.should_write:
        write_proposed_orders_csv(
            safe_plan,
            args.proposed_orders_csv,
            dry_run=args.mode == "dry-run",
        )
        state["last_written_timestamp"] = safe_plan.timestamp
        state["last_status"] = decision.status
        state["last_message"] = decision.message
        state["last_mode"] = args.mode
        state["last_updated_at"] = datetime.now(UTC).isoformat()
        write_state(args.state_file, state)
    elif state_changed:
        state["last_status"] = decision.status
        state["last_message"] = decision.message
        state["last_mode"] = args.mode
        state["last_updated_at"] = datetime.now(UTC).isoformat()
        write_state(args.state_file, state)

    log_line(
        args.log_file,
        (
            f"{decision.status}: {decision.message}; "
            f"mode={args.mode}; export={exported_at}; candle={decision.candle_timestamp}"
        ),
    )
    return decision


def main() -> None:
    args = parse_args()
    while True:
        try:
            decision = run_once(args)
        except Exception as exc:  # noqa: BLE001
            log_line(args.log_file, f"ERROR: {type(exc).__name__}: {exc}")
            if args.once:
                raise
        if args.once:
            print(json.dumps(decision.__dict__, indent=2), flush=True)
            return
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
