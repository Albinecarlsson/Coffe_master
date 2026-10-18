from __future__ import annotations

import pytest

from espresso_mod.domain.pulse import Pulse


@pytest.mark.parametrize("on_s", [0.0, -1.0])
def test_a_pulse_needs_a_positive_on_time(on_s):
    with pytest.raises(ValueError, match="on_s"):
        Pulse(on_s=on_s, off_s=1.0)


def test_a_pulse_needs_a_non_negative_off_time():
    with pytest.raises(ValueError, match="off_s"):
        Pulse(on_s=1.0, off_s=-0.5)


def test_a_pulse_can_run_without_a_soak():
    pulse = Pulse(on_s=1.0, off_s=0.0)

    assert pulse.off_s == 0.0
