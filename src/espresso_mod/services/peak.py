"""Peak brew pressure for one shot.

The pressure sensor is sampled by the telemetry thread, but a pour reports its
own peak when it finishes. The sampler feeds this small accumulator: it is reset
when a pour starts and read when the pour is written to history. The pour thread
may also read the sender to end a preinfusion burst at its target; the peak still
comes from the sampler, so every trace and history row has one source.

Only healthy readings are observed; a fault must not look like a 16 bar shot.
"""

from __future__ import annotations

import threading


class PeakPressure:
    """Thread-safe highest pressure seen since the last :meth:`reset`."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bar: float | None = None

    def reset(self) -> None:
        with self._lock:
            self._bar = None

    def observe(self, bar: float) -> None:
        with self._lock:
            if self._bar is None or bar > self._bar:
                self._bar = bar

    @property
    def bar(self) -> float | None:
        """The peak, or None if nothing was observed (or the sensor is absent)."""
        with self._lock:
            return self._bar
