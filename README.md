# Espresso Mod – Isomac Brio Controller

**Transform a classic Isomac Brio espresso machine into a precision-controlled, programmable coffee brewing system.**

This project provides a Raspberry Pi-based controller with PID temperature control, one-touch drink dosing, shot profiling, and a web-based touch UI. Built with a **simulation-first architecture**, you can develop and test every feature without hardware access.

> **Renovating the machine itself?** The electrical, mechanical and shopping
> plan — including what is genuinely safe to modify on a 230 V appliance with a
> boiler — is in [docs/renovation.md](docs/renovation.md). Read it before
> ordering parts.

---

## 🎯 Project Overview

The Espresso Mod replaces the traditional thermostat and manual controls of an Isomac Brio with:
- **Precision PID temperature control** (±0.1°C accuracy)
- **One-touch drinks** – pick a coffee, the machine doses the water and sets its own temperature
- **Programmable shot profiles** (pressure/flow profiling)
- **Real-time telemetry and monitoring**
- **RESTful API** for programmatic control
- **Touch-friendly web UIs** – an engineer dashboard at `/` and a drink picker at `/kiosk`

All hardware interactions go through a **Hardware Abstraction Layer (HAL)**, allowing full development using a thermal simulator before touching any actual machine components.

---

## ✨ Features

### Currently Implemented
- ✅ **PID Temperature Controller** – maintains precise boiler temperature with configurable tuning
- ✅ **Hardware Abstraction Layer** – swap between simulator and real GPIO/sensors without code changes
- ✅ **Drink Catalogue & Dosing** – ristretto/espresso/doppio/lungo, poured by volume
- ✅ **Shot Runner** – state machine for automated espresso shot execution
- ✅ **Telemetry System** – time-series data logging for temperature, power, valve state and pressure
- ✅ **HTTP API** – control and monitor via RESTful endpoints (FastAPI)
- ✅ **Kiosk UI** – touchscreen drink picker with live temperature and readiness gating
- ✅ **Thermal Simulation** – realistic boiler physics model for offline development
- ✅ **MAX31865 RTD Driver** – PT100/PT1000 over SPI, with fault decoding and range checks
- ✅ **GPIO Actuators** – time-proportioned SSR heater, plus solenoid valve and pump for `HARDWARE_MODE=rtd`
- ✅ **Pump-Pulsed Preinfusion** – wet the puck in bursts before the measured pour
- ✅ **Shot History** – every shot and pour appended to SQLite, with the last few on the kiosk
- ✅ **Brew Pressure Monitoring** – 0–16 bar sender through an ADS1115, live on both UIs and logged per shot

### Roadmap
- 🔜 WebSocket push for real-time UI updates (the UI currently polls)
- 🔜 Pressure-guided preinfusion (stop the pulse when the puck is pressurised)
- 🔜 Volumetric dosing from a real flow meter (today it is time-based)
- 🔜 Gravimetric dosing (load cell under the drip tray)
- 🔜 Hot-water path, so americanos and tea can be poured in one action
- 🔜 Grinder control (grind by weight)
- 🔜 Advanced pressure profiling (flow control valve)

---

## 🚀 Quickstart

### 1. Clone and Setup
```bash
git clone https://github.com/Albinecarlsson/Coffe_master.git
cd Coffe_master
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
# or: source .venv/bin/activate  # Linux/macOS
pip install -U pip
pip install -e ".[dev]"
```

### 2. Run in Simulation Mode
No hardware needed – the simulator models boiler thermal dynamics.

```bash
uvicorn espresso_mod.main:app --reload
```

Server starts at `http://127.0.0.1:8000`  
Engineer dashboard: `http://127.0.0.1:8000/`  
Kiosk drink picker: `http://127.0.0.1:8000/kiosk`  
Interactive API docs: `http://127.0.0.1:8000/docs`

Everything runs against the in-memory thermal simulator, so you can drive the
whole system from the UI without any hardware attached.

---

## 🧪 Testing the API

### Basic Temperature Control
```bash
# Check current state
curl http://127.0.0.1:8000/state

# Set target temperature to 93°C
curl -X POST http://127.0.0.1:8000/control/setpoint \
  -H "Content-Type: application/json" \
  -d '{"setpoint_c": 93}'

# Enable PID controller
curl -X POST http://127.0.0.1:8000/control/enable \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Monitor telemetry (last 30 seconds)
curl http://127.0.0.1:8000/telemetry?seconds=30
```

### Running a Shot Profile
```bash
# List available profiles
curl http://127.0.0.1:8000/shot/profiles

# Start a classic espresso shot (31 s: 6 s pulsed preinfusion + 25 s extraction)
curl -X POST http://127.0.0.1:8000/shot/start/classic_espresso

# Check shot status
curl http://127.0.0.1:8000/shot/status

# Cancel running shot
curl -X POST http://127.0.0.1:8000/shot/cancel
```

