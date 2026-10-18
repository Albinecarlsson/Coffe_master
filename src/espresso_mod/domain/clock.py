from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    """Time source for services that measure or wait for time.

    Injecting a clock lets time-dependent logic (shot profiles, control
    dwell times) be tested deterministically and without real waiting.
    """

    def now(self) -> float:
        """Monotonic time in seconds."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block for ``seconds``."""
        ...


class SystemClock:
    """Default :class:`Clock`, backed by the standard library."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
