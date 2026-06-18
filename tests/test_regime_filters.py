import pandas as pd

from quantbot.research.signals import regime_mask


def test_regime_mask_requires_expanding_vol() -> None:
    frame = pd.DataFrame(
        {
            "vol_ratio_16_64": [0.8, 1.2],
            "trend_strength_32": [5.0, 5.0],
            "spread_z_64": [0.0, 0.0],
        }
    )
    mask = regime_mask(frame, {"require_expanding_vol": True, "min_vol_ratio": 1.0})
    assert mask.tolist() == [False, True]


def test_regime_mask_blocks_high_spread() -> None:
    frame = pd.DataFrame(
        {
            "vol_ratio_16_64": [1.0, 1.0],
            "trend_strength_32": [2.0, 2.0],
            "spread_z_64": [1.0, 4.0],
        }
    )
    mask = regime_mask(frame, {"max_spread_z": 3.0})
    assert mask.tolist() == [True, False]
