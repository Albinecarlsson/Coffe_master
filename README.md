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
- **Touch-friendly web UI** (planned)

All hardware interactions go through a **Hardware Abstraction Layer (HAL)**, allowing full development using a thermal simulator before touching any actual machine components.

---

## ✨ Features

### Currently Implemented
- ✅ **PID Temperature Controller** – maintains precise boiler temperature with configurable tuning
- ✅ **Hardware Abstraction Layer** – swap between simulator and real GPIO/sensors without code changes
- ✅ **Shot Runner** – state machine for automated espresso shot execution
- ✅ **Telemetry System** – time-series data logging for temperature, power, and valve state
- ✅ **HTTP API** – control and monitor via RESTful endpoints (FastAPI)
- ✅ **Thermal Simulation** – realistic boiler physics model for offline development

### Roadmap
- 🔜 Touch UI (HTML5 + WebSockets for real-time updates)
- 🔜 Pressure sensor integration (ADC-based)
- 🔜 Shot history persistence (SQLite)
- 🔜 MAX31865 RTD sensor implementation (PT100/PT1000)
- 🔜 Advanced pressure profiling (flow control valve)

---

## 🚀 Quickstart

### 1. Clone and Setup
```bash
git clone https://github.com/yourusername/Coffe_master.git
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
Interactive API docs: `http://127.0.0.1:8000/docs`

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

# Start a classic espresso shot (25s extraction)
curl -X POST http://127.0.0.1:8000/shot/run/classic_espresso

# Check shot status
curl http://127.0.0.1:8000/shot/status

# Cancel running shot
curl -X POST http://127.0.0.1:8000/shot/cancel
```

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
│   └── shot_profiles.py # Shot profile definitions
├── hal/                # Hardware Abstraction Layer
│   ├── base.py         # Abstract interfaces
│   ├── sim.py          # Thermal simulator (default)
│   └── rtd_max31865.py # Real MAX31865 RTD sensor (future)
├── services/           # Orchestration & business logic
│   ├── control.py      # PID control loop
│   ├── shot_runner.py  # Shot execution state machine
│   ├── telemetry.py    # Data history tracking
│   └── runtime.py      # Service container & lifecycle
└── ui/
    └── index.html      # Web UI (under development)
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
pytest                  # Run all tests
pytest -v               # Verbose output
mypy src/               # Type checking
ruff check src/         # Linting
```

### Code Guidelines
- **Python 3.11+** with full type hints
- **Keep functions small** – no hidden side effects
- **Docstrings required** for public APIs and non-obvious logic
- **Add tests** for every bug fix and feature

---

## 🛠️ Hardware Setup (Future)

When ready to connect real hardware:

1. **Temperature Sensor**: MAX31865 RTD amplifier → PT100/PT1000 probe
2. **SSR Control**: GPIO → Solid State Relay → Heating element
3. **Valve Control**: GPIO → Solenoid valve driver
4. **Pressure Sensor** (optional): ADS1115 ADC → analog pressure transducer

Swap `espresso_mod.hal.sim` for real implementations in [config.py](src/espresso_mod/config.py).

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
