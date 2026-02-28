from fastapi import FastAPI
from fastapi.responses import FileResponse
from pathlib import Path

from espresso_mod.api import router

app = FastAPI(title="Espresso Mod API", version="0.1.0")
app.include_router(router)

UI_PATH = Path(__file__).resolve().parent / "ui" / "index.html"

@app.get("/")
def ui() -> FileResponse:
    return FileResponse(UI_PATH)
