# QuantHack

QuantHack is a Python and MQL5 algorithmic trading system built for a two-week quantitative trading competition, where I reached the finals and placed 85th of 440 participants.

The system generated trading decisions in Python and executed them through MetaTrader 5 against live market quotes in a simulated $1,000,000 account. Python and MQL5 communicated through a bidirectional CSV bridge, with validation, stale-state rejection, duplicate-order suppression and acknowledgement logic protecting the asynchronous execution boundary.

## Engineering Highlights

- Bidirectional CSV bridge between Python and MQL5 for market/account state and proposed orders.
- MT5 snapshots older than 120 seconds rejected before new decisions are acted upon.
- Pydantic validation for state/order payloads at process boundaries.
- Order-file fingerprinting in MQL5 suppresses duplicate execution.
- New orders are held while a prior write is pending until MT5 acknowledges the expected position change.
- Malformed or partially-written files are retried without terminating the main trading loop.
- Configuration is loaded from YAML.

## Architecture

```text
Market / MT5 state
      ↓
MQL5 exporter
      ↓
mt5_bars.csv + mt5_positions.csv
      ↓
Python strategy / risk / decision engine
      ↓
syphonix_proposed_orders.csv
      ↓
MQL5 execution bridge
      ↓
MetaTrader 5 simulated account
```

Polling is asynchronous. The acknowledgement and fingerprinting mechanisms exist because the two processes do not execute in lockstep.

## Competition Context

- Solo project
- Two-week competition
- 440 participants
- Finalist
- Final placement: 85th
- Simulated starting balance: $1,000,000
- Execution used live market quotes with simulated funds.

## Tech Stack

- Python
- MQL5
- Pandas
- Pydantic
- PyYAML
- Pytest

## Running / Testing

### A. Python Tests and Local Inspection

Local testing uses mocked dataframes and does not require MetaTrader 5.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest tests/
```

### B. Full MT5 Integration

Running the full execution bridge requires MetaTrader 5 and the MQL5 bridge to be active.

```bash
./run_autobot.sh live
```

(Optional) Run the dynamic profit locker in a separate terminal:
```bash
.venv/bin/python scripts/profit_locker.py
```
