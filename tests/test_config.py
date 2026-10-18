from __future__ import annotations

import pytest

from espresso_mod.config import _get_bool  # the env-parsing contract for flag settings


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on", " true "])
def test_get_bool_accepts_the_usual_truthy_spellings(monkeypatch, raw):
    monkeypatch.setenv("SOME_FLAG", raw)

    assert _get_bool("SOME_FLAG", False) is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", ""])
def test_get_bool_treats_anything_else_as_false(monkeypatch, raw):
    monkeypatch.setenv("SOME_FLAG", raw)

    assert _get_bool("SOME_FLAG", True) is False


def test_get_bool_falls_back_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_FLAG", raising=False)

    assert _get_bool("SOME_FLAG", True) is True
    assert _get_bool("SOME_FLAG", False) is False
