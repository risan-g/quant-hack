from quantbot.research.selection import (
    CandidateScore,
    select_diversified_candidates,
    weights_from_scores,
)


def test_select_diversified_candidates_limits_symbol_count() -> None:
    scores = [
        CandidateScore("XAUUSD", "a", 10, 1, 0, 1, 100),
        CandidateScore("XAUUSD", "b", 9, 1, 0, 1, 100),
        CandidateScore("USDJPY", "c", 8, 1, 0, 1, 100),
    ]
    selected = select_diversified_candidates(scores, top_n=2, max_per_symbol=1)
    assert [(item.symbol, item.strategy) for item in selected] == [
        ("XAUUSD", "a"),
        ("USDJPY", "c"),
    ]


def test_weights_from_scores_normalizes_positive_utility() -> None:
    scores = [
        CandidateScore("XAUUSD", "a", 3, 1, 0, 1, 100),
        CandidateScore("USDJPY", "b", 1, 1, 0, 1, 100),
    ]
    weights = weights_from_scores(scores)
    assert weights[0]["weight"] == 0.75
    assert weights[1]["weight"] == 0.25
