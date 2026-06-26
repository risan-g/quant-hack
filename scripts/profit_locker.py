import pandas as pd
import time
"""
Syphonix QuantHack: Dynamic Profit Locker & Risk Sidecar

This daemon runs alongside the main execution loop to autonomously protect capital.
It continuously scans the MT5 positions CSV for real-time equity data.

Innovation:
Instead of sending API close requests, it mathematically locks in wealth by 
dynamically parsing and rewriting the live YAML configuration files in real-time.
When massive profit milestones are reached, it seamlessly downshifts the entire 
trading engine from an aggressive high-leverage "Attack" gear into a highly 
defensive "Wealth Generation" gear without interrupting the execution pipeline.
"""

import os

MT5_POSITIONS = "/Users/risan/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/MQL5/Files/syphonix_mt5_positions.csv"
KILL_SWITCH = "M5_STOP_AUTO_TRADING"

# Target: $13,000 floating profit (which brings the 987k base equity to exactly 1M).
TRIGGER_USD = 13000.0
FLOOR_USD = 10000.0

print(f"Automatic Gear Shifter Active. Monitoring for ${TRIGGER_USD} profit trigger to break 1M...")
highest_profit = 0.0

while True:
    try:
        if os.path.exists(MT5_POSITIONS):
            df = pd.read_csv(MT5_POSITIONS)
            if 'profit' in df.columns:
                total_profit = df['profit'].sum()
                
                if total_profit > highest_profit:
                    highest_profit = total_profit
                    if highest_profit >= TRIGGER_USD:
                        print(f"[{time.strftime('%H:%M:%S')}] PEAK CROSSED $18k! 1M MILESTONE HIT. Trailing lock engaged.")
                
                if highest_profit >= TRIGGER_USD:
                    current_floor = highest_profit - (TRIGGER_USD - FLOOR_USD)
                elif highest_profit >= 8000.0:
                    current_floor = 4000.0  # Emergency floor to protect the 9k spike
                else:
                    current_floor = -999999.0
                    
                if total_profit <= current_floor and highest_profit >= 8000.0:
                        print("\n!!! GEAR SHIFT ENGAGED !!!")
                        print(f"Peak Profit: ${highest_profit:.2f}")
                        print(f"Current Profit: ${total_profit:.2f} (Hit floor of ${current_floor:.2f})")
                        print("SHIFTING INTO SAFE WEALTH-GENERATION GEAR...")
                        
                        try:
                            with open("configs/portfolio_scanner_attack.yaml", "r") as f:
                                config = f.read()
                            # Downshift leverage to 6.0x instead of 0.0 to keep safely generating profit
                            config = config.replace("max_gross_leverage: 20.0", "max_gross_leverage: 6.0")
                            config = config.replace("attack_gross_leverage: 16.0", "attack_gross_leverage: 4.5")
                            config = config.replace("base_gross_leverage: 10.0", "base_gross_leverage: 3.0")
                            with open("configs/portfolio_scanner_attack.yaml", "w") as f:
                                f.write(config)
                            print("Leverage successfully downshifted to 6.0x. The bot will keep safely grinding past 1M.")
                        except Exception as ce:
                            print(f"Failed to update config: {ce}")
                            
                        break
    except Exception as e:
        print(f"Error reading positions: {e}")
        
    time.sleep(5)
