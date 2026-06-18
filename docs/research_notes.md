# Research Notes

## Dataset

The downloaded backtest data is xSyphon pricer output from 2026-05-11 through 2026-06-10.

It contains 531 daily Parquet files, one file per symbol per UTC trading day, with about 789 million quote rows and 20.3 GiB of compressed data.

Each row includes:

- `time`: UTC quote timestamp
- `sym`: instrument
- `provider`: pricer channel
- `bid`, `ask`: best quote
- `bidprices`, `bidsizes`, `askprices`, `asksizes`: up to 5 levels of ladder depth

## Competition Symbols Present

Present:

- AUDUSD
- EURCHF
- EURGBP
- EURUSD
- GBPUSD
- USDCAD
- USDCHF
- USDJPY
- XAGUSD
- XAUUSD

Missing from this dataset:

- BARUSD
- BTCUSD
- ETHUSD
- SOLUSD
- XRPUSD

This means the historical backtest file supports FX/metals research but not crypto research. Crypto strategy will need live platform data, another source, or a separate dataset if the organizers expose one later.

## First Bar Build

Created `data/processed/bars_15min.parquet` using eligible instruments present in the dataset.

- Frequency: 15 minutes
- Rows: 21,953
- Output columns include bid/ask OHLC, mid OHLC, mean/max spread, and tick count.

## First Signal Sweep

Ran simple momentum, breakout, and mean-reversion strategies on 15-minute bars with spread costs and 5x leverage.

Early observations:

- XAUUSD momentum looks promising for return generation.
- XAGUSD can produce large returns but drawdown is very high.
- USDJPY mean reversion is much smoother and useful as a stabilizing leg.
- Some FX strategies are positive but low-return; they are better as diversification/risk stabilizers than as podium engines.

## Baseline Portfolio

Config: `configs/portfolio_baseline.yaml`

Gross leverage: 6x

Legs:

- XAUUSD `momentum_8`, weight 30%
- USDJPY `mean_reversion_8`, weight 25%
- USDCHF `momentum_32`, weight 15%
- AUDUSD `breakout_32`, weight 15%
- USDCAD `momentum_32`, weight 15%

Backtest result on available sample:

- Return: 16.07%
- Max drawdown: 10.34%
- Competition-style 15-minute Sharpe: 0.0255
- Final equity from 1,000,000 USD: 1,160,664.86 USD

Interpretation: this is a first benchmark, not a final strategy. It is plausibly Top-100-shaped but probably needs stronger adaptive risk and crypto/live-data integration for a podium attempt.

## Adaptive Risk Sweep

Added an adaptive gross-leverage governor that scales portfolio risk from prior equity state only:

- Attack mode near equity highs.
- Base mode during normal conditions.
- Defend mode after recent losses or drawdown.
- Flattening when hard drawdown is breached.

The first hand-set adaptive config was too defensive:

- Return: 13.78%
- Max drawdown: 10.83%
- Average gross leverage: 5.52x

A parameter sweep found a stronger profile:

- Base gross leverage: 7x
- Attack gross leverage: 10x
- Defend gross leverage: 1x
- Soft drawdown: 10%
- Hard drawdown: 14%
- Recent-loss cut: -1.5% across 16 bars

Result:

- Return: 24.64%
- Max drawdown: 9.18%
- Competition-style 15-minute Sharpe: 0.0324
- Average gross leverage: 6.33x
- Max gross leverage: 10x

Interpretation: adaptive risk is promising, but this is still in-sample. Next steps are walk-forward validation, richer strategy search, and a live-data plan for crypto.

## Subperiod Evaluation

Evaluated the tuned adaptive portfolio over three calendar slices, resetting risk state at the start of each slice:

| Period | Return | Max Drawdown | 15-min Sharpe |
| --- | ---: | ---: | ---: |
| 2026-05-11 to 2026-05-20 | 4.28% | 8.94% | 0.0188 |
| 2026-05-21 to 2026-05-29 | 9.78% | 5.32% | 0.0453 |
| 2026-05-31 to 2026-06-10 | 9.42% | 7.02% | 0.0343 |

