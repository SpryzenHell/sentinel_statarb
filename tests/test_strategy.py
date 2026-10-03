import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "python"))

from sentinel_statarb.strategy import DynamicDebouncer, OCOBracket


def test_dynamic_debouncer_requires_more_confirmation_in_high_vol():
    debouncer = DynamicDebouncer(base=2, max_confirmations=8, reference_vol=0.001)
    assert debouncer.required(0.001) == 3
    assert debouncer.required(0.005) >= 5


def test_oco_is_one_shot_and_uses_five_bps():
    bracket = OCOBracket(1, 100.0, reference_notional=100.0, stop_bps=5.0)
    assert bracket.active
    assert not bracket.check_stop(99.96)
    assert bracket.check_stop(99.94)
    assert not bracket.check_stop(99.0)
