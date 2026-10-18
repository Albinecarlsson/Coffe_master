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
- ✅ **Telemetry System** – time-series data logging for temperature, power, and valve state
- ✅ **HTTP API** – control and monitor via RESTful endpoints (FastAPI)
- ✅ **Kiosk UI** – touchscreen drink picker with live temperature and readiness gating
- ✅ **Thermal Simulation** – realistic boiler physics model for offline development
- ✅ **MAX31865 RTD Driver** – PT100/PT1000 over SPI, with fault decoding and range checks
- ✅ **GPIO Actuators** – time-proportioned SSR heater, plus solenoid valve and pump for `HARDWARE_MODE=rtd`

### Roadmap
- 🔜 WebSocket push for real-time UI updates (the UI currently polls)
- 🔜 Pressure sensor integration (ADC-based)
- 🔜 Volumetric dosing from a real flow meter (today it is time-based)
- 🔜 Gravimetric dosing (load cell under the drip tray)
- 🔜 Hot-water path, so americanos and tea can be poured in one action
- 🔜 Grinder control (grind by weight)
- 🔜 Shot history persistence (SQLite)
- 🔜 Proportional preinfusion (needs a proportional valve or pump pressure control)
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

# Start a classic espresso shot (28 s: 3 s preinfusion + 25 s extraction)
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
```

---

## 🖥️ Touch UI

Two pages are served from the same API:

**Kiosk — `http://127.0.0.1:8000/kiosk`** is the one for daily use. It shows a tile
per drink with its water volume and temperature, a live boiler temperature, and a
readiness pill. Tapping a tile pours that drink and shows a progress bar with
delivered millilitres; the tiles disable themselves until the boiler is at
temperature, or the pour can be forced from the toast that appears.

**Engineer dashboard — `http://127.0.0.1:8000/`** shows live temperature, heater
power and valve state, lets you set the setpoint and toggle the PID loop, runs any
shot profile, and plots recent telemetry.

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
│   ├── drinks.py       # Drink catalogue (volumes and temperatures)
│   └── shot_profiles.py # Shot profile definitions
├── hal/                # Hardware Abstraction Layer
│   ├── base.py         # Abstract interfaces
│   ├── sim.py          # Thermal simulator (default)
│   ├── gpio.py         # SSR heater, solenoid valve and pump over GPIO
│   └── rtd_max31865.py # MAX31865 RTD sensor over SPI (PT100/PT1000)
├── services/           # Orchestration & business logic
│   ├── control.py      # PID control loop
│   ├── doser.py        # Volumetric pour control
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
(`raspi-config` → Interface Options) and install the optional dependencies:

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

A solenoid has two states, so a fractional demand cannot be honoured: the valve opens
at or above 0.5 and is closed below it. That means the built-in profiles' 0.2
preinfusion step leaves it **shut** rather than pretending to throttle a binary
device — real preinfusion needs a proportional valve or pump pressure control.

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
