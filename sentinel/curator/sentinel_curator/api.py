from __future__ import annotations

from fastapi import FastAPI

from . import __version__

app = FastAPI(title="Sentinel Curator", version=__version__)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "sentinel-curator", "version": __version__}
