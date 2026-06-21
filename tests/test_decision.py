from quantbot.live.decision import DecisionLeg, DecisionReport, rescale_decision_report, side_from_signal


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
