import pandas as pd

from quantbot.risk.governor import AdaptiveRiskConfig, AdaptiveRiskGovernor


def test_governor_attacks_near_highs() -> None:
    returns = pd.Series([0.001, 0.001, 0.001])
    config = AdaptiveRiskConfig(base_gross_leverage=5, attack_gross_leverage=7)
    result = AdaptiveRiskGovernor(config).run(returns)
    assert result.gross_leverage.iloc[0] == 7


def test_governor_flattens_after_hard_drawdown() -> None:
    returns = pd.Series([-0.2, 0.1])
    config = AdaptiveRiskConfig(
        base_gross_leverage=1,
        attack_gross_leverage=1,
        soft_drawdown=0.05,
        hard_drawdown=0.10,
    )
    result = AdaptiveRiskGovernor(config).run(returns)
    assert result.gross_leverage.iloc[1] == 0


def test_current_state_reports_next_leverage() -> None:
    returns = pd.Series([0.001, 0.001])
    config = AdaptiveRiskConfig(base_gross_leverage=5, attack_gross_leverage=7)
    state = AdaptiveRiskGovernor(config).current_state(returns)
    assert state.equity > 1_000_000
    assert state.gross_leverage == 7
