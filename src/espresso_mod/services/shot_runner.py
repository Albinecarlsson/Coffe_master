from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from dataclasses import dataclass

from espresso_mod.domain.clock import Clock, SystemClock
from espresso_mod.domain.shot_profiles import SHOT_PROFILES, ShotStep
from espresso_mod.hal.base import PumpActuator, ValveActuator
from espresso_mod.services.control import ControlLoop
from espresso_mod.services.pacing import pulse_until, wait_until


@dataclass
class _RunnerState:
    state: str = "idle"  # idle | running | done | canceled | error
    profile: str | None = None
    step_index: int = 0
    step_started_ts: float = 0.0
    started_ts: float = 0.0
    message: str | None = None
    # Derived from the clock when `status()` is called, never stored.
    total_elapsed_s: float = 0.0
    step_elapsed_s: float = 0.0


class ShotRunner:
    """
    Non-blocking shot runner.
    Runs profiles step-by-step on a background thread.

    Safety:
    - On cancel/error/finish, the pump stops and the valve is closed.
    """

    def __init__(
        self,
        control: ControlLoop,
        valve: ValveActuator,
        clock: Clock | None = None,
        *,
        pump: PumpActuator | None = None,
        on_finish: Callable[[], None] | None = None,
    ) -> None:
        self.control = control
        self.valve = valve
        # None means valve-only: the plant or test double models the flow itself.
        self.pump = pump
        self._clock: Clock = clock or SystemClock()
        self._on_finish = on_finish

        self._lock = threading.Lock()
        self._state = _RunnerState()
        self._thread: threading.Thread | None = None
        self._cancel = False

    def status(self) -> _RunnerState:
        with self._lock:
            state = _RunnerState(**self._state.__dict__)

        now = self._clock.now()
        if state.state in ("running", "done", "canceled", "error") and state.started_ts > 0:
            state.total_elapsed_s = max(0.0, now - state.started_ts)
        if state.state == "running" and state.step_started_ts > 0:
            state.step_elapsed_s = max(0.0, now - state.step_started_ts)
        return state

    def start(self, name: str) -> None:
        profile = SHOT_PROFILES.get(name)
        if not profile:
            raise KeyError(f"Unknown profile '{name}'. Known: {list(SHOT_PROFILES.keys())}")

        with self._lock:
            if self._state.state == "running":
                raise RuntimeError("Shot already running")
            self._state = _RunnerState(state="running", profile=name, step_index=0)
            self._cancel = False

        self._thread = threading.Thread(target=self._run_profile, args=(name, profile), daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        with self._lock:
            if self._state.state != "running":
                return
            self._cancel = True

    def _run_profile(self, name: str, profile: list[ShotStep]) -> None:
        start_ts = self._clock.now()
        try:
            with self._lock:
                self._state.started_ts = start_ts

            for idx, step in enumerate(profile):
                if self._is_canceled():
                    self._finish("canceled", "Canceled by user")
                    return

                with self._lock:
                    self._state.step_index = idx
                    self._state.step_started_ts = self._clock.now()

                if step.setpoint_c is not None:
                    self.control.set_setpoint(step.setpoint_c)

                if not self._run_step(step):
                    self._finish("canceled", "Canceled by user")
                    return

            self._finish("done", "Profile completed")
        except Exception as e:  # noqa: BLE001
            self._finish("error", f"{type(e).__name__}: {e}")

    def _run_step(self, step: ShotStep) -> bool:
        """Drive one step. False if the shot was cancelled part-way."""
        self.valve.set_open(step.valve_open)
        deadline = self._clock.now() + step.seconds

        if not step.pump_on:
            self._set_pump(False)
            return wait_until(self._clock, deadline, self._is_canceled)

        if step.pulse is not None:
            return pulse_until(self.pump, self._clock, step.pulse, deadline, self._is_canceled)

        self._set_pump(True)
        return wait_until(self._clock, deadline, self._is_canceled)

    def _is_canceled(self) -> bool:
        with self._lock:
            return bool(self._cancel)

    def _set_pump(self, on: bool) -> None:
        if self.pump is not None:
            self.pump.set_on(on)

    def _finish(self, state: str, msg: str | None) -> None:
        # Stop pushing first, then close the valve. Neither may raise: this runs
        # on the error path too, where the actuator is exactly what failed. The
        # pin is de-energised for real when the device itself is closed.
        with contextlib.suppress(Exception):
            self._set_pump(False)
        with contextlib.suppress(Exception):
            self.valve.set_open(0.0)
        with self._lock:
            self._state.state = state
            self._state.message = msg
        # Reporting is an observer, never a reason for a shot to fail.
        if self._on_finish is not None:
            with contextlib.suppress(Exception):
                self._on_finish()
