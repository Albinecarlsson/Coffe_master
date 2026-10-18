"""Pouring a measured volume of water through the group.

The Brio has no flow meter, so the volume is estimated from time at a calibrated
flow rate. ``brew_flow_ml_s`` is a per-machine constant: measure it once by
timing a pour into a cup on a scale. When a flow meter is fitted (see
docs/renovation.md, Phase 3) this is the one place that has to change.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from dataclasses import dataclass

from espresso_mod.domain.clock import Clock, SystemClock
from espresso_mod.domain.drinks import Drink
from espresso_mod.hal.base import PumpActuator, ValveActuator
from espresso_mod.services.pacing import pulse_until, wait_until


@dataclass
class PourState:
    state: str = "idle"  # idle | pouring | done | canceled | error
    drink: str | None = None
    target_ml: float = 0.0
    flow_ml_s: float = 0.0
    started_ts: float = 0.0
    # When the measured pour began. Zero while preinfusing, so the water pushed
    # into the puck is not counted as delivered volume.
    poured_ts: float = 0.0
    message: str | None = None
    # Derived from the clock in `status()`, never stored.
    elapsed_s: float = 0.0
    delivered_ml: float = 0.0


class Doser:
    """Pours a drink's water volume, then stops.

    Safety:
        The water path is closed on completion, on cancel, on error and by
        :meth:`stop`. It opens valve-first so the pump is never dead-headed
        against a shut valve, and closes pump-first so the pump stops pushing
        before the path behind it is shut.
    """

    def __init__(
        self,
        valve: ValveActuator,
        *,
        pump: PumpActuator | None = None,
        brew_flow_ml_s: float = 1.1,
        clock: Clock | None = None,
        on_start: Callable[[], None] | None = None,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        if brew_flow_ml_s <= 0.0:
            raise ValueError(f"brew_flow_ml_s must be positive, got {brew_flow_ml_s}")

        self.valve = valve
        self.pump = pump
        self.brew_flow_ml_s = float(brew_flow_ml_s)
        self._clock: Clock = clock or SystemClock()
        self._on_start = on_start
        self._on_finish = on_finish

        self._lock = threading.Lock()
        self._state = PourState()
        self._thread: threading.Thread | None = None
        self._cancel = False

    def status(self) -> PourState:
        with self._lock:
            state = PourState(**self._state.__dict__)

        if state.started_ts > 0:
            state.elapsed_s = max(0.0, self._clock.now() - state.started_ts)
        if state.poured_ts > 0:
            state.delivered_ml = min(
                state.target_ml,
                max(0.0, self._clock.now() - state.poured_ts) * state.flow_ml_s,
            )
        return state

    def duration_s(self, drink: Drink) -> float:
        """How long the pump has to run to deliver the drink's water."""
        return drink.water_ml / self.brew_flow_ml_s

    def start(self, drink: Drink) -> None:
        with self._lock:
            if self._state.state == "pouring":
                raise RuntimeError("A pour is already running")
            self._state = PourState(
                state="pouring",
                drink=drink.key,
                target_ml=drink.water_ml,
                flow_ml_s=self.brew_flow_ml_s,
                started_ts=self._clock.now(),
            )
            self._cancel = False

        # Reset the peak before the first drop, but never let an observer stop a pour.
        if self._on_start is not None:
            with contextlib.suppress(Exception):
                self._on_start()

        self._thread = threading.Thread(target=self._run, args=(drink,), daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        with self._lock:
            if self._state.state != "pouring":
                return
            self._cancel = True

    def stop(self, timeout: float = 1.0) -> None:
        """Cancel any pour, wait for it to unwind, and close the water path."""
        self.cancel()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._close_water()

    # ---- internals ----

    def _run(self, drink: Drink) -> None:
        try:
            # Valve first: the water needs somewhere to go before the pump pushes.
            self.valve.set_open(1.0)

            if drink.preinfusion is not None and drink.preinfusion_s > 0.0:
                wet_done = pulse_until(
                    self.pump,
                    self._clock,
                    drink.preinfusion,
                    self._clock.now() + drink.preinfusion_s,
                    self._is_canceled,
                )
                if not wet_done:
                    self._finish("canceled", "Canceled by user")
                    return

            with self._lock:
                self._state.poured_ts = self._clock.now()
            if self.pump is not None:
                self.pump.set_on(True)

            deadline = self._clock.now() + self.duration_s(drink)
            if not wait_until(self._clock, deadline, self._is_canceled):
                self._finish("canceled", "Canceled by user")
                return

            self._finish("done", f"Poured {drink.water_ml:.0f} ml")
        except Exception as e:  # noqa: BLE001
            self._finish("error", f"{type(e).__name__}: {e}")
        finally:
            self._close_water()
            # Reporting is an observer, never a reason for a pour to fail.
            if self._on_finish is not None:
                with contextlib.suppress(Exception):
                    self._on_finish()

    def _is_canceled(self) -> bool:
        with self._lock:
            return bool(self._cancel)

    def _finish(self, state: str, message: str | None) -> None:
        with self._lock:
            self._state.state = state
            self._state.message = message

    def _close_water(self) -> None:
        # Pump first, then valve: stop pushing before shutting the path behind it.
        if self.pump is not None:
            self.pump.set_on(False)
        # Closing must never raise: callers run this from `finally` and from
        # shutdown, where an exception would skip cutting the heater. The pin is
        # de-energised for real when the device itself is closed anyway.
        with contextlib.suppress(Exception):
            self.valve.set_open(0.0)
