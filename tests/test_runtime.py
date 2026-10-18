from __future__ import annotations

import pytest

from espresso_mod.config import settings
from espresso_mod.services.runtime import Runtime


def test_rtd_mode_names_the_missing_actuators(monkeypatch):
    """HARDWARE_MODE=rtd fails loudly and says exactly what is still missing."""
    monkeypatch.setattr(settings, "hardware_mode", "rtd")

    with pytest.raises(RuntimeError, match="GPIO heater and valve actuators"):
        Runtime()


def test_unknown_hardware_mode_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "hardware_mode", "banana")

    with pytest.raises(ValueError, match="banana"):
        Runtime()
