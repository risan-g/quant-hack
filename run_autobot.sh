#!/bin/bash
MT5_DIR="/Users/risan/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files"

# Use dry-run by default, pass "live" as an argument to run in live mode
MODE=${1:-dry-run}

echo "Starting autobot loop in $MODE mode..."
.venv/bin/python scripts/auto_m5_checkpoint_loop.py \
  --config configs/portfolio_scanner_attack.yaml \
  --mt5-bars-csv "$MT5_DIR/syphonix_mt5_live_bars.csv" \
  --mt5-positions-csv "$MT5_DIR/syphonix_mt5_positions.csv" \
  --proposed-orders-csv "$MT5_DIR/syphonix_proposed_orders.csv" \
  --max-total-action-lots 250.0 \
  --max-projected-gross-leverage 20.0 \
  --max-projected-margin-usage 0.95 \
  --split-large-orders \
  --profit-lock-trigger-usd 10000.0 \
  --profit-lock-floor-usd 8000.0 \
  --profit-lock-giveback-usd 2000.0 \
  --disable-entry-confirmation \
  --equity-ceiling 1500000.0 \
  --equity-floor 850000.0 \
  --assume-timezone UTC \
  --mode "$MODE"