### Pouring a Drink
```bash
# List the drink catalogue and the calibrated brew flow
curl http://127.0.0.1:8000/drinks

# Everything the kiosk screen polls: temperature, readiness, pour progress
curl http://127.0.0.1:8000/kiosk/status

# Pour an espresso. Refused with 409 until the boiler is at the drink's
# temperature, which tapping a drink also starts heating towards.
curl -X POST http://127.0.0.1:8000/drinks/pour/espresso

# Pour anyway, without waiting for temperature (use with care)
curl -X POST "http://127.0.0.1:8000/drinks/pour/espresso?force=true"

# Stop a pour
curl -X POST http://127.0.0.1:8000/drinks/cancel

# The last few shots and pours, newest first
curl "http://127.0.0.1:8000/history?limit=5"
```

---

## 🖥️ Touch UI

Two pages are served from the same API:

**Kiosk — `http://127.0.0.1:8000/kiosk`** is the one for daily use. It is styled
like the machine rather than a dashboard: espresso browns, crema accents, a serif
wordmark and a drawn cup per drink whose fill matches its volume. The header shows
the time, a temperature ring that fills as the boiler warms, and a readiness pill.
Tapping a tile opens a full-screen pour card with a cup that fills as the shot
lands, delivered millilitres, a progress bar and a stop button. Because the
mechanical gauge goes away when the screen takes its place, the card also shows
brew pressure on a 0–16 bar scale with a mark at 9 bar, turning amber-red above
13 bar — a choked shot is visible while it happens, not after. The result lingers
for a moment, then clears itself. Tiles disable until the boiler is at temperature,
or the pour can be forced from the toast that appears. Under the tiles, the last few
drinks come back from the shot history as chips, including the peak pressure. After a
minute without a touch the kiosk turns into an idle clock: a large serif time, the
date, a cup trailing slow wisps of steam and a gently breathing temperature ring.
Any tap or key brings the drinks back; faults and a running pour always take
priority over the idle view.

**Engineer dashboard — `http://127.0.0.1:8000/`** shares the same warm palette and
shows live temperature, heater power, valve state and pressure (number plus a 0–16
bar meter), lets you set the setpoint and toggle the PID loop, runs any shot
profile, and plots recent telemetry with pressure on its own axis.

Both poll the REST API; moving to WebSocket push is on the roadmap. For a panel on
the machine, run Chromium fullscreen pointed at `/kiosk`.

---

## 🏗️ Architecture

```
espresso_mod/
├── api.py              # FastAPI HTTP endpoints
├── main.py             # Application entry point
├── config.py           # Configuration management
├── domain/             # Pure business logic (no I/O)
│   ├── models.py       # Data models (State, TempReading, etc.)
│   ├── pid.py          # PID controller implementation
│   ├── clock.py        # Injectable time source (deterministic timing)
│   ├── pulse.py        # Pump on/off pattern for preinfusion
│   ├── pressure.py     # Volts-to-bar maths for a ratiometric sender
│   ├── drinks.py       # Drink catalogue (volumes and temperatures)
│   └── shot_profiles.py # Shot profile definitions
├── hal/                # Hardware Abstraction Layer
│   ├── base.py         # Abstract interfaces
│   ├── sim.py          # Thermal and pressure simulator (default)
│   ├── gpio.py         # SSR heater, solenoid valve and pump over GPIO
│   ├── pressure_ads1115.py # Brew pressure sender over I2C (ADS1115)
│   └── rtd_max31865.py # MAX31865 RTD sensor over SPI (PT100/PT1000)
├── services/           # Orchestration & business logic
│   ├── control.py      # PID control loop
│   ├── doser.py        # Volumetric pour control
│   ├── history.py      # SQLite shot history
│   ├── pacing.py       # Cancellable waits and pump pulsing
│   ├── peak.py         # Peak pressure for the shot in progress
│   ├── shot_runner.py  # Shot execution state machine
│   ├── telemetry.py    # Data history tracking
│   └── runtime.py      # Service container & lifecycle
└── ui/
    ├── index.html      # Engineer dashboard (polls the API)
    └── kiosk.html      # Touchscreen drink picker
```

### Design Principles
1. **HAL Isolation** – API endpoints never touch GPIO directly; all hardware via interfaces
2. **Safe-by-Default** – invalid sensor readings immediately zero heater power
3. **Simulation-First** – every feature testable without hardware
4. **Strict Typing** – mypy strict mode enforced

---

## 🔬 Development

### Run Tests
```bash
pytest --cov=espresso_mod --cov-report=term-missing   # Tests + coverage (CI gate: 90%)
mypy src/               # Type checking (strict)
ruff check .            # Linting
```

