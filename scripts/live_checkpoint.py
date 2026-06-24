#!/usr/bin/env python3
"""Run one live checkpoint from MT5 bars and MT5-exported current positions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quantbot.execution.adjustments import adjustment_orders_from_positions
from quantbot.execution.formatting import format_manual_ticket
from quantbot.execution.planner import plan_from_decision
from quantbot.execution.proposed_orders import write_proposed_orders_csv
from quantbot.execution.sizing import load_symbol_specs
from quantbot.live.decision import generate_decision_report, rescale_decision_report
from quantbot.live.mt5_bridge import merge_historical_and_live_bars, read_mt5_live_bars_csv
from quantbot.live.mt5_positions import read_mt5_positions_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--mt5-bars-csv", type=Path, required=True)
    parser.add_argument("--mt5-positions-csv", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_guarded.yaml"))
    parser.add_argument("--symbol-specs", type=Path, default=Path("configs/mt5_symbol_specs.yaml"))
    parser.add_argument("--output-bars", type=Path, default=Path("data/live/bars_15min_full_live.parquet"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/execution_tickets"))
    parser.add_argument(
        "--proposed-orders-csv",
        type=Path,
        default=None,
        help="Optional MT5 Files path for dry-run proposed orders CSV.",
    )
    parser.add_argument(
        "--proposed-live",
        action="store_true",
        help=(
            "Write proposed orders with dry_run=false for the live EA. "
            "Use only with the EA's own live-trading gates and lot caps."
        ),
    )
    parser.add_argument(
        "--assume-timezone",
        default="Europe/London",
        help="Timezone for naive MT5 timestamps.",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def configured_symbols(config: dict[str, Any]) -> set[str]:
    return {str(leg["symbol"]).upper() for leg in config["legs"]}


def print_action(adjustment_orders: list[Any]) -> None:
    print()
    if not adjustment_orders:
        print("ACTION: HOLD - no MT5 orders required")
        return
    print("ACTION:")
    for order in adjustment_orders:
        volume = "UNKNOWN" if order.volume_lots is None else f"{order.volume_lots:.2f}"
        print(f"  {order.side.value.upper()} {order.symbol} {volume}")


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    symbols = configured_symbols(config)

    historical = pd.read_parquet(args.historical)
    live = read_mt5_live_bars_csv(args.mt5_bars_csv, args.assume_timezone, symbols)
    merged = merge_historical_and_live_bars(historical, live)
    args.output_bars.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(args.output_bars, index=False)

    snapshot = read_mt5_positions_csv(args.mt5_positions_csv, args.assume_timezone)
    specs = load_symbol_specs(args.symbol_specs)
    report = generate_decision_report(merged, config, config_name=args.config.name)
    report = rescale_decision_report(report, snapshot.equity)
    target = plan_from_decision(report, symbol_specs=specs)
    adjustment = adjustment_orders_from_positions(target, snapshot.positions)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    safe_timestamp = adjustment.timestamp.replace(":", "").replace("+", "_").replace("-", "")
    json_path = args.output_dir / f"live_checkpoint_adjustment_{safe_timestamp}.json"
    markdown_path = args.output_dir / f"live_checkpoint_adjustment_{safe_timestamp}.md"
    json_path.write_text(json.dumps(adjustment.model_dump(mode="json"), indent=2), encoding="utf-8")
    markdown_path.write_text(format_manual_ticket(adjustment), encoding="utf-8")
    if args.proposed_orders_csv is not None:
        write_proposed_orders_csv(adjustment, args.proposed_orders_csv, dry_run=not args.proposed_live)

    print("MT5_ACCOUNT")
    print(snapshot.model_dump_json(indent=2))
    print()
    print("TARGET_PLAN")
    print(json.dumps(target.model_dump(mode="json"), indent=2))
    print()
    print("ADJUSTMENT_PLAN")
    print(json.dumps(adjustment.model_dump(mode="json"), indent=2))
    print_action(adjustment.orders)
    print()
    print(f"Wrote {json_path} and {markdown_path}")
    if args.proposed_orders_csv is not None:
        mode = "live" if args.proposed_live else "dry-run"
        print(f"Wrote {mode} proposed orders to {args.proposed_orders_csv}")


if __name__ == "__main__":
    main()
