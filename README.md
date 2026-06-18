# AI Trading Competition Plan

This repo is for a solo AI/quant trading competition using simulated funds, real quotes, and a formula-based ranking system.

## Current Known Rules

- Initial equity: 1,000,000 USD
- Max platform leverage: 30x
- Tradable instruments:
  - FX: AUD/USD, EUR/CHF, EUR/GBP, EUR/USD, GBP/USD, USD/CAD, USD/CHF, USD/JPY
  - Metals: XAG/USD, XAU/USD
  - Crypto: BAR/USD, BTC/USD, ETH/USD, SOL/USD, XRP/USD
- Composite score:
  - 70% return rank
  - 15% maximum drawdown rank
  - 10% Sharpe rank
  - 5% risk discipline
- Sharpe is non-annualized and computed from 15-minute account equity returns.
- Best Sharpe eligibility requires finals, Top 50 overall, no red-line violations, and at least 30 trades.

## Hard Risk Constraints

Treat 30x leverage as a danger zone, not a target.

- Forced liquidation means immediate elimination.
- Margin usage above 90% for 30 minutes loses risk discipline points.
- Margin usage above 95% for 15 minutes loses more points.
- Margin usage above 98% for 10 minutes triggers compliance review.
- Effective leverage above 28x for 30 minutes loses points.
- Effective leverage above 29x for 15 minutes loses more points.
- Near-30x leverage for 10 minutes triggers compliance review.
- Single-instrument exposure above 90% for 30 minutes loses points.
- Net directional exposure above 95% for 30 minutes loses points.

Internal system limits should be stricter than the public limits.

## Strategic Objective

This is a rank optimization problem, not a normal long-term investment problem.

Round behavior should depend on leaderboard state:

- Below target qualification zone: controlled aggression.
- Safely above qualification zone: protect equity and drawdown.
- Blind final phase: run robust composite-score strategy.

The system should separate:

- Prediction: what looks attractive.
- Allocation: how much exposure to take.
- Risk: what is allowed.
- Execution: how orders are actually placed.

## Architecture Target

```text
market data
  -> feature pipeline
  -> strategy ensemble
  -> portfolio allocator
  -> risk governor
  -> execution adapter
  -> trade/equity logger
  -> monitoring and post-trade analysis
```

The AI layer should not place unchecked trades. It can summarize regimes, suggest parameters, and produce explanations, but deterministic code should enforce risk.

## Platform Unknowns

The console currently appears to expose rules and a backtest dataset download, but not developer docs. The site states that trading method selection opens on Jun 19 at 08:00 BST. The key missing details are:

- API availability and base URL.
- Authentication method.
- Market data endpoint.
- Historical data access.
- Order placement endpoint.
- Account, equity, positions, and open-order endpoint.
- Rate limits.
- Exact instrument symbols.
- WebSocket streaming availability.
- MT5 server/login details.
- Whether automated browser/chat trading is permitted.
- Whether the platform will expose peer logs via API or only UI.

## Backtest Data

The platform exposes a "Backtest Data" page with a Parquet download for Week 1 strategy building and local backtesting. The dataset may be large, so the loader should inspect metadata first and avoid reading the full dataset into memory.

Initial data workflow:

1. Download the Parquet artifact once.
2. Inspect schema, columns, row groups, date range, and symbol coverage.
3. Create small sampled extracts for fast iteration.
4. Resample to 1-minute, 5-minute, and 15-minute bars.
5. Backtest strategy candidates with transaction-cost/spread assumptions when bid/ask exists.
6. Optimize against a proxy for the competition composite score, not raw PnL alone.

## Discord Message To Send

```text
Hi, I am preparing my trading system for the competition. Where can we find the technical trading docs?

Specifically looking for:
- REST/WebSocket API docs, if available
- API key/auth instructions
- historical data access/download
- exact instrument symbols
- order placement/account/positions endpoints
- rate limits
- MT5 login/server setup, if API docs are not public yet
- whether automated strategies may trade through API/MT5 from launch

The rules mention API, MT5, and chat interface, but I only see the rules/trading setup page at the moment.
```

## Build Path If Docs Arrive

1. Implement typed config and schemas.
2. Implement platform client.
3. Implement market data recorder.
4. Implement account and position snapshot loop.
5. Implement risk governor.
6. Implement order executor.
7. Implement baseline strategies.
8. Implement monitoring and emergency kill switch.
9. Deploy worker.

## Build Path If Docs Do Not Arrive Before Launch

Build a platform-agnostic decision engine that outputs trade recommendations and risk limits every 15 minutes.

Execution modes:

- Manual execution through the web UI.
- MT5 execution if credentials appear.
- Chat-interface execution if allowed.
- API execution if docs appear later.

The core strategy/risk system remains the same; only the execution adapter changes.

## Local Research Commands

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Inspect the raw dataset:

```bash
.venv/bin/python scripts/inspect_data.py pricer-output-2026-05-11_2026-06-10 --sample-symbol XAUUSD
```

Build compact 15-minute bars:

```bash
.venv/bin/python scripts/build_bars.py pricer-output-2026-05-11_2026-06-10 --output data/processed/bars_15min.parquet
```

Run first-pass signal research:

```bash
.venv/bin/python scripts/research_signals.py --bars data/processed/bars_15min.parquet --output reports/signal_research.csv --leverage 5
```

Run the current baseline portfolio:

```bash
.venv/bin/python scripts/backtest_portfolio.py --bars data/processed/bars_15min.parquet --config configs/portfolio_baseline.yaml
```

Run the adaptive portfolio:

```bash
.venv/bin/python scripts/backtest_adaptive_portfolio.py --bars data/processed/bars_15min.parquet --config configs/portfolio_adaptive.yaml
.venv/bin/python scripts/backtest_adaptive_portfolio.py --bars data/processed/bars_15min.parquet --config configs/portfolio_guarded.yaml --equity-output reports/guarded_equity.csv
```

Emit latest decision report:

```bash
.venv/bin/python scripts/decision_report.py --bars data/processed/bars_15min.parquet --config configs/portfolio_guarded.yaml
```

Create a manual execution ticket from latest decision:

```bash
.venv/bin/python scripts/create_execution_ticket.py --bars data/processed/bars_15min.parquet --config configs/portfolio_guarded.yaml
```

Sweep adaptive risk parameters:

```bash
.venv/bin/python scripts/sweep_risk_configs.py --bars data/processed/bars_15min.parquet --config configs/portfolio_adaptive.yaml
```

Evaluate adaptive performance by subperiod:

```bash
.venv/bin/python scripts/evaluate_periods.py --bars data/processed/bars_15min.parquet --config configs/portfolio_adaptive.yaml
```

Sweep regime filters:

```bash
.venv/bin/python scripts/sweep_regime_filters.py --bars data/processed/bars_15min.parquet --config configs/portfolio_adaptive.yaml
```

Run walk-forward strategy selection:

```bash
.venv/bin/python scripts/walk_forward_select.py --bars data/processed/bars_15min.parquet
.venv/bin/python scripts/walk_forward_select.py --bars data/processed/bars_15min.parquet --robust --output reports/walk_forward_robust.csv
```
