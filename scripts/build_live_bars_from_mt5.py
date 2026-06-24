#!/usr/bin/env python3
"""Merge MT5-exported live M15 bars with historical research bars."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from quantbot.live.mt5_bridge import merge_historical_and_live_bars, read_mt5_live_bars_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--mt5-csv", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_guarded.yaml"))
    parser.add_argument("--output", type=Path, default=Path("data/live/bars_15min_live.parquet"))
    parser.add_argument("--max-symbol-lag-minutes", type=float, default=30.0)
    parser.add_argument("--allow-stale-symbols", action="store_true")
    parser.add_argument(
        "--assume-timezone",
        default="Europe/London",
        help="Timezone for naive MT5 timestamps.",
    )
    return parser.parse_args()


def load_config_symbols(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    return {str(leg["symbol"]).upper() for leg in config["legs"]}


def main() -> None:
    args = parse_args()
    symbols = load_config_symbols(args.config)
    historical = pd.read_parquet(args.historical)
    live = read_mt5_live_bars_csv(args.mt5_csv, assume_timezone=args.assume_timezone, symbols=symbols)
    merged = merge_historical_and_live_bars(historical, live)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(args.output, index=False)

    latest_by_symbol = live.groupby("symbol")["time"].max().sort_index()
    missing_symbols = sorted(symbols - set(latest_by_symbol.index))
    if missing_symbols:
        raise SystemExit(f"MT5 export missing configured symbols: {', '.join(missing_symbols)}")

    latest_time = latest_by_symbol.max()
    stale = latest_by_symbol[
        (latest_time - latest_by_symbol).dt.total_seconds() / 60.0 > args.max_symbol_lag_minutes
    ]
    if not stale.empty and not args.allow_stale_symbols:
        stale_text = ", ".join(f"{symbol}={time.isoformat()}" for symbol, time in stale.items())
        raise SystemExit(
            "MT5 export has stale configured symbols relative to the freshest symbol: "
            f"{stale_text}. Use --allow-stale-symbols only for inspection, not live tickets."
        )

    print(f"Wrote {len(merged):,} merged bars to {args.output}")
    print("Latest MT5 live bar by configured symbol:")
    for symbol, timestamp in latest_by_symbol.items():
        print(f"  {symbol}: {timestamp.isoformat()}")


if __name__ == "__main__":
    main()
