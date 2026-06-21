from pathlib import Path

import pandas as pd

from quantbot.live.mt5_bridge import merge_historical_and_live_bars, read_mt5_live_bars_csv


def test_read_mt5_live_bars_csv_builds_canonical_schema(tmp_path: Path) -> None:
    csv_path = tmp_path / "mt5_live.csv"
    csv_path.write_text(
        "\n".join(
            [
                "exported_at,symbol,time,bid_open,bid_high,bid_low,bid_close,current_bid,current_ask,tick_volume",
                "2026-06-21 22:16:00,XAUUSD,2026-06-21 22:15:00,3370,3375,3368,3372,3372,3372.5,100",
            ]
        ),
        encoding="utf-8",
    )

    bars = read_mt5_live_bars_csv(csv_path, symbols={"XAUUSD"})

    assert list(bars["symbol"]) == ["XAUUSD"]
    assert bars.loc[0, "time"] == pd.Timestamp("2026-06-21 22:15:00", tz="UTC")
    assert bars.loc[0, "ask_close"] == 3372.5
    assert bars.loc[0, "mid_close"] == 3372.25
    assert bars.loc[0, "spread_mean"] == 0.5
    assert bars.loc[0, "ticks"] == 100


def test_merge_historical_and_live_bars_prefers_live_duplicate() -> None:
    historical = pd.DataFrame(
        [
            {
                "symbol": "XAUUSD",
                "source_date": "2026-06-21",
                "time": pd.Timestamp("2026-06-21 22:15:00", tz="UTC"),
                "bid_open": 1.0,
                "bid_high": 1.0,
                "bid_low": 1.0,
                "bid_close": 1.0,
                "ask_open": 1.1,
                "ask_high": 1.1,
                "ask_low": 1.1,
                "ask_close": 1.1,
                "mid_open": 1.05,
                "mid_high": 1.05,
                "mid_low": 1.05,
                "mid_close": 1.05,
                "spread_mean": 0.1,
                "spread_max": 0.1,
                "ticks": 1,
            }
        ]
    )
    live = historical.copy()
    live.loc[0, "mid_close"] = 2.0

    merged = merge_historical_and_live_bars(historical, live)

    assert len(merged) == 1
    assert merged.loc[0, "mid_close"] == 2.0