Interpretation: the profile is not dependent on a single profitable slice, though early-sample performance is materially weaker. This supports continuing with the portfolio but not trusting it blindly.

## Walk-Forward Selection

Added a first walk-forward selector:

1. Score candidate symbol/strategy pairs on a training period.
2. Select a diversified top-N portfolio with at most one strategy per symbol.
3. Weight selected legs by positive training utility.
4. Evaluate on the following unseen period with the adaptive risk governor.

This is deliberately simple. Its purpose is to detect whether hand-picked strategy legs are robust or whether selection collapses out of sample.

Naive train-then-select walk-forward results:

| Split | Test Return | Test Max Drawdown | Test Sharpe |
| --- | ---: | ---: | ---: |
| 2026-05-11..20 -> 2026-05-21..29 | -9.36% | 14.03% | -0.0319 |
| 2026-05-21..29 -> 2026-05-31..06-10 | -6.78% | 14.00% | -0.0219 |

Robust daily-stability selection:

| Split | Test Return | Test Max Drawdown | Test Sharpe |
| --- | ---: | ---: | ---: |
| 2026-05-11..20 -> 2026-05-21..29 | -10.68% | 12.42% | -0.0666 |
| 2026-05-21..29 -> 2026-05-31..06-10 | 1.59% | 6.66% | 0.0087 |

Interpretation: unconstrained strategy selection is currently not robust enough. The stronger path is to use a small, human-reviewed portfolio of structurally plausible legs and use data-driven sweeps primarily for risk calibration. Strategy selection should be constrained by market role and regime logic, not pure recent backtest ranking.

## Regime Filters

Added optional per-leg regime filters based on:

- realized-volatility ratio
- trend strength
- spread z-score

The first hand-authored volatility/trend regime config was too restrictive:

- Return: -2.39%
- Max drawdown: 8.47%
- Sharpe: -0.0041

A sweep of simple filter families found that the best current variant is much simpler: apply a spread guard to momentum/breakout legs and a looser spread guard to the mean-reversion leg.

| Variant | Return | Max Drawdown | 15-min Sharpe |
| --- | ---: | ---: | ---: |
| momentum/breakout spread guard | 28.62% | 8.72% | 0.0366 |
| spread-only all legs | 25.94% | 8.91% | 0.0336 |
| mean-reversion trend guard | 25.12% | 8.96% | 0.0327 |
| loose volatility filter | 22.80% | 7.85% | 0.0332 |
| no regime filter | 24.64% | 9.18% | 0.0324 |

Current promoted config: `configs/portfolio_guarded.yaml`.

Subperiod evaluation for the guarded config:

| Period | Return | Max Drawdown | 15-min Sharpe |
| --- | ---: | ---: | ---: |
| 2026-05-11 to 2026-05-20 | 7.86% | 7.54% | 0.0312 |
| 2026-05-21 to 2026-05-29 | 8.93% | 5.21% | 0.0428 |
| 2026-05-31 to 2026-06-10 | 12.40% | 7.30% | 0.0435 |

Interpretation: quote quality/spread filtering appears useful and improved all three subperiods. More elaborate volatility/trend filters need better validation before they should affect live trading.

## Decision Output

Added a decision report layer that converts the latest bars plus portfolio config into:

- current estimated equity and drawdown
- next gross leverage from the adaptive risk governor
- per-leg signal side
- regime permission status
- target leverage and notional per instrument
- net directional leverage and gross notional

This is execution-adapter agnostic. It can drive API orders, MT5 orders, chat/manual execution, or a dashboard once the competition trading method unlocks.

## Execution Planning

Added typed execution models and a manual execution adapter.

The execution planner converts decision report target notionals into order intents:

- `symbol`
- side: buy/sell
- order type
- notional USD
- target leverage
- reason string

The manual adapter writes a JSON ticket that can be used for manual entry, chat-interface execution, or as the contract for future API/MT5 adapters.
