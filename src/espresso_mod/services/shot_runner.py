from __future__ import annotations

import threading
from dataclasses import dataclass

from espresso_mod.domain.clock import Clock, SystemClock
from espresso_mod.domain.shot_profiles import SHOT_PROFILES, ShotStep
from espresso_mod.hal.base import ValveActuator
from espresso_mod.services.control import ControlLoop


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
    - On cancel/error/finish, valve is closed.
    """

    def __init__(
        self,
        control: ControlLoop,
        valve: ValveActuator,
        clock: Clock | None = None,
    ) -> None:
        self.control = control
        self.valve = valve
        self._clock: Clock = clock or SystemClock()

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

                self.valve.set_open(step.valve_open)

                t0 = self._clock.now()
                while (self._clock.now() - t0) < step.seconds:
                    if self._is_canceled():
                        self._finish("canceled", "Canceled by user")
                        return
                    self._clock.sleep(0.02)

            self._finish("done", "Profile completed")
        except Exception as e:  # noqa: BLE001
            self._finish("error", f"{type(e).__name__}: {e}")

    def _is_canceled(self) -> bool:
        with self._lock:
            return bool(self._cancel)

    def _finish(self, state: str, msg: str | None) -> None:
        # always close valve at end
        try:
            self.valve.set_open(0.0)
        finally:
            with self._lock:
                self._state.state = state
                self._state.message = msg
