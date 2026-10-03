import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "python"))

from sentinel_statarb.strategy import DynamicDebouncer, KalmanHedge, OCOBracket, PairStrategy


def test_dynamic_debouncer_requires_more_confirmation_in_high_vol():
    debouncer = DynamicDebouncer(base=2, max_confirmations=8, reference_vol=0.001)
    assert debouncer.required(0.001) == 3
    assert debouncer.required(0.005) >= 5


def test_oco_is_one_shot_and_uses_five_bps():
    bracket = OCOBracket(1, 100.0, reference_notional=100.0, stop_bps=5.0)
    assert bracket.active
    assert not bracket.check_stop(99.96)
    assert not bracket.check_stop(99.94)  # triggered, but below the 99.90 limit
    assert bracket.stop_triggered
    assert bracket.check_stop(99.90)
    assert not bracket.active
    assert not bracket.check_stop(99.0)


def test_kalman_hedge_tracks_stable_ratio():
    rng = np.random.default_rng(11)
    x = np.linspace(90.0, 110.0, 500)
    y = 1.25 * x + rng.normal(0.0, 0.02, size=x.size)
    kf = KalmanHedge(beta0=1.0, process_var=1e-6, meas_var=1e-2)
    for xi, yi in zip(x, y):
        beta = kf.update(float(xi), float(yi))
    assert abs(beta - 1.25) < 0.01


def test_rolling_stats_match_sample_std_after_window_rolls():
    strategy = PairStrategy(window=5)
    values = [1.0, 1.5, 2.0, 0.5, 3.0, -1.0, 2.5]
    for value in values:
        strategy._append_spread(value)

    expected = np.asarray(values[-5:], dtype=float)
    mean, sd = strategy._rolling_stats()
    assert mean == pytest.approx(float(expected.mean()))
    assert sd == pytest.approx(float(expected.std(ddof=1)))
