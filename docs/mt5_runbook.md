# MT5 Runbook

This runbook is for operating the competition account through MetaTrader 5.

## Current Status

- MT5 login works.
- Account balance/equity shows 1,000,000 USD.
- All 15 competition symbols are visible.
- Journal reports trading enabled in netting mode.
- Tiny `EURUSD` `0.01` open-close test succeeded after launch.
- Trade tab was flat after the test and Journal was clean.

Strategy-sized trades still require a fresh live-data ticket. Do not execute the
old historical ticket from the June 10 bar file.

## Visible Competition Symbols

- EURUSD
- GBPUSD
- AUDUSD
- USDCHF
- USDJPY
- USDCAD
- EURGBP
- EURCHF
- XAUUSD
- BTCUSD
- ETHUSD
- SOLUSD
- XAGUSD
- XRPUSD
- BARUSD

## Verified Contract Specs

XAUUSD:

- Contract size: 100 XAU
- Minimum volume: 0.01 lots
- Maximum volume: 100 lots
- Volume step: 0.01 lots
- Profit currency: USD

USDJPY / USDCHF / USDCAD:

- Contract size: 100,000 USD
- Minimum volume: 0.01 lots
- Maximum volume: 100 lots
- Volume step: 0.01 lots

## First Trade Test When Server Enables Trading

Use EURUSD, not gold or crypto.

1. Select `EURUSD` in Market Watch.
2. Open New Order.
3. Set Type to Market Execution.
4. Set Volume to `0.01`.
5. Leave Stop Loss and Take Profit blank.
6. Click Buy by Market.
7. Verify the position appears in the Trade tab.
8. Immediately close the position.
9. Verify no open position remains.
10. Check the Journal tab for errors.

Only after this test succeeds should strategy-sized trades be considered.

## Launch Decision Tree

Use this sequence around the official 22:00 BST launch.

1. Confirm the Trade tab shows no open positions.
2. Confirm Market Watch still shows all competition symbols.
3. Try exactly one tiny EURUSD `0.01` market order.
4. If MT5 still says `market closed`, stop and check the Journal tab. Wait a few
   minutes before trying again.
5. If the tiny order opens, close it immediately.
6. If the close succeeds and Trade tab is flat, manual strategy tickets are
   allowed.
7. If any open/close step behaves unexpectedly, stay flat and use mobile only as
   backup monitoring/close control.

Do not start with gold, crypto, or multi-leg strategy size before the tiny
EURUSD open-close test has succeeded.

## Manual Strategy Ticket Workflow

Generate the ticket:

```bash
.venv/bin/python scripts/create_execution_ticket.py \
  --bars data/processed/bars_15min.parquet \
  --config configs/portfolio_guarded.yaml \
  --symbol-specs configs/mt5_symbol_specs.yaml
```

Or re-size with live quotes copied from Market Watch:

```bash
.venv/bin/python scripts/manual_quote_ticket.py \
  --quote XAUUSD:BID:ASK \
  --quote USDCHF:BID:ASK \
  --quote USDCAD:BID:ASK
```

The generated markdown ticket gives the symbol, side, and MT5 lot volume for manual entry.

The live quote ticket only re-sizes existing strategy targets with copied MT5
quotes. It does not recompute live signals from current MT5 bar history.

Before entering a manual strategy ticket:

1. Confirm the tiny EURUSD open-close test succeeded.
2. Confirm the ticket timestamp and understand whether it is based on historical
   bars or refreshed live inputs.
3. Confirm the Trade tab is flat unless the ticket is intentionally modifying an
   existing net position.
4. Enter one symbol at a time and re-check symbol, side, and volume before each
   click.
5. After entry, compare the Trade tab against the ticket.

MT5 netting mode means there is one net position per symbol. A new order in the
opposite direction can reduce, close, or flip the existing position.

## MT5 Live Data Bridge

The live data bridge is one-way and non-trading:

```text
MT5 completed M15 bars -> CSV file -> Python importer -> fresh manual ticket
```

The MT5 exporter file is:

```text
mt5/ExportLiveBars.mq5
```

It exports completed M15 candles for the configured strategy symbols:

```text
XAUUSD, USDJPY, USDCHF, AUDUSD, USDCAD
```

It does not place orders.

Install/run outline:

1. In MT5, open MetaEditor.
2. Create a new Expert Advisor named `ExportLiveBars`.
3. Paste the contents of `mt5/ExportLiveBars.mq5`.
4. Compile it.
5. Attach it to any chart while the account is flat.
6. Confirm MT5 writes `syphonix_mt5_live_bars.csv` in its `MQL5/Files` folder.

After MT5 writes the CSV, merge it with historical bars:

```bash
.venv/bin/python scripts/build_live_bars_from_mt5.py \
  --mt5-csv /path/to/syphonix_mt5_live_bars.csv \
  --output data/live/bars_15min_live.parquet
```

Then create a fresh manual ticket from the merged live bar file:

```bash
.venv/bin/python scripts/create_execution_ticket.py \
  --bars data/live/bars_15min_live.parquet \
  --config configs/portfolio_guarded.yaml \
  --symbol-specs configs/mt5_symbol_specs.yaml
```

Use completed 15-minute candles. The first useful post-launch decision window is
around `22:16`, then `22:31`, `22:46`, and so on.

To translate a target ticket into netting-mode adjustment orders, pass the
current MT5 Trade tab positions:

```bash
.venv/bin/python scripts/create_adjustment_ticket.py \
  --bars data/live/bars_15min_fx_live.parquet \
  --config configs/portfolio_fx_live.yaml \
  --symbol-specs configs/mt5_symbol_specs.yaml \
  --execution-equity 1000000 \
  --position USDJPY:sell:21 \
  --position USDCHF:buy:15 \
  --position USDCAD:buy:12
```

If `ADJUSTMENT_PLAN` has no orders, hold. If it has orders, enter only those
adjustment orders, not the full target ticket.

Important limitation: MT5 M15 candles are treated as bid candles, and the bridge
approximates ask/mid fields using the current bid/ask spread. This is acceptable
for a first fresh-signal bridge, but each generated ticket still needs a manual
sanity check before entry.

## EA Bridge Decision

Do not deploy an Expert Advisor before the first successful tiny manual order.

A dry-run EA bridge can be useful later for writing proposed orders into MT5 and
checking that MT5 sees the same symbols, volumes, and account state. It should
start in logging-only mode and must not place orders until it has been tested
while the account is flat.

For launch, the safer choice is:

1. manual tiny EURUSD test;
2. manual ticket workflow if the platform behaves normally;
3. only then consider a dry-run EA bridge for monitoring or future automation.

## Safety Rules

- Do not use 30x leverage.
- Do not leave near-max leverage open for long periods.
- Do not let one symbol become almost all exposure for 30 minutes.
- Keep the Trade tab visible after placing orders.
- If platform/server behavior is unclear, stop and inspect the Journal tab.
