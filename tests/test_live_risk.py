from quantbot.execution.adjustments import CurrentPosition
from quantbot.execution.models import OrderIntent, OrderSide
from quantbot.execution.sizing import SymbolSpec
from quantbot.risk.live import (
    assess_live_positions,
    live_risk_block_reasons,
    projected_positions_after_orders,
)


def test_assess_live_positions_reports_gross_and_warnings() -> None:
    specs = {
        "USDCHF": SymbolSpec(
            symbol="USDCHF",
            contract_size=100_000,
            contract_asset="USD",
            quote_currency="CHF",
            min_volume=0.01,
            max_volume=100,
            volume_step=0.01,
        )
    }
    positions = [CurrentPosition(symbol="USDCHF", side=OrderSide.BUY, volume_lots=10)]

    report = assess_live_positions(positions, specs, {"USDCHF": 0.8}, equity_usd=1_000_000)

    assert report.gross_notional_usd == 1_000_000
    assert report.gross_leverage == 1.0
    assert report.net_directional_leverage == 1.0
    assert report.net_directional_share == 1.0
    assert report.warnings == [
        "WARN largest symbol USDCHF is 100.0% of gross exposure",
        "WARN net directional leverage 1.00x",
    ]


def test_projected_positions_after_orders_netting_mode() -> None:
    current = [CurrentPosition(symbol="USDCHF", side=OrderSide.BUY, volume_lots=1.0)]
    orders = [
        OrderIntent(
            symbol="USDCHF",
            side=OrderSide.SELL,
            notional_usd=60_000,
            volume_lots=0.6,
            target_leverage=0.0,
            reason="reduce",
        ),
        OrderIntent(
            symbol="XAUUSD",
            side=OrderSide.SELL,
            notional_usd=820_000,
            volume_lots=2.0,
            target_leverage=0.0,
            reason="open",
        ),
    ]

    projected = projected_positions_after_orders(current, orders)

    assert [(row.symbol, row.side, row.volume_lots) for row in projected] == [
        ("USDCHF", OrderSide.BUY, 0.4),
        ("XAUUSD", OrderSide.SELL, 2.0),
    ]


def test_live_risk_block_reasons_catches_concentration() -> None:
    specs = {
        "USDCHF": SymbolSpec(
            symbol="USDCHF",
            contract_size=100_000,
            contract_asset="USD",
            quote_currency="CHF",
            min_volume=0.01,
            max_volume=100,
            volume_step=0.01,
        )
    }
    positions = [CurrentPosition(symbol="USDCHF", side=OrderSide.BUY, volume_lots=100)]

    report = assess_live_positions(positions, specs, {"USDCHF": 0.8}, equity_usd=1_000_000)
    reasons = live_risk_block_reasons(
        report,
        max_gross_leverage=12.0,
        max_largest_symbol_share=0.85,
        max_net_directional_share=0.90,
        max_margin_usage=0.50,
        max_platform_leverage=30.0,
    )

    assert reasons == [
        "projected largest symbol share 100.0% exceeds 85.0%",
        "projected net directional share 100.0% exceeds 90.0%",
    ]
