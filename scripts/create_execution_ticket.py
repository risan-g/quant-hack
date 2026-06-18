#!/usr/bin/env python3
"""Create a manual execution ticket from the latest decision report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quantbot.execution.adapters import ManualExecutionAdapter
from quantbot.execution.planner import plan_from_decision
from quantbot.live.decision import generate_decision_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=Path("data/processed/bars_15min.parquet"))
    parser.add_argument("--config", type=Path, default=Path("configs/portfolio_guarded.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/execution_tickets"))
    parser.add_argument("--min-notional-usd", type=float, default=10_000.0)
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def main() -> None:
    args = parse_args()
    bars = pd.read_parquet(args.bars)
    config = load_config(args.config)
    report = generate_decision_report(bars, config, config_name=args.config.name)
    plan = plan_from_decision(report, min_notional_usd=args.min_notional_usd)
    receipt = ManualExecutionAdapter(args.output_dir).submit(plan)

    print("EXECUTION_PLAN")
    print(json.dumps(plan.model_dump(mode="json"), indent=2))
    print()
    print("RECEIPT")
    print(receipt.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
