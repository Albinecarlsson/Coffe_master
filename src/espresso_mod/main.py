from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from espresso_mod.api import close_runtime, get_runtime, router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the machine at boot, not on the first request.

    The runtime owns the control loop, the telemetry sampler and the history
    database. Creating it here means an unattended Pi is controlling the boiler
    from the moment uvicorn is up rather than waiting for the first UI poll. It
    also makes a hardware configuration error fail the service at startup, which
    systemd surfaces loudly and restarts.
    """
    get_runtime()
    try:
        yield
    finally:
        close_runtime()


app = FastAPI(title="Espresso Mod API", version="0.1.0", lifespan=lifespan)
app.include_router(router)

UI_PATH = Path(__file__).resolve().parent / "ui" / "index.html"
KIOSK_PATH = Path(__file__).resolve().parent / "ui" / "kiosk.html"

@app.get("/")
def ui() -> FileResponse:
    return FileResponse(UI_PATH)

@app.get("/kiosk")
def kiosk() -> FileResponse:
    """The touchscreen drink picker. See docs/renovation.md, Phase 6."""
    return FileResponse(KIOSK_PATH)
