#!/usr/bin/env python3
"""Inspect the pricer-output dataset without loading every row."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from quantbot.competition import ELIGIBLE_INSTRUMENTS
from quantbot.data.pricer import discover_pricer_files, read_mid_quotes, resample_quotes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--sample-symbol", default="XAUUSD")
    parser.add_argument("--sample-date", default=None)
    parser.add_argument("--sample-frequency", default="15min")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = discover_pricer_files(args.data_dir)
    if not files:
        raise SystemExit(f"No pricer Parquet files found under {args.data_dir}")

    by_symbol: dict[str, list] = {}
    for item in files:
        by_symbol.setdefault(item.symbol, []).append(item)

    summary = {
        "data_dir": str(args.data_dir),
        "files": len(files),
        "symbols": sorted(by_symbol),
        "eligible_symbols_present": sorted(set(by_symbol).intersection(ELIGIBLE_INSTRUMENTS)),
        "extra_symbols_present": sorted(set(by_symbol).difference(ELIGIBLE_INSTRUMENTS)),
        "date_range": [min(item.date for item in files), max(item.date for item in files)],
        "rows": sum(item.rows for item in files),
        "size_gb": round(sum(item.size_bytes for item in files) / 1024**3, 3),
        "files_by_symbol": {
            symbol: {
                "files": len(items),
                "rows": sum(item.rows for item in items),
                "size_mb": round(sum(item.size_bytes for item in items) / 1024**2, 1),
                "first_date": min(item.date for item in items),
                "last_date": max(item.date for item in items),
            }
            for symbol, items in sorted(by_symbol.items())
        },
    }

    print(json.dumps(summary, indent=2))

    sample_candidates = by_symbol.get(args.sample_symbol, [])
    if args.sample_date:
        sample_candidates = [item for item in sample_candidates if item.date == args.sample_date]
    if sample_candidates:
        sample = sample_candidates[0]
        parquet = pq.ParquetFile(sample.path)
        print("\nSAMPLE_FILE")
        print(sample.path)
        print("\nSCHEMA")
        print(parquet.schema)
        quotes = read_mid_quotes(sample.path)
        print("\nHEAD")
        print(quotes.head(5).to_string(index=False))
        print("\nRESAMPLED")
        print(resample_quotes(quotes, args.sample_frequency).head(10).to_string(index=False))


if __name__ == "__main__":
    main()
