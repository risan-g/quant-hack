#!/usr/bin/env python3
"""Emit the latest portfolio decision as JSON and a readable table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quantbot.live.decision import generate_decision_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_guarded.yaml"))
    parser.add_argument("--output", type=Path, default=Path("reports/latest_decision.json"))
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    bars = pd.read_parquet(args.bars)
    config = load_config(args.config)
    report = generate_decision_report(bars, config, config_name=args.config.name)

    payload = report.model_dump(mode="json")
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("DECISION_REPORT")
    print(f"timestamp: {report.timestamp}")
    print(f"config: {report.config_name}")
    print(f"equity: ${report.equity_usd:,.2f}")
    print(f"drawdown: {report.drawdown:.2%}")
    print(f"gross_leverage: {report.gross_leverage:.2f}x")
    print(f"net_directional_leverage: {report.net_directional_leverage:.2f}x")
    print(f"gross_target_notional: ${report.gross_target_notional_usd:,.2f}")
    print()

    table = pd.DataFrame([leg.model_dump() for leg in report.legs])
    table["target_notional_usd"] = table["target_notional_usd"].map(lambda value: f"{value:,.0f}")
    table["target_leverage"] = table["target_leverage"].map(lambda value: f"{value:.2f}x")
    table["spread_fraction"] = table["spread_fraction"].map(lambda value: f"{value:.5%}")
    print(
        table[
            [
                "symbol",
                "strategy",
                "side",
                "allowed_by_regime",
                "target_leverage",
                "target_notional_usd",
                "mid_price",
                "spread_fraction",
                "spread_z",
            ]
        ].to_string(index=False)
    )
    print(f"\nwrote: {args.output}")


if __name__ == "__main__":
    main()
