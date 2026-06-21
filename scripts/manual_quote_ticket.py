#!/usr/bin/env python3
"""Re-size a generated execution ticket with live quotes copied from MT5."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quantbot.execution.adapters import ManualExecutionAdapter
from quantbot.execution.planner import plan_from_decision, reprice_plan_with_quotes
from quantbot.execution.sizing import load_symbol_specs
from quantbot.live.decision import generate_decision_report, rescale_decision_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_guarded.yaml"))
    parser.add_argument("--symbol-specs", type=Path, default=Path("configs/mt5_symbol_specs.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/execution_tickets"))
    parser.add_argument("--min-notional-usd", type=float, default=10_000.0)
    parser.add_argument(
        "--execution-equity",
        type=float,
        default=None,
        help="Override ticket sizing equity with actual live account equity.",
    )
    parser.add_argument(
        "--quote",
        action="append",
        default=[],
        metavar="SYMBOL:BID:ASK",
        help="Live MT5 quote, e.g. XAUUSD:4099.10:4099.42. Repeat for each active symbol.",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def parse_quotes(raw_quotes: list[str]) -> dict[str, float]:
    quotes: dict[str, float] = {}
    for raw in raw_quotes:
        parts = raw.split(":")
        if len(parts) != 3:
            raise SystemExit(f"Invalid quote {raw!r}; expected SYMBOL:BID:ASK")
        symbol, bid_raw, ask_raw = parts
        bid = float(bid_raw)
        ask = float(ask_raw)
        if bid <= 0 or ask <= 0 or ask < bid:
            raise SystemExit(f"Invalid bid/ask for {symbol}: bid={bid}, ask={ask}")
        quotes[symbol.upper()] = (bid + ask) / 2.0
    return quotes


def main() -> None:
    args = parse_args()
    bars = pd.read_parquet(args.bars)
    config = load_config(args.config)
    specs = load_symbol_specs(args.symbol_specs)
    live_mid_prices = parse_quotes(args.quote)

    report = generate_decision_report(bars, config, config_name=args.config.name)
    if args.execution_equity is not None:
        report = rescale_decision_report(report, args.execution_equity)
    plan = plan_from_decision(report, min_notional_usd=args.min_notional_usd)
    repriced = reprice_plan_with_quotes(plan, specs, live_mid_prices)
    receipt = ManualExecutionAdapter(args.output_dir).submit(repriced)

    print("LIVE_QUOTE_EXECUTION_PLAN")
    print(json.dumps(repriced.model_dump(mode="json"), indent=2))
    print()
    print("RECEIPT")
    print(receipt.model_dump_json(indent=2))
    print()
    print("WARNING")
    print("This only re-sizes existing strategy targets with live MT5 quotes.")
    print("It does not recompute strategy signals from live MT5 bar history.")


if __name__ == "__main__":
    main()
