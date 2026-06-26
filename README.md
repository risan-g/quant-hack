# Syphonix QuantHack: Autonomous AI Trading Engine

This repository contains the architecture, execution engine, and dynamic risk management systems developed for the QuantHack 2026 AI Trading Competition. 

## System Architecture

The core philosophy of this project is to build an unshakeable, autonomous bridge between a Python-based quantitative AI and the MetaTrader 5 (MT5) execution environment.

```text
market data (MT5)
  -> CSV Bridge
  -> feature pipeline (Python)
  -> strategy ensemble (Regime Filters + Momentum/Reversion)
  -> portfolio allocator (YAML Configs)
  -> risk governor (Dynamic Margin & Equity Limits)
  -> execution adapter (CSV Output)
  -> MT5 Expert Advisor (Order Execution)
```

### 1. The Autonomous Execution Loop (`auto_m5_checkpoint_loop.py`)
To solve the problem of robust data transfer between Python and MT5 without relying on unverified APIs or webhooks, we built an asynchronous CSV data bridge. 
- The MT5 EA exports live bars and positions to CSV every 5 minutes.
- The Python AI engine continuously watches these files, calculates mathematical momentum and breakout signals, and writes optimized, chunked orders back to a `proposed_orders` CSV.
- The system includes a deadlock-resolution mechanism that clears stalled files gracefully during timeouts or network latency, ensuring the bot never hangs.

### 2. The Dynamic Profit Locker (`profit_locker.py`)
To secure capital automatically during extreme market volatility, a standalone AI-assisted gear-shifting script runs alongside the main execution loop.
- It constantly monitors the MT5 positions CSV.
- When massive equity milestones (e.g., $1.01M) are breached, the Python script dynamically rewrites the live YAML configuration file in real-time.
- It downshifts max leverage from an aggressive 27.5x "YOLO" gear to a safe 6.0x "Wealth-Generation" gear seamlessly, without interrupting the main trading loop.

### 3. Config-Driven Regime Filters (`portfolio_scanner_attack.yaml`)
Risk is handled strictly through deterministic mathematical bounds, not guessing.
- Strategies are defined in modular YAML files.
- The engine uses `regime: max_spread_z` and volume thresholds to actively filter out low-liquidity "chop" sessions (e.g., the Asian overnight session) and wait for the explosive volume of the London/NY overlap.
- Drawdowns are mathematically bounded with hard circuit breakers (e.g., `-0.035` 16-period loss cuts).

## Deployment Instructions

1. Install dependencies:
   ```bash
   python3 -m venv .venv
   .venv/bin/python -m pip install -e '.[dev]'
   ```

2. Run the fully autonomous execution bridge:
   ```bash
   ./run_autobot.sh live
   ```

3. (Optional) Run the dynamic profit locker in a separate terminal to protect gains:
   ```bash
   .venv/bin/python scripts/profit_locker.py
   ```

---
*Developed for the $10,000 Tech Award Submission.*
