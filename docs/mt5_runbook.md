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
MT5 completed M15 bars + current positions -> CSV files -> Python importer -> fresh manual ticket
```

The MT5 exporter file is:

```text
mt5/ExportLiveBars.mq5
```

It exports completed M15 candles for the configured strategy symbols:

```text
XAUUSD, USDJPY, USDCHF, AUDUSD, USDCAD
```

It also exports current MT5 net positions and account state to:

```text
syphonix_mt5_positions.csv
```

It does not place orders.

Install/run outline:

1. In MT5, open MetaEditor.
2. Create a new Expert Advisor named `ExportLiveBars`.
3. Paste the contents of `mt5/ExportLiveBars.mq5`.
4. Compile it.
5. Attach it to any chart while the account is flat.
6. Confirm MT5 writes these files in its `MQL5/Files` folder:
   - `syphonix_mt5_live_bars.csv`
   - `syphonix_mt5_positions.csv`

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

After the position exporter is installed, the preferred single command is:

```bash
.venv/bin/python scripts/live_checkpoint.py \
  --mt5-bars-csv /path/to/syphonix_mt5_live_bars.csv \
  --mt5-positions-csv /path/to/syphonix_mt5_positions.csv \
  --config configs/portfolio_guarded.yaml
```

Read the final `ACTION:` section. It prints either `HOLD` or the exact MT5
orders to enter manually.

## Dry-Run Proposed Orders

After the position exporter works, the next automation layer is dry-run only:

```text
Python writes proposed orders -> MT5 reads them -> MT5 logs WOULD BUY/SELL
```

The MT5 dry-run reader is:

```text
mt5/DryRunProposedOrders.mq5
```

It does not place orders.

Install/run outline:

1. In MetaEditor, create a new Expert Advisor named `DryRunProposedOrders`.
2. Paste the contents of `mt5/DryRunProposedOrders.mq5`.
3. Compile it.
4. Attach it to one chart.
5. Keep Algo Trading enabled, but remember this EA has no trade placement calls.

Run the checkpoint with proposed-order output:

```bash
.venv/bin/python scripts/live_checkpoint.py \
  --mt5-bars-csv /path/to/syphonix_mt5_live_bars.csv \
  --mt5-positions-csv /path/to/syphonix_mt5_positions.csv \
  --proposed-orders-csv /path/to/syphonix_proposed_orders.csv \
  --config configs/portfolio_guarded.yaml
```

Then check the MT5 Experts tab. It should log `WOULD BUY/SELL ...` lines that
match the Python `ACTION:` section.

Important limitation: MT5 M15 candles are treated as bid candles, and the bridge
approximates ask/mid fields using the current bid/ask spread. This is acceptable
for a first fresh-signal bridge, but each generated ticket still needs a manual
sanity check before entry.

## Tiny-Capped Live EA

The first live executor is intentionally capped and gated:

```text
mt5/AutoExecuteProposedOrders.mq5
```

It ignores the proposed-order file that already exists when the EA is attached.
Only a newly generated file can trigger actions.

Live execution requires all gates to be open:

1. EA input `DryRunMode=false`.
2. EA input `ArmedForLiveTrading=true`.
3. The CSV row has `dry_run=false`, generated with `--proposed-live`.
4. The signal timestamp is not stale.
5. The symbol is in `AllowedSymbols`.
6. Each order is capped by `MaxOrderLots`.

Initial live setting should keep `MaxOrderLots=0.10` until the mechanics are
confirmed in MT5 History and Journal.

Generate a live-proposed file:

```bash
.venv/bin/python scripts/live_checkpoint.py \
  --mt5-bars-csv /path/to/syphonix_mt5_live_bars.csv \
  --mt5-positions-csv /path/to/syphonix_mt5_positions.csv \
  --proposed-orders-csv /path/to/syphonix_proposed_orders.csv \
  --proposed-live \
  --config configs/portfolio_guarded.yaml
```

## Supervised Auto Checkpoint Loop

The supervised loop can run every few seconds and only writes a proposed-order
file when a new completed candle produces safe-sized actions:

```bash
.venv/bin/python scripts/auto_checkpoint_loop.py \
  --mt5-bars-csv /path/to/syphonix_mt5_live_bars.csv \
  --mt5-positions-csv /path/to/syphonix_mt5_positions.csv \
  --proposed-orders-csv /path/to/syphonix_proposed_orders.csv \
  --mode dry-run
```

MT5 exports naive timestamps from the terminal/server clock; for launch day this
workflow treats those timestamps as `Europe/London`.

Switch to `--mode live` only after dry-run logs match expectations. The loop
does not write live files when:

- `STOP_AUTO_TRADING` exists in the repo root;
- the MT5 export is stale;
- the candle was already handled;
- all actions are tiny churn;
- any order exceeds `--max-auto-order-lots`, unless `--split-large-orders` is enabled.

For less manual work, use `--split-large-orders`. This keeps each EA order
capped while allowing the loop to complete a larger target as several chunks.
Keep `--max-total-action-lots` conservative so one bad checkpoint cannot produce
an unlimited burst.

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
