from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app import auth
from app.api import initiatives, reference
from app.config import get_db_path
from app.db import make_engine


def get_app(db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="AI Cockpit API", version="0.1.0")
    app.state.engine = make_engine(db_path or get_db_path())

    @app.exception_handler(OperationalError)
    async def _db_unavailable(_: Request, __: OperationalError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "Datenbank vorübergehend nicht verfügbar"},
            headers={"Retry-After": "2"},
        )

    # Liveness only; the reference deployment configures no probes, so no
    # /startup or /readz. Deliberately without auth and without touching the DB.
    @app.get("/api/healthz", tags=["infra"])
    def healthz() -> str:
        return "OK"

    app.include_router(auth.auth_router)
    app.include_router(initiatives.router)
    app.include_router(reference.router)
    return app
