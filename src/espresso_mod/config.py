from pydantic import BaseModel
import os

class Settings(BaseModel):
    hardware_mode: str = os.getenv("HARDWARE_MODE", "sim")
    sim_ambient_c: float = float(os.getenv("SIM_AMBIENT_C", "22.0"))
    sim_initial_water_c: float = float(os.getenv("SIM_INITIAL_WATER_C", "25.0"))
    control_loop_hz: int = int(os.getenv("CONTROL_LOOP_HZ", "10"))

settings = Settings()
