# MT5 Runbook

This runbook is for operating the competition account through MetaTrader 5.

## Current Status

- MT5 login works.
- Account balance/equity shows 1,000,000 USD.
- All 15 competition symbols are visible.
- Trading is currently disabled server-side.

Do not repeatedly retry orders while the server says trading is disabled.

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

## Safety Rules

- Do not use 30x leverage.
- Do not leave near-max leverage open for long periods.
- Do not let one symbol become almost all exposure for 30 minutes.
- Keep the Trade tab visible after placing orders.
- If platform/server behavior is unclear, stop and inspect the Journal tab.
