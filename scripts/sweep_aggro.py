#!/usr/bin/env python3
import itertools
from pathlib import Path
import pandas as pd
import yaml

from quantbot.backtest.metrics import summarize_returns
from quantbot.research.portfolio import build_enriched_bars, build_unit_returns
from quantbot.risk.governor import AdaptiveRiskConfig, AdaptiveRiskGovernor

def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)

def score_row(metrics: dict) -> float:
    return metrics["return"] - 1.50 * metrics["max_drawdown"] + 4.0 * metrics["sharpe"]

def main():
    config = load_config(Path("configs/portfolio_aggro.yaml"))
    bars = pd.read_parquet(Path("data/live/bars_15min_full_live.parquet"))
    enriched = build_enriched_bars(bars)
    aligned = build_unit_returns(enriched, config["legs"])
    unit_returns = aligned.sum(axis=1)

    rows = []
    # Test aggressive bases from 10 to 18
    # Test aggressive attacks from 15 to 29
    # Test soft/hard drawdowns from 0.15 to 0.35
    grid = itertools.product(
        [10.0, 12.0, 15.0],        # base
        [18.0, 22.0, 26.0, 28.0],  # attack
        [2.0, 3.0],                # defend
        [0.10, 0.15],              # soft_dd
        [0.20, 0.25, 0.30],        # hard_dd
        [-0.02, -0.03],            # recent_loss_cut
    )
    for base, attack, defend, soft_dd, hard_dd, loss_cut in grid:
        if attack <= base or hard_dd <= soft_dd:
            continue
        risk_config = AdaptiveRiskConfig(
            base_gross_leverage=base,
            attack_gross_leverage=attack,
            defend_gross_leverage=defend,
            max_gross_leverage=min(attack + 2.0, 29.5),
            soft_drawdown=soft_dd,
            hard_drawdown=hard_dd,
            attack_drawdown=0.03,
            recent_loss_window=16,
            recent_loss_cut=loss_cut,
            recovery_bars=8,
        )
        result = AdaptiveRiskGovernor(risk_config).run(unit_returns)
        metrics = summarize_returns(result.returns)
        rows.append(
            {
                **metrics,
                "utility": score_row(metrics),
                "avg_gross_leverage": float(result.gross_leverage.mean()),
                "min_gross_leverage": float(result.gross_leverage.min()),
                "max_gross_leverage": float(result.gross_leverage.max()),
                "base_gross_leverage": base,
                "attack_gross_leverage": attack,
                "defend_gross_leverage": defend,
                "soft_drawdown": soft_dd,
                "hard_drawdown": hard_dd,
                "recent_loss_cut": loss_cut,
            }
        )

    report = pd.DataFrame(rows).sort_values(
        ["utility", "return", "max_drawdown"], ascending=[False, False, True]
    )
    print(report.head(15).to_string(index=False))

if __name__ == "__main__":
    main()
