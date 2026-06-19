"""MT5 lot sizing helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    contract_size: float
    contract_asset: str
    quote_currency: str
    min_volume: float
    max_volume: float
    volume_step: float

    @property
    def base_currency(self) -> str:
        return self.contract_asset


def load_symbol_specs(path: Path) -> dict[str, SymbolSpec]:
    with path.open("r", encoding="utf-8") as handle:
        payload: dict[str, Any] = yaml.safe_load(handle)
    specs = {}
    for symbol, values in payload["symbols"].items():
        specs[symbol] = SymbolSpec(symbol=symbol, **values)
    return specs


def usd_notional_per_lot(spec: SymbolSpec, mid_price: float) -> float:
    """Estimate USD notional represented by one MT5 lot.

    This supports USD-quoted symbols such as XAUUSD/EURUSD and USD-base FX
    symbols such as USDJPY/USDCHF/USDCAD. Crosses without USD need an explicit
    conversion layer and intentionally fail here.
    """
    if spec.base_currency == "USD":
        return spec.contract_size
    if spec.quote_currency == "USD":
        return spec.contract_size * mid_price
    raise ValueError(f"USD conversion unavailable for {spec.symbol}")


def round_volume_down(volume: float, step: float) -> float:
    return math.floor((volume + 1e-12) / step) * step


def lots_for_notional_usd(spec: SymbolSpec, notional_usd: float, mid_price: float) -> float:
    raw_volume = notional_usd / usd_notional_per_lot(spec, mid_price)
    rounded = round_volume_down(raw_volume, spec.volume_step)
    if rounded < spec.min_volume:
        return 0.0
    return min(rounded, spec.max_volume)
