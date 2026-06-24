#!/usr/bin/env python3
"""Create netting-mode adjustment orders from current MT5 positions to target ticket."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quantbot.execution.adjustments import CurrentPosition, adjustment_orders_from_positions
from quantbot.execution.formatting import format_manual_ticket
from quantbot.execution.models import OrderSide
from quantbot.execution.planner import plan_from_decision
from quantbot.execution.sizing import load_symbol_specs
from quantbot.live.decision import generate_decision_report, rescale_decision_report
from quantbot.live.mt5_positions import read_mt5_positions_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=Path("data/live/bars_15min_fx_live.parquet"))
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_fx_live.yaml"))
    parser.add_argument("--symbol-specs", type=Path, default=Path("configs/mt5_symbol_specs.yaml"))
    parser.add_argument("--execution-equity", type=float, default=None)
    parser.add_argument(
        "--positions-csv",
        type=Path,
        default=None,
        help="MT5-exported positions CSV. If provided, positions and equity are read from it.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("reports/execution_tickets"))
    parser.add_argument(
        "--position",
        action="append",
        default=[],
        metavar="SYMBOL:SIDE:LOTS",
        help="Current MT5 net position, e.g. USDJPY:sell:21. Repeat for each open symbol.",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def parse_positions(raw_positions: list[str]) -> list[CurrentPosition]:
    positions: list[CurrentPosition] = []
    for raw in raw_positions:
        parts = raw.split(":")
        if len(parts) != 3:
            raise SystemExit(f"Invalid position {raw!r}; expected SYMBOL:SIDE:LOTS")
        symbol, side_raw, lots_raw = parts
        side = OrderSide(side_raw.lower())
        lots = float(lots_raw)
        positions.append(CurrentPosition(symbol=symbol.upper(), side=side, volume_lots=lots))
    return positions


def main() -> None:
    args = parse_args()
    bars = pd.read_parquet(args.bars)
    config = load_config(args.config)
    specs = load_symbol_specs(args.symbol_specs)
    if args.positions_csv is not None:
        snapshot = read_mt5_positions_csv(args.positions_csv)
        positions = snapshot.positions
        execution_equity = snapshot.equity if args.execution_equity is None else args.execution_equity
    else:
        positions = parse_positions(args.position)
        if args.execution_equity is None:
            raise SystemExit("--execution-equity is required unless --positions-csv is provided")
        execution_equity = args.execution_equity

    report = generate_decision_report(bars, config, config_name=args.config.name)
    report = rescale_decision_report(report, execution_equity)
    target = plan_from_decision(report, symbol_specs=specs)
    adjustment = adjustment_orders_from_positions(target, positions)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    safe_timestamp = adjustment.timestamp.replace(":", "").replace("+", "_").replace("-", "")
    json_path = args.output_dir / f"adjustment_ticket_{safe_timestamp}.json"
    markdown_path = args.output_dir / f"adjustment_ticket_{safe_timestamp}.md"
    json_path.write_text(json.dumps(adjustment.model_dump(mode="json"), indent=2), encoding="utf-8")
    markdown_path.write_text(format_manual_ticket(adjustment), encoding="utf-8")

    print("TARGET_PLAN")
    print(json.dumps(target.model_dump(mode="json"), indent=2))
    print()
    print("ADJUSTMENT_PLAN")
    print(json.dumps(adjustment.model_dump(mode="json"), indent=2))
    print()
    print(f"Wrote {json_path} and {markdown_path}")


if __name__ == "__main__":
    main()
