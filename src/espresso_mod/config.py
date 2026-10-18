import os

from pydantic import BaseModel


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

settings = Settings()
