# Espresso Mod – Isomac Milano Controller

**Transform a classic Isomac Milano espresso machine into a precision-controlled, programmable coffee brewing system.**

This project provides a Raspberry Pi-based controller with PID temperature control, shot profiling, and a web-based touch UI. Built with a **simulation-first architecture**, you can develop and test every feature without hardware access.

---

## 🎯 Project Overview

The Espresso Mod replaces the traditional thermostat and manual controls of an Isomac Milano with:
- **Precision PID temperature control** (±0.1°C accuracy)
- **Programmable shot profiles** (pressure/flow profiling)
- **Real-time telemetry and monitoring**
- **RESTful API** for programmatic control
- **Touch-friendly web UI** – single-page dashboard served at `/`

All hardware interactions go through a **Hardware Abstraction Layer (HAL)**, allowing full development using a thermal simulator before touching any actual machine components.

---

## ✨ Features

### Currently Implemented
- ✅ **PID Temperature Controller** – maintains precise boiler temperature with configurable tuning
- ✅ **Hardware Abstraction Layer** – swap between simulator and real GPIO/sensors without code changes
- ✅ **Shot Runner** – state machine for automated espresso shot execution
- ✅ **Telemetry System** – time-series data logging for temperature, power, and valve state
- ✅ **HTTP API** – control and monitor via RESTful endpoints (FastAPI)
- ✅ **Touch UI** – single-page dashboard for live state, shots and telemetry
- ✅ **Thermal Simulation** – realistic boiler physics model for offline development
- ✅ **MAX31865 RTD Driver** – PT100/PT1000 over SPI, with fault decoding and range checks

### Roadmap
- 🔜 GPIO heater and valve actuators, so `HARDWARE_MODE=rtd` works end to end
- 🔜 WebSocket push for real-time UI updates (the UI currently polls)
- 🔜 Pressure sensor integration (ADC-based)
- 🔜 Shot history persistence (SQLite)
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
Touch UI: `http://127.0.0.1:8000/`  
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

---

## 🖥️ Touch UI

Open `http://127.0.0.1:8000/` for the single-page dashboard. It shows live
temperature, heater power and valve state, lets you set the setpoint and toggle
the PID loop, runs any shot profile, and plots recent telemetry.

It polls the REST API every second; moving to WebSocket push is on the roadmap.

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
│   └── shot_profiles.py # Shot profile definitions
├── hal/                # Hardware Abstraction Layer
│   ├── base.py         # Abstract interfaces
│   ├── sim.py          # Thermal simulator (default)
│   └── rtd_max31865.py # MAX31865 RTD sensor over SPI (PT100/PT1000)
├── services/           # Orchestration & business logic
│   ├── control.py      # PID control loop
│   ├── shot_runner.py  # Shot execution state machine
│   ├── telemetry.py    # Data history tracking
│   └── runtime.py      # Service container & lifecycle
└── ui/
    └── index.html      # Single-page touch UI (polls the API)
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

1. **Temperature Sensor**: MAX31865 RTD amplifier → PT100/PT1000 probe — driver implemented, see below
2. **SSR Control**: GPIO → Solid State Relay → Heating element — not implemented yet
3. **Valve Control**: GPIO → Solenoid valve driver — not implemented yet
4. **Pressure Sensor** (optional): ADS1115 ADC → analog pressure transducer — not implemented yet

### MAX31865 RTD sensor

Enable SPI (`raspi-config` → Interface Options) and install the optional dependency:

```bash
pip install -e ".[hardware]"   # Raspberry Pi only
```

Then point the driver at your probe via `.env` (see [.env.example](.env.example)):

| Variable | Default | Meaning |
| --- | --- | --- |
| `RTD_R0_OHMS` | `100.0` | Probe nominal resistance: 100 for PT100, 1000 for PT1000 |
| `RTD_RREF_OHMS` | `430.0` | Reference resistor on the breakout (4300 for the PT1000 board) |
| `RTD_WIRES` | `2` | 2, 3 or 4; three-wire probes get lead-resistance compensation |
| `RTD_FILTER_HZ` | `60` | Mains rejection: 50 (Europe) or 60 (US) |
| `RTD_SPI_BUS` / `RTD_SPI_DEVICE` | `0` / `0` | SPI bus and chip-select |

The driver runs the chip in auto-convert mode, so a `read()` is a fast register access
rather than a ~75 ms blocking wait — worth having when the control loop and the
telemetry sampler both sample at `CONTROL_LOOP_HZ`. It reports `ok=False` for chip
faults, for the first conversion after startup, and for resistances outside the RTD's
standard range (a shorted or disconnected probe).

`HARDWARE_MODE=rtd` still raises at startup, and deliberately so: the sensor is ready,
but the GPIO heater and valve actuators are not, and only the simulator provides those.

---

## 📖 Documentation

- [Architecture Overview](prompts/architecture.md)
- [API Contracts](prompts/api_contracts.md)  
- [Simulation Model](prompts/sim_model.md)

---

## 📜 License

MIT License – See LICENSE file for details.

---

## 🙏 Acknowledgments

Built for the Isomac Milano, a prosumer espresso machine with excellent thermal stability. This mod brings modern control to classic Italian engineering.
