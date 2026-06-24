"""Read MetaTrader 5 exported account and net position snapshots."""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import BaseModel, Field

from quantbot.execution.adjustments import CurrentPosition
from quantbot.execution.models import OrderSide

REQUIRED_POSITION_COLUMNS = {
    "exported_at",
    "balance",
    "equity",
    "margin",
    "free_margin",
    "margin_level",
    "symbol",
    "side",
    "volume",
    "price_open",
    "price_current",
    "profit",
}


class MT5PositionSnapshot(BaseModel):
    exported_at: str
    balance: float
    equity: float = Field(gt=0)
    margin: float
    free_margin: float
    margin_level: float
    positions: list[CurrentPosition]


def read_mt5_positions_csv(path: Path, assume_timezone: str = "UTC") -> MT5PositionSnapshot:
    raw = pd.read_csv(path)
    missing = REQUIRED_POSITION_COLUMNS - set(raw.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"MT5 positions CSV missing required columns: {missing_text}")
    if raw.empty:
        raise ValueError("MT5 positions CSV has no account row")

    first = raw.iloc[0]
    exported_at = pd.to_datetime(first["exported_at"])
    if exported_at.tzinfo is None:
        exported_at = exported_at.tz_localize(ZoneInfo(assume_timezone))
    exported_at = exported_at.tz_convert("UTC")

    positions: list[CurrentPosition] = []
    for _, row in raw.iterrows():
        symbol = str(row["symbol"]).upper().strip()
        side_raw = str(row["side"]).lower().strip()
        volume = float(row["volume"])
        if not symbol or side_raw == "flat" or volume <= 0:
            continue
        positions.append(
            CurrentPosition(
                symbol=symbol,
                side=OrderSide(side_raw),
                volume_lots=volume,
                price_open=float(row["price_open"]),
                price_current=float(row["price_current"]),
                profit=float(row["profit"]),
            )
        )

    return MT5PositionSnapshot(
        exported_at=exported_at.isoformat(),
        balance=float(first["balance"]),
        equity=float(first["equity"]),
        margin=float(first["margin"]),
        free_margin=float(first["free_margin"]),
        margin_level=float(first["margin_level"]),
        positions=positions,
    )
