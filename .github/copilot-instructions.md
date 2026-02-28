# Copilot instructions for this repo (espresso_mod)

## Project goal
Build a Raspberry Pi based espresso controller with a touch UI, temperature control, and valve control.
Development starts in **simulation mode** so features can be built and tested without hardware.

## Key design rules
- Never access GPIO/hardware directly from API endpoints.
- All hardware goes through HAL interfaces:
  - TemperatureSensor.read() -> TempReading
  - HeaterActuator.set_power(0..1)
  - ValveActuator.set_open(0..1)
- The simulator (espresso_mod.hal.sim) is the default implementation.
- Code must be safe-by-default: if sensor reading is not ok, heater power must go to 0.

## Architecture
- `espresso_mod/api.py`: HTTP API only
- `espresso_mod/services/control.py`: control loop + PID logic
- `espresso_mod/hal/*`: hardware abstraction + implementations
- `espresso_mod/domain/*`: pure domain logic (PID, profiles, models)

## Testing expectations
- Add/adjust tests for any bug fix or feature.
- Prefer deterministic simulation: if randomness is used, allow seeding or keep noise small.
- Keep mypy strict; add typing instead of disabling checks.

## Style
- Python 3.11+, type hints everywhere.
- Keep functions small; no hidden side effects.
- Add docstrings for public functions and any non-obvious math/assumptions.

## Roadmap hints
Near-term: async shot runner (state machine), telemetry history endpoint, pressure sensor via ADC.
Later: real MAX31865 implementation; microcontroller offload.