### Code Guidelines
- **Python 3.11+** with full type hints
- **Keep functions small** – no hidden side effects
- **Docstrings required** for public APIs and non-obvious logic
- **Add tests** for every bug fix and feature

---

## 🛠️ Hardware Setup

`HARDWARE_MODE=sim` needs no hardware at all. To drive a real machine, enable SPI
and I2C (`raspi-config` → Interface Options) and install the optional dependencies:

```bash
pip install -e ".[hardware]"   # Raspberry Pi only
```

Then set `HARDWARE_MODE=rtd` in `.env` and map the hardware to your board:

| Variable | Default | Meaning |
| --- | --- | --- |
| `RTD_R0_OHMS` | `100.0` | Probe nominal resistance: 100 for PT100, 1000 for PT1000 |
| `RTD_RREF_OHMS` | `430.0` | Reference resistor on the breakout (4300 for the PT1000 board) |
| `RTD_WIRES` | `2` | 2, 3 or 4; three-wire probes get lead-resistance compensation |
| `RTD_FILTER_HZ` | `60` | Mains rejection: 50 (Europe) or 60 (US) |
| `RTD_SPI_BUS` / `RTD_SPI_DEVICE` | `0` / `0` | SPI bus and chip-select |
| `HEATER_GPIO_PIN` | `17` | SSR control pin (BCM) |
| `VALVE_GPIO_PIN` | `27` | Solenoid driver pin (BCM) |
| `PUMP_GPIO_PIN` | `22` | Pump relay/SSR control pin (BCM) |
| `HEATER_ACTIVE_HIGH` / `VALVE_ACTIVE_HIGH` / `PUMP_ACTIVE_HIGH` | `true` | Set false for active-low driver boards |
| `HEATER_WINDOW_S` | `1.0` | Time-proportioning window for the relay |
| `BREW_FLOW_ML_S` | `1.1` | Calibrated flow used to convert volume into pump seconds |
| `READY_TOLERANCE_C` | `2.0` | How close to setpoint the boiler must be before a pour is allowed |
| `HISTORY_DB_PATH` | `data/history.db` | SQLite file for shot history; created on first use |
| `PRESSURE_ENABLED` | `true` | Set `false` while no sender is fitted; the UI shows a dash, not a fake 0 bar |
| `PRESSURE_I2C_BUS` / `PRESSURE_I2C_ADDRESS` | `1` / `0x48` | ADS1115 bus and address (`0x48`–`0x4B`) |
| `PRESSURE_ADS_CHANNEL` | `0` | Single-ended input `AIN0`–`AIN3` |
| `PRESSURE_BAR_MAX` | `16.0` | The sender's rated span |
| `PRESSURE_VOLTS_MIN` / `PRESSURE_VOLTS_MAX` | `0.5` / `4.5` | Sender output at 0 bar and at full scale |
| `PRESSURE_DIVIDER` | `2.0` | Sender volts ÷ ADC volts (2.0 for a 10k/10k divider) |
| `PRESSURE_ADS_PGA` | `4.096` | ADS1115 full-scale range in volts |
| `PRESSURE_ADS_DATA_RATE` | `128` | Conversions per second (8…860) |

### MAX31865 RTD sensor

The driver runs the chip in auto-convert mode, so a `read()` is a fast register access
rather than a ~75 ms blocking wait — worth having when the control loop and the
telemetry sampler both sample at `CONTROL_LOOP_HZ`. It reports `ok=False` for chip
faults, for the first conversion after startup, and for resistances outside the RTD's
standard range (a shorted or disconnected probe).

### SSR heater

A solid state relay is on or off, so the PID's continuous duty cycle is applied by
holding the element on for `duty × HEATER_WINDOW_S` at the start of each window.
A one second window is far shorter than a boiler's thermal time constant, and
switching at around 1 Hz is gentle on the relay.

The element is de-energised on startup and on shutdown, and the applied duty drops to
zero if the control loop stops sending commands for a second. A loop that stalls or
dies must not leave the element latched on.

### Solenoid valve

A solenoid has two states, so it cannot be throttled: **any** non-zero demand opens it
fully and `0` closes it. A demand of 0.2 means "some water", not 20% flow. `GpioValve`
takes an `open_threshold` if you ever want to suppress small demands, but the default
is zero — refusing a profile step silently is worse than opening a binary valve.

Because of that, the built-in shot profiles get their preinfusion from the pump,
not the valve: a short burst of full pressure, then a soak with the valve still
open while the pressure decays into the puck, repeated before the continuous
pour. `ShotStep.pump_on=False` gives a plain dwell. The timings in
`domain/shot_profiles.py` are a starting point — they depend on the pump, the
basket and the grind, so tune them on the bench (Phase 4 in
[docs/renovation.md](docs/renovation.md)).

