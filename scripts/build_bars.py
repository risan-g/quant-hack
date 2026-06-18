#!/usr/bin/env python3
"""Build compact quote bars from raw pricer-output Parquet files."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from quantbot.competition import ELIGIBLE_INSTRUMENTS
from quantbot.data.pricer import discover_pricer_files, read_mid_quotes, resample_quotes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--frequency", default="15min")
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=sorted(ELIGIBLE_INSTRUMENTS),
        help="Symbols to include. Defaults to competition-eligible symbols.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    wanted = set(args.symbols)
    files = [item for item in discover_pricer_files(args.data_dir) if item.symbol in wanted]
    if not files:
        raise SystemExit("No matching files found.")

    frames: list[pd.DataFrame] = []
    for idx, item in enumerate(files, start=1):
        quotes = read_mid_quotes(item.path)
        bars = resample_quotes(quotes, args.frequency)
        bars.insert(0, "symbol", item.symbol)
        bars.insert(1, "source_date", item.date)
        frames.append(bars)
        print(f"[{idx:03d}/{len(files):03d}] {item.symbol} {item.date}: {len(bars)} bars")

    result = pd.concat(frames, ignore_index=True).sort_values(["symbol", "time"])
    result.to_parquet(args.output, index=False)
    print(f"Wrote {len(result):,} bars to {args.output}")


if __name__ == "__main__":
    main()
