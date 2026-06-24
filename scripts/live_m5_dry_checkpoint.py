#!/usr/bin/env python3
"""Run a dry 5-minute checkpoint from MT5-exported M5 bars."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quantbot.execution.adjustments import adjustment_orders_from_positions
from quantbot.execution.planner import plan_from_decision
from quantbot.execution.sizing import load_symbol_specs
from quantbot.live.decision import generate_decision_report, rescale_decision_report
from quantbot.live.mt5_bridge import read_mt5_live_bars_csv
from quantbot.live.mt5_positions import read_mt5_positions_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mt5-bars-csv", type=Path, required=True)
    parser.add_argument("--mt5-positions-csv", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_scanner_attack.yaml"))
    parser.add_argument("--symbol-specs", type=Path, default=Path("configs/mt5_symbol_specs.yaml"))
    parser.add_argument("--min-bars-per-symbol", type=int, default=96)
    parser.add_argument("--max-symbol-lag-minutes", type=float, default=15.0)
    parser.add_argument("--assume-timezone", default="Europe/London")
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def configured_symbols(config: dict[str, Any]) -> set[str]:
    return {str(leg["symbol"]).upper() for leg in config["legs"]}


def validate_live_bars(bars: pd.DataFrame, symbols: set[str], min_bars: int, max_lag: float) -> None:
    counts = bars.groupby("symbol").size()
    missing = sorted(symbol for symbol in symbols if counts.get(symbol, 0) < min_bars)
    if missing:
        raise SystemExit(
            "M5 dry-run needs more bars before it is meaningful: "
            + ", ".join(f"{symbol}={counts.get(symbol, 0)}" for symbol in missing)
        )

    latest = bars.groupby("symbol")["time"].max().sort_index()
    freshest = latest.max()
    stale = latest[(freshest - latest).dt.total_seconds() / 60.0 > max_lag]
    if not stale.empty:
        stale_text = ", ".join(f"{symbol}={time.isoformat()}" for symbol, time in stale.items())
        raise SystemExit(f"M5 dry-run has stale configured symbols: {stale_text}")


def print_action(orders: list[Any]) -> None:
    print()
    if not orders:
        print("M5 DRY ACTION: HOLD")
        return
    print("M5 DRY ACTION:")
    for order in orders:
        volume = "UNKNOWN" if order.volume_lots is None else f"{order.volume_lots:.2f}"
        print(f"  {order.side.value.upper()} {order.symbol} {volume}")


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    symbols = configured_symbols(config)

    bars = read_mt5_live_bars_csv(args.mt5_bars_csv, args.assume_timezone, symbols)
    validate_live_bars(bars, symbols, args.min_bars_per_symbol, args.max_symbol_lag_minutes)

    snapshot = read_mt5_positions_csv(args.mt5_positions_csv, args.assume_timezone)
    specs = load_symbol_specs(args.symbol_specs)
    report = generate_decision_report(bars, config, config_name=f"{args.config.name}:M5_DRY")
    report = rescale_decision_report(report, snapshot.equity)
    target = plan_from_decision(report, symbol_specs=specs)
    adjustment = adjustment_orders_from_positions(target, snapshot.positions)

    print("M5_MT5_ACCOUNT")
    print(snapshot.model_dump_json(indent=2))
    print()
    print("M5_TARGET_PLAN")
    print(json.dumps(target.model_dump(mode="json"), indent=2))
    print()
    print("M5_ADJUSTMENT_PLAN")
    print(json.dumps(adjustment.model_dump(mode="json"), indent=2))
    print_action(adjustment.orders)


if __name__ == "__main__":
    main()
