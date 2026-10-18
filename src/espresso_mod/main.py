from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from espresso_mod.api import router

app = FastAPI(title="Espresso Mod API", version="0.1.0")
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
