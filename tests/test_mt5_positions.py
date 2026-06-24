from pathlib import Path

from quantbot.execution.models import OrderSide
from quantbot.live.mt5_positions import read_mt5_positions_csv


def test_read_mt5_positions_csv_reads_open_positions(tmp_path: Path) -> None:
    path = tmp_path / "positions.csv"
    path.write_text(
        "\n".join(
            [
                "exported_at,balance,equity,margin,free_margin,margin_level,symbol,side,volume,price_open,price_current,profit",
                "2026.06.22 12:00:00,997212.77,995854.23,118679.88,877174.35,839.11,XAUUSD,buy,4.50,4209.76,4206.23,-1592.20",
                "2026.06.22 12:00:00,997212.77,995854.23,118679.88,877174.35,839.11,USDCAD,sell,8.33,1.41726,1.41684,250.84",
            ]
        ),
        encoding="utf-8",
    )

    snapshot = read_mt5_positions_csv(path)

    assert snapshot.equity == 995854.23
    assert len(snapshot.positions) == 2
    assert snapshot.positions[0].symbol == "XAUUSD"
    assert snapshot.positions[0].side == OrderSide.BUY
    assert snapshot.positions[0].volume_lots == 4.5


def test_read_mt5_positions_csv_handles_flat_account(tmp_path: Path) -> None:
    path = tmp_path / "positions.csv"
    path.write_text(
        "\n".join(
            [
                "exported_at,balance,equity,margin,free_margin,margin_level,symbol,side,volume,price_open,price_current,profit",
                "2026.06.22 12:00:00,997212.77,997212.77,0,997212.77,0,,flat,0,0,0,0",
            ]
        ),
        encoding="utf-8",
    )

    snapshot = read_mt5_positions_csv(path)

    assert snapshot.equity == 997212.77
    assert snapshot.positions == []
