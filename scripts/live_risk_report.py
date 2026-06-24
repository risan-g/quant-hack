#!/usr/bin/env python3
"""Assess current manual MT5 positions against live prices."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from quantbot.execution.adjustments import CurrentPosition
from quantbot.execution.models import OrderSide
from quantbot.execution.sizing import load_symbol_specs
from quantbot.risk.live import assess_live_positions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=Path("data/live/bars_15min_full_live.parquet"))
    parser.add_argument("--symbol-specs", type=Path, default=Path("configs/mt5_symbol_specs.yaml"))
    parser.add_argument("--equity", type=float, required=True)
    parser.add_argument(
        "--position",
        action="append",
        default=[],
        metavar="SYMBOL:SIDE:LOTS",
        help="Current MT5 net position, e.g. XAUUSD:buy:4.98. Repeat for each open symbol.",
    )
    return parser.parse_args()


def parse_positions(raw_positions: list[str]) -> list[CurrentPosition]:
    positions: list[CurrentPosition] = []
    for raw in raw_positions:
        parts = raw.split(":")
        if len(parts) != 3:
            raise SystemExit(f"Invalid position {raw!r}; expected SYMBOL:SIDE:LOTS")
        symbol, side_raw, lots_raw = parts
        positions.append(
            CurrentPosition(
                symbol=symbol.upper(),
                side=OrderSide(side_raw.lower()),
                volume_lots=float(lots_raw),
            )
        )
    return positions


def latest_mid_prices(bars: pd.DataFrame) -> dict[str, float]:
    latest = bars.sort_values("time").groupby("symbol").tail(1)
    return dict(zip(latest["symbol"], latest["mid_close"], strict=True))


def main() -> None:
    args = parse_args()
    bars = pd.read_parquet(args.bars)
    specs = load_symbol_specs(args.symbol_specs)
    positions = parse_positions(args.position)
    report = assess_live_positions(positions, specs, latest_mid_prices(bars), args.equity)
    print("LIVE_RISK_REPORT")
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    if report.warnings:
        print()
        print("RISK_ACTION: REVIEW / CONSIDER REDUCE")
    else:
        print()
        print("RISK_ACTION: OK")


if __name__ == "__main__":
    main()
