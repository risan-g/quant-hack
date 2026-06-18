from quantbot.competition import CompetitionScore, max_drawdown, sharpe_from_returns


def test_competition_score_weights() -> None:
    score = CompetitionScore(
        return_rank=100,
        drawdown_rank=50,
        sharpe_rank=25,
        risk_discipline=100,
    )
    assert score.final_score == 85.0


def test_max_drawdown() -> None:
    assert round(max_drawdown([100, 120, 90, 110]), 6) == 0.25


def test_zero_variance_sharpe_is_zero() -> None:
    assert sharpe_from_returns([0.01, 0.01, 0.01]) == 0.0
