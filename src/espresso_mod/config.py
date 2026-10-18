import os

from pydantic import BaseModel


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Settings(BaseModel):
    hardware_mode: str = os.getenv("HARDWARE_MODE", "sim")
    sim_ambient_c: float = float(os.getenv("SIM_AMBIENT_C", "22.0"))
    sim_initial_water_c: float = float(os.getenv("SIM_INITIAL_WATER_C", "25.0"))
    control_loop_hz: int = int(os.getenv("CONTROL_LOOP_HZ", "10"))

    # MAX31865 RTD sensor (used when HARDWARE_MODE=rtd)
    rtd_r0_ohms: float = float(os.getenv("RTD_R0_OHMS", "100.0"))
    rtd_rref_ohms: float = float(os.getenv("RTD_RREF_OHMS", "430.0"))
    rtd_wires: int = int(os.getenv("RTD_WIRES", "2"))
    rtd_filter_hz: int = int(os.getenv("RTD_FILTER_HZ", "60"))
    rtd_spi_bus: int = int(os.getenv("RTD_SPI_BUS", "0"))
    rtd_spi_device: int = int(os.getenv("RTD_SPI_DEVICE", "0"))

    # GPIO actuators (used when HARDWARE_MODE=rtd)
    heater_gpio_pin: int = int(os.getenv("HEATER_GPIO_PIN", "17"))
    # Solid state relay modules differ: set these false for active-low boards
    heater_active_high: bool = _get_bool("HEATER_ACTIVE_HIGH", True)
    # Time-proportioning window for the relay, in seconds
    heater_window_s: float = float(os.getenv("HEATER_WINDOW_S", "1.0"))
    valve_gpio_pin: int = int(os.getenv("VALVE_GPIO_PIN", "27"))
    valve_active_high: bool = _get_bool("VALVE_ACTIVE_HIGH", True)
    pump_gpio_pin: int = int(os.getenv("PUMP_GPIO_PIN", "22"))
    pump_active_high: bool = _get_bool("PUMP_ACTIVE_HIGH", True)

    # Dosing
    # Calibrated brew flow: measure it by timing a pour into a cup on a scale.
    brew_flow_ml_s: float = float(os.getenv("BREW_FLOW_ML_S", "1.1"))
    # How close to the setpoint the boiler must be before a pour is allowed.
    ready_tolerance_c: float = float(os.getenv("READY_TOLERANCE_C", "2.0"))

    # Shot history (SQLite). Created lazily on the first pour.
    history_db_path: str = os.getenv("HISTORY_DB_PATH", "data/history.db")

settings = Settings()
