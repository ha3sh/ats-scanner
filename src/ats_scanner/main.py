"""FastAPI app, static mount, startup wiring.

build_app() is the production composition: the API app from api.create_app()
plus the committed static directory mounted at "/". No module-level app
instance and no module-level state — the launcher and every test call
build_app() or create_app() themselves.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ats_scanner.api import create_app

STATIC_DIR = Path(__file__).parent / "static"


def build_app() -> FastAPI:
    """Create the API app and mount the built frontend at "/"."""
    app = create_app()
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
