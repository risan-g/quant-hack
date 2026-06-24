import pandas as pd

from quantbot.live.decision import (
    DecisionLeg,
    DecisionReport,
    high_conviction_mask,
    m15_trend_bias,
    rescale_decision_report,
    side_from_signal,
)


def test_side_from_signal() -> None:
    assert side_from_signal(1.0) == "long"
    assert side_from_signal(-1.0) == "short"
    assert side_from_signal(0.0) == "flat"


def test_rescale_decision_report_uses_execution_equity() -> None:
    report = DecisionReport(
        timestamp="2026-06-21T22:30:00+00:00",
        config_name="test.yaml",
        equity_usd=1_110_000,
        peak_equity_usd=1_110_000,
        drawdown=0,
        gross_leverage=4,
        cooldown_bars=0,
        active_legs=1,
        net_directional_leverage=1.5,
        gross_target_notional_usd=1_665_000,
        legs=[
            DecisionLeg(
                symbol="USDCHF",
                strategy="momentum_32",
                side="long",
                raw_signal=1,
                allowed_by_regime=True,
                weight=0.25,
                mid_price=0.8,
                spread_fraction=0.0001,
                spread_z=0.0,
                target_notional_usd=1_665_000,
                target_leverage=1.5,
            )
        ],
    )

    rescaled = rescale_decision_report(report, 1_000_000)

    assert rescaled.equity_usd == 1_000_000
    assert rescaled.legs[0].target_notional_usd == 1_500_000
    assert rescaled.gross_target_notional_usd == 1_500_000


def test_high_conviction_mask_blocks_weak_mean_reversion() -> None:
    group = pd.DataFrame({"mean_reversion_z_32": [1.10, -1.40, 1.70]})

    mask = high_conviction_mask(
        group,
        "mean_reversion_32",
        {"min_abs_reversion_z": 1.55},
    )

    assert mask.tolist() == [False, False, True]


def test_high_conviction_mask_blocks_weak_momentum() -> None:
    group = pd.DataFrame({"move_strength_32": [0.8, 2.1, 2.7]})

    mask = high_conviction_mask(
        group,
        "momentum_32",
        {"min_abs_move_strength": 2.25},
    )

    assert mask.tolist() == [False, False, True]


def test_m15_trend_bias_maps_back_to_m5_rows() -> None:
    times = pd.date_range("2026-06-24T00:00:00Z", periods=160, freq="5min")
    group = pd.DataFrame(
        {
            "time": times,
            "mid_close": [1.0 + index * 0.001 for index in range(len(times))],
        }
    )

    bias = m15_trend_bias(group, fast_span=4, slow_span=12)

    assert bias.index.equals(group.index)
    assert bias.iloc[-1] == 1.0


def test_high_conviction_mask_requires_m15_alignment() -> None:
    times = pd.date_range("2026-06-24T00:00:00Z", periods=160, freq="5min")
    group = pd.DataFrame(
        {
            "time": times,
            "mid_close": [1.0 + index * 0.001 for index in range(len(times))],
            "mean_reversion_32": [-1.0] * 160,
            "mean_reversion_z_32": [2.0] * 160,
        }
    )

    mask = high_conviction_mask(
        group,
        "mean_reversion_32",
        {
            "min_abs_reversion_z": 1.8,
            "require_m15_trend_align": True,
            "m15_ema_fast": 4,
            "m15_ema_slow": 12,
        },
    )

    assert not mask.iloc[-1]
