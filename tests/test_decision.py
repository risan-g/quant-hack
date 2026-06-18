from quantbot.live.decision import side_from_signal


def test_side_from_signal() -> None:
    assert side_from_signal(1.0) == "long"
    assert side_from_signal(-1.0) == "short"
    assert side_from_signal(0.0) == "flat"
