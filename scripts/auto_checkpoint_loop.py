#!/usr/bin/env python3
"""Supervised MT5 checkpoint loop for the Syphonix live bridge."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quantbot.execution.adjustments import CurrentPosition, adjustment_orders_from_positions
from quantbot.execution.formatting import format_manual_ticket
from quantbot.execution.models import ExecutionPlan, OrderIntent, OrderSide
from quantbot.execution.planner import plan_from_decision
from quantbot.execution.proposed_orders import write_proposed_orders_csv
from quantbot.execution.sizing import load_symbol_specs
from quantbot.live.decision import generate_decision_report, rescale_decision_report
from quantbot.live.mt5_bridge import merge_historical_and_live_bars, read_mt5_live_bars_csv
from quantbot.live.mt5_positions import MT5PositionSnapshot, read_mt5_positions_csv
from quantbot.risk.live import (
    assess_live_positions,
    live_risk_block_reasons,
    projected_positions_after_orders,
)


@dataclass(frozen=True)
class LoopDecision:
    status: str
    message: str
    candle_timestamp: str | None
    should_write: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--mt5-bars-csv", type=Path, required=True)
    parser.add_argument("--mt5-positions-csv", type=Path, required=True)
    parser.add_argument("--proposed-orders-csv", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_guarded.yaml"))
    parser.add_argument("--symbol-specs", type=Path, default=Path("configs/mt5_symbol_specs.yaml"))
    parser.add_argument("--output-bars", type=Path, default=Path("data/live/bars_15min_full_live.parquet"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/execution_tickets"))
    parser.add_argument("--state-file", type=Path, default=Path("reports/auto_checkpoint_state.json"))
    parser.add_argument("--log-file", type=Path, default=Path("reports/auto_checkpoint_loop.log"))
    parser.add_argument("--kill-switch", type=Path, default=Path("STOP_AUTO_TRADING"))
    parser.add_argument(
        "--assume-timezone",
        default="Europe/London",
        help="Timezone for naive MT5 timestamps.",
    )
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--max-export-age-seconds", type=int, default=180)
    parser.add_argument("--min-action-lots", type=float, default=0.05)
    parser.add_argument("--max-auto-order-lots", type=float, default=1.0)
    parser.add_argument(
        "--split-large-orders",
        action="store_true",
        help=(
            "Split actions larger than --max-auto-order-lots into multiple capped "
            "orders instead of requiring manual execution."
        ),
    )
    parser.add_argument(
        "--max-total-action-lots",
        type=float,
        default=30.0,
        help="Block a checkpoint if total requested adjustment volume exceeds this.",
    )
    parser.add_argument("--max-projected-gross-leverage", type=float, default=12.0)
    parser.add_argument("--max-projected-symbol-share", type=float, default=0.85)
    parser.add_argument("--max-projected-net-directional-share", type=float, default=0.90)
    parser.add_argument("--max-projected-margin-usage", type=float, default=0.50)
    parser.add_argument("--max-platform-leverage", type=float, default=30.0)
    parser.add_argument(
        "--allow-one-step-flips",
        action="store_true",
        help="Allow one checkpoint to close and reopen a symbol in the opposite direction.",
    )
    parser.add_argument("--mode", choices=["dry-run", "live"], default="dry-run")
    parser.add_argument("--once", action="store_true", help="Run one check and exit.")
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def configured_symbols(config: dict[str, Any]) -> set[str]:
    return {str(leg["symbol"]).upper() for leg in config["legs"]}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def log_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")
    print(f"{stamp} {message}", flush=True)


def export_age_seconds(exported_at: str) -> float:
    exported = datetime.fromisoformat(exported_at)
    if exported.tzinfo is None:
        exported = exported.replace(tzinfo=UTC)
    return (datetime.now(UTC) - exported.astimezone(UTC)).total_seconds()


def meaningful_orders(plan: ExecutionPlan, min_action_lots: float) -> ExecutionPlan:
    orders = [
        order
        for order in plan.orders
        if order.volume_lots is not None and order.volume_lots >= min_action_lots
    ]
    return ExecutionPlan(
        timestamp=plan.timestamp,
        equity_usd=plan.equity_usd,
        gross_leverage=plan.gross_leverage,
        orders=orders,
    )


def max_order_lots(plan: ExecutionPlan) -> float:
    volumes = [order.volume_lots or 0.0 for order in plan.orders]
    return max(volumes, default=0.0)


def total_order_lots(plan: ExecutionPlan) -> float:
    return sum(order.volume_lots or 0.0 for order in plan.orders)


def total_risk_increasing_lots(plan: ExecutionPlan) -> float:
    return sum(order.volume_lots or 0.0 for order in plan.orders if not order.reduce_only)


def latest_mid_prices(bars: pd.DataFrame) -> dict[str, float]:
    latest = bars.sort_values("time").groupby("symbol").tail(1)
    return dict(zip(latest["symbol"], latest["mid_close"], strict=True))


def split_large_orders(plan: ExecutionPlan, max_order_lots: float) -> ExecutionPlan:
    """Split orders into chunks so the EA per-order cap still bounds each click."""
    if max_order_lots <= 0:
        raise ValueError("max_order_lots must be positive")

    split_orders: list[OrderIntent] = []
    for order in plan.orders:
        if order.volume_lots is None:
            split_orders.append(order)
            continue

        remaining = round(order.volume_lots, 2)
        chunk_index = 1
        while remaining > 0:
            chunk = min(remaining, max_order_lots)
            chunk = round(chunk, 2)
            if chunk <= 0:
                break
            notional = round(order.notional_usd * (chunk / order.volume_lots), 2)
            split_orders.append(
                order.model_copy(
                    update={
                        "notional_usd": notional,
                        "volume_lots": chunk,
                        "reason": f"{order.reason}; auto_chunk={chunk_index}",
                    }
                )
            )
            remaining = round(remaining - chunk, 2)
            chunk_index += 1

    return ExecutionPlan(
        timestamp=plan.timestamp,
        equity_usd=plan.equity_usd,
        gross_leverage=plan.gross_leverage,
        orders=split_orders,
    )


def limit_one_step_flips(
    plan: ExecutionPlan,
    current_positions: list[CurrentPosition],
    min_volume_lots: float = 0.01,
) -> ExecutionPlan:
    """Turn one-step reversals into close-to-flat orders first."""
    current_by_symbol = {
        position.symbol.upper(): position.signed_volume_lots for position in current_positions
    }
    limited_orders: list[OrderIntent] = []
    for order in plan.orders:
        if order.volume_lots is None:
            limited_orders.append(order)
            continue

        current = current_by_symbol.get(order.symbol.upper(), 0.0)
        signed_order = order.volume_lots if order.side == OrderSide.BUY else -order.volume_lots
        projected = round(current + signed_order, 2)
        if current == 0 or current * projected >= 0:
            limited_orders.append(order)
            continue

        close_volume = round(abs(current), 2)
        if close_volume < min_volume_lots:
            continue
        close_side = OrderSide.SELL if current > 0 else OrderSide.BUY
        limited_orders.append(
            order.model_copy(
                update={
                    "side": close_side,
                    "volume_lots": close_volume,
                    "notional_usd": close_volume,
                    "reduce_only": True,
                    "reason": (
                        f"Close {order.symbol} to flat before considering reversal; "
                        f"original reason: {order.reason}"
                    ),
                }
            )
        )

    return ExecutionPlan(
        timestamp=plan.timestamp,
        equity_usd=plan.equity_usd,
        gross_leverage=plan.gross_leverage,
        orders=limited_orders,
    )


def risk_limited_orders(
    plan: ExecutionPlan,
    current_positions: list[CurrentPosition],
    specs: dict[str, Any],
    mid_prices: dict[str, float],
    equity_usd: float,
    max_order_lots: float,
    max_gross_leverage: float,
    max_largest_symbol_share: float,
    max_net_directional_share: float,
    max_margin_usage: float,
    max_platform_leverage: float,
) -> ExecutionPlan:
    """Keep the largest sequential order prefix that stays within live risk limits."""
    chunked = split_large_orders(plan, max_order_lots)
    accepted: list[OrderIntent] = []
    for order in chunked.orders:
        trial_orders = [*accepted, order]
        projected_positions = projected_positions_after_orders(current_positions, trial_orders)
        projected_risk = assess_live_positions(projected_positions, specs, mid_prices, equity_usd)
        reasons = live_risk_block_reasons(
            projected_risk,
            max_gross_leverage=max_gross_leverage,
            max_largest_symbol_share=max_largest_symbol_share,
            max_net_directional_share=max_net_directional_share,
            max_margin_usage=max_margin_usage,
            max_platform_leverage=max_platform_leverage,
        )
        if reasons:
            break
        accepted.append(order)

    return ExecutionPlan(
        timestamp=plan.timestamp,
        equity_usd=plan.equity_usd,
        gross_leverage=plan.gross_leverage,
        orders=accepted,
    )


def action_text(plan: ExecutionPlan) -> str:
    if not plan.orders:
        return "HOLD"
    lines = []
    for order in plan.orders:
        assert order.volume_lots is not None
        lines.append(f"{order.side.value.upper()} {order.symbol} {order.volume_lots:.2f}")
    return "; ".join(lines)


def write_ticket_files(plan: ExecutionPlan, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_timestamp = plan.timestamp.replace(":", "").replace("+", "_").replace("-", "")
    json_path = output_dir / f"auto_checkpoint_adjustment_{safe_timestamp}.json"
    markdown_path = output_dir / f"auto_checkpoint_adjustment_{safe_timestamp}.md"
    json_path.write_text(json.dumps(plan.model_dump(mode="json"), indent=2), encoding="utf-8")
    markdown_path.write_text(format_manual_ticket(plan), encoding="utf-8")
    return json_path, markdown_path


def build_adjustment(
    args: argparse.Namespace,
) -> tuple[ExecutionPlan, str, float, MT5PositionSnapshot, dict[str, float]]:
    config = load_config(args.config)
    symbols = configured_symbols(config)

    historical = pd.read_parquet(args.historical)
    live = read_mt5_live_bars_csv(args.mt5_bars_csv, args.assume_timezone, symbols)
    merged = merge_historical_and_live_bars(historical, live)
    args.output_bars.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(args.output_bars, index=False)
    mid_prices = latest_mid_prices(merged)

    snapshot = read_mt5_positions_csv(args.mt5_positions_csv, args.assume_timezone)
    specs = load_symbol_specs(args.symbol_specs)
    report = generate_decision_report(merged, config, config_name=args.config.name)
    report = rescale_decision_report(report, snapshot.equity)
    target = plan_from_decision(report, symbol_specs=specs)
    adjustment = adjustment_orders_from_positions(target, snapshot.positions)
    age = export_age_seconds(snapshot.exported_at)
    return adjustment, snapshot.exported_at, age, snapshot, mid_prices


def decide(
    plan: ExecutionPlan,
    exported_at: str,
    export_age: float,
    state: dict[str, Any],
    max_export_age_seconds: int,
    min_action_lots: float,
    max_auto_order_lots: float,
    split_large: bool,
    max_total_action_lots: float,
    risk_block_messages: list[str] | None = None,
) -> tuple[LoopDecision, ExecutionPlan]:
    if export_age > max_export_age_seconds:
        return (
            LoopDecision(
                status="STALE_EXPORT",
                message=f"MT5 export is stale: {exported_at} age={export_age:.0f}s",
                candle_timestamp=plan.timestamp,
                should_write=False,
            ),
            plan,
        )

    if state.get("last_written_timestamp") == plan.timestamp:
        return (
            LoopDecision(
                status="ALREADY_WRITTEN",
                message=f"Already handled candle {plan.timestamp}",
                candle_timestamp=plan.timestamp,
                should_write=False,
            ),
            plan,
        )

    filtered = meaningful_orders(plan, min_action_lots)
    if not filtered.orders:
        return (
            LoopDecision(
                status="HOLD",
                message="No meaningful orders after tiny-churn filter",
                candle_timestamp=plan.timestamp,
                should_write=False,
            ),
            filtered,
        )

    total = total_risk_increasing_lots(filtered)
    if total > max_total_action_lots:
        return (
            LoopDecision(
                status="BLOCKED_TOTAL_SIZE",
                message=(
                    f"Risk-increasing action {total:.2f} lots exceeds safety limit "
                    f"{max_total_action_lots:.2f}: {action_text(filtered)}"
                ),
                candle_timestamp=plan.timestamp,
                should_write=False,
            ),
            filtered,
        )

    if risk_block_messages:
        return (
            LoopDecision(
                status="RISK_BLOCKED",
                message="; ".join(risk_block_messages),
                candle_timestamp=plan.timestamp,
                should_write=False,
            ),
            filtered,
        )

    largest = max_order_lots(filtered)
    if largest > max_auto_order_lots:
        if split_large:
            split_plan = split_large_orders(filtered, max_auto_order_lots)
            return (
                LoopDecision(
                    status="WRITE_SPLIT",
                    message=(
                        f"Writing split proposed orders: {action_text(filtered)} "
                        f"as {len(split_plan.orders)} capped chunks"
                    ),
                    candle_timestamp=plan.timestamp,
                    should_write=True,
                ),
                split_plan,
            )
        return (
            LoopDecision(
                status="MANUAL_REQUIRED",
                message=(
                    f"Largest order {largest:.2f} lots exceeds auto cap "
                    f"{max_auto_order_lots:.2f}: {action_text(filtered)}"
                ),
                candle_timestamp=plan.timestamp,
                should_write=False,
            ),
            filtered,
        )

    return (
        LoopDecision(
            status="WRITE",
            message=f"Writing proposed orders: {action_text(filtered)}",
            candle_timestamp=plan.timestamp,
            should_write=True,
        ),
        filtered,
    )


def run_once(args: argparse.Namespace) -> LoopDecision:
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
    adjustment, exported_at, export_age, snapshot, mid_prices = build_adjustment(args)
    if not args.allow_one_step_flips:
        adjustment = limit_one_step_flips(adjustment, snapshot.positions)
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
        args.split_large_orders,
        args.max_total_action_lots,
        risk_block_messages,
    )

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
