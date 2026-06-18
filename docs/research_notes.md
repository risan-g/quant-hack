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
