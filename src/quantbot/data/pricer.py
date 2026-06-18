"""Utilities for the xSyphon pricer-output Parquet dataset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

FILENAME_RE = re.compile(r"^(?P<symbol>[A-Z0-9]+)_(?P<year>\d{4})_(?P<month>\d{2})_(?P<day>\d{2})\.parquet$")


@dataclass(frozen=True)
class PricerFile:
    path: Path
    symbol: str
    date: str
    rows: int
    size_bytes: int


def parse_pricer_filename(path: Path) -> tuple[str, str] | None:
    match = FILENAME_RE.match(path.name)
    if not match:
        return None
    date = f"{match.group('year')}-{match.group('month')}-{match.group('day')}"
    return match.group("symbol"), date


def discover_pricer_files(data_dir: Path) -> list[PricerFile]:
    files: list[PricerFile] = []
    for path in sorted(data_dir.glob("*.parquet")):
        parsed = parse_pricer_filename(path)
        if parsed is None:
            continue
        symbol, date = parsed
        metadata = pq.ParquetFile(path).metadata
        files.append(
            PricerFile(
                path=path,
                symbol=symbol,
                date=date,
                rows=metadata.num_rows,
                size_bytes=path.stat().st_size,
            )
        )
    return files


def read_quote_file(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=columns)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
    if "received" in df.columns:
        df["received"] = pd.to_datetime(df["received"], utc=True)
    return df


def read_mid_quotes(path: Path) -> pd.DataFrame:
    df = read_quote_file(path, columns=["time", "sym", "bid", "ask"])
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    df["spread"] = df["ask"] - df["bid"]
    return df


def resample_quotes(df: pd.DataFrame, frequency: str) -> pd.DataFrame:
    if df.empty:
        return df
    work = df.sort_values("time").set_index("time")
    bars = work.resample(frequency).agg(
        bid_open=("bid", "first"),
        bid_high=("bid", "max"),
        bid_low=("bid", "min"),
        bid_close=("bid", "last"),
        ask_open=("ask", "first"),
        ask_high=("ask", "max"),
        ask_low=("ask", "min"),
        ask_close=("ask", "last"),
        mid_open=("mid", "first"),
        mid_high=("mid", "max"),
        mid_low=("mid", "min"),
        mid_close=("mid", "last"),
        spread_mean=("spread", "mean"),
        spread_max=("spread", "max"),
        ticks=("mid", "count"),
    )
    return bars.dropna(subset=["mid_open", "mid_close"]).reset_index()
