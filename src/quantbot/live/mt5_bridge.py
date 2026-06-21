"""Import MetaTrader 5 exported live bars into the research bar schema."""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REQUIRED_MT5_COLUMNS = {
    "symbol",
    "time",
    "bid_open",
    "bid_high",
    "bid_low",
    "bid_close",
    "current_bid",
    "current_ask",
    "tick_volume",
}

BAR_COLUMNS = [
    "symbol",
    "source_date",
    "time",
    "bid_open",
    "bid_high",
    "bid_low",
    "bid_close",
    "ask_open",
    "ask_high",
    "ask_low",
    "ask_close",
    "mid_open",
    "mid_high",
    "mid_low",
    "mid_close",
    "spread_mean",
    "spread_max",
    "ticks",
]


def _parse_time_column(values: pd.Series, assume_timezone: str) -> pd.Series:
    parsed = pd.to_datetime(values)
    if parsed.dt.tz is None:
        parsed = parsed.dt.tz_localize(ZoneInfo(assume_timezone))
    return parsed.dt.tz_convert("UTC")


def read_mt5_live_bars_csv(
    path: Path,
    assume_timezone: str = "UTC",
    symbols: set[str] | None = None,
) -> pd.DataFrame:
    """Read an MT5-exported CSV and return canonical 15-minute bars.

    MT5 normally exports bid OHLC candles. We approximate ask OHLC by adding the
    current bid/ask spread, then use those fields to calculate mid OHLC.
    """
    raw = pd.read_csv(path)
    missing = REQUIRED_MT5_COLUMNS - set(raw.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"MT5 CSV missing required columns: {missing_text}")

    work = raw.copy()
    work["symbol"] = work["symbol"].astype(str).str.upper().str.strip()
    if symbols is not None:
        work = work[work["symbol"].isin(symbols)].copy()
    if work.empty:
        raise ValueError("No MT5 rows left after symbol filtering")

    work["time"] = _parse_time_column(work["time"], assume_timezone)
    numeric_columns = [
        "bid_open",
        "bid_high",
        "bid_low",
        "bid_close",
        "current_bid",
        "current_ask",
        "tick_volume",
    ]
    for column in numeric_columns:
        work[column] = pd.to_numeric(work[column], errors="raise")

    invalid_prices = (
        (work["bid_open"] <= 0)
        | (work["bid_high"] <= 0)
        | (work["bid_low"] <= 0)
        | (work["bid_close"] <= 0)
        | (work["current_bid"] <= 0)
        | (work["current_ask"] <= 0)
        | (work["current_ask"] < work["current_bid"])
    )
    if invalid_prices.any():
        bad = work.loc[invalid_prices, ["symbol", "time"]].head().to_dict("records")
        raise ValueError(f"Invalid MT5 price rows: {bad}")

    spread = work["current_ask"] - work["current_bid"]
    work["ask_open"] = work["bid_open"] + spread
    work["ask_high"] = work["bid_high"] + spread
    work["ask_low"] = work["bid_low"] + spread
    work["ask_close"] = work["bid_close"] + spread
    work["mid_open"] = (work["bid_open"] + work["ask_open"]) / 2.0
    work["mid_high"] = (work["bid_high"] + work["ask_high"]) / 2.0
    work["mid_low"] = (work["bid_low"] + work["ask_low"]) / 2.0
    work["mid_close"] = (work["bid_close"] + work["ask_close"]) / 2.0
    work["spread_mean"] = spread
    work["spread_max"] = spread
    work["ticks"] = work["tick_volume"].astype("int64")
    work["source_date"] = work["time"].dt.strftime("%Y-%m-%d")

    bars = work[BAR_COLUMNS].sort_values(["symbol", "time"]).reset_index(drop=True)
    duplicated = bars.duplicated(["symbol", "time"], keep=False)
    if duplicated.any():
        bars = bars.drop_duplicates(["symbol", "time"], keep="last").reset_index(drop=True)
    return bars


def merge_historical_and_live_bars(historical: pd.DataFrame, live: pd.DataFrame) -> pd.DataFrame:
    """Merge historical and live bars, preferring live rows on duplicate timestamps."""
    combined = pd.concat([historical[BAR_COLUMNS], live[BAR_COLUMNS]], ignore_index=True)
    combined = combined.sort_values(["symbol", "time"])
    combined = combined.drop_duplicates(["symbol", "time"], keep="last")
    return combined.reset_index(drop=True)