### Brew pressure

The physical manometer is in the way of the touchscreen, so a 0–16 bar sender
takes its place on the group circuit and the screen becomes the gauge. A typical
sender is ratiometric: 0.5 V at 0 bar, 4.5 V at 16 bar, on 5 V. The ADS1115 runs
at 3.3 V with the Pi, so the signal goes through a **2:1 divider** first
(`PRESSURE_DIVIDER=2.0`). Wiring:

```
sender V+  -> 5 V            ADS1115 VDD -> 3.3 V
sender GND -> GND            ADS1115 GND -> GND (common)
sender S   -> 10k -> AIN0    ADS1115 SDA/SCL -> Pi (address 0x48)
                    10k -> GND
                    100 nF from AIN0 to GND
```

The chip stays in continuous-conversion mode (128 SPS by default), so sampling is a
two-byte register read rather than a blocking conversion — the telemetry thread and
the web API both read it. It reports `ok=False` for the first conversions after
startup, for a signal below 0.2 V (sender unplugged), above 4.8 V (wiring or
divider fault) and for an I2C error. Both UIs show a dash instead of a
plausible-looking 0.0 bar when that happens.

Pressure is **monitoring only**: a vibration pump is not dimmable, so nothing in the
control path uses the reading yet. It is in the telemetry stream on its own axis,
in `/state` and `/kiosk/status`, and the peak of each shot or pour is written to
history (`peak_bar`). That is the number to watch when you change the grind: a
shot that pins at 13–14 bar is choked, and one that never reaches 5 bar is
channeling or too coarse.

Calibrate by reading the sender at rest (0 bar) and at the pump's dead-head or
against a known gauge, then adjust `PRESSURE_VOLTS_MIN` / `PRESSURE_VOLTS_MAX`.
Set `PRESSURE_ENABLED=false` to run without a sender until it is fitted.

**Safety:** the sender sees brew pressure and near-boiling water. Use a part rated
for at least 16 bar and 120 °C with brass or stainless wetted parts, fit it with the
right thread (G1/4 or 1/8" BSP — check the port), and leak-test with the case open
before closing the machine. If in doubt, keep the mechanical gauge on a tee: a
leak inside the case next to mains wiring is the worst failure mode in this build.

### Pump and dosing

The pump also sits on the mains side behind its own relay, so `PUMP_GPIO_PIN` only
switches a control line. A pour opens the valve first and then starts the pump, and
stops the pump before shutting the valve, so the machine never dead-heads against a
closed valve.

The Brio has no flow meter yet, so volume is **time based**: the doser runs the pump
for `water_ml / BREW_FLOW_ML_S` seconds. Calibrate `BREW_FLOW_ML_S` once by timing a
pour into a cup on a scale — every drink scales from that one number. A real flow
meter is the Phase 3 upgrade in [docs/renovation.md](docs/renovation.md).

`water_ml` is water delivered *through the group*, not the yield in the cup: the puck
keeps roughly twice its own weight in water, so a 9 g dose at 30 ml through the group
yields about 12 ml. Weigh the cup when calibrating.

Every drink also gets a pump-pulsed preinfusion before the measured pour: 1.5 s on,
1.5 s off, for six seconds. That water stays in the puck, so it is **not** counted
against `water_ml`; only the continuous pour after it counts. This is the same idea
as the shot-profile preinfusion above, driven from `Drink.preinfusion`.

### Shot history

Every finished shot and pour is appended to SQLite (`HISTORY_DB_PATH`). The table is
created on the first pour, so nothing is written until the machine has actually made
coffee. `GET /history?limit=20` returns the newest first; the kiosk shows the last
six. A write failure is logged nowhere and deliberately ignored — history is an
observer, and a full disk must not turn a completed shot into an error.

Each row also keeps the **peak brew pressure** for that shot. The database from
before pressure logging is migrated in place (one `ALTER TABLE`) the next time it is
read or written, so existing history is not lost.

### Control-loop faults

An exception from the sensor or an actuator no longer kills the control thread. The
loop cuts the element, records `control_error`, and keeps running, so a transient
SPI glitch recovers on its own instead of needing a restart. Both UIs show it: the
dashboard's control pill turns red and the kiosk's readiness pill reads
"Control fault", with the exception as the hover text.

---

## 📖 Documentation

- [Renovation Plan & Shopping List](docs/renovation.md)
- [Architecture Overview](prompts/architecture.md)
- [API Contracts](prompts/api_contracts.md)  
- [Simulation Model](prompts/sim_model.md)

---

## 📜 License

MIT License – See LICENSE file for details.

---

## 🙏 Acknowledgments

Built for the Isomac Brio, a compact Italian machine with a small boiler and a
built-in grinder. This mod brings modern control to classic Italian engineering.
