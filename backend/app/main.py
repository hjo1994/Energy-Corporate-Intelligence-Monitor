from __future__ import annotations

import sys
from pathlib import Path
import os

if os.getenv("EG_AUTH_DEV_MODE", "").lower() == "true":
    sys.path.insert(
        0,
        str(Path(__file__).resolve().parent.parent / "local_stubs")
    )
import eg_auth
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app import auth
from app.api import initiatives, reference
from app.config import get_db_path
from app.db import make_engine
from app import docs


app = FastAPI(
    title="AI Cockpit API",
    openapi_url="/api/openapi.json",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)


def get_app(db_path: Path | None = None) -> FastAPI:
    app.state.engine = make_engine(db_path or get_db_path())

    @app.exception_handler(OperationalError)
    async def _db_unavailable(_: Request, __: OperationalError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "Datenbank vorübergehend nicht verfügbar"},
            headers={"Retry-After": "2"},
        )

    @app.get("/api/healthz", tags=["infra"])
    def healthz() -> str:
        return "OK"

    app.include_router(auth.auth_router)
    app.include_router(initiatives.router)
    app.include_router(reference.router)

    # Offline Swagger UI
    app.include_router(docs.router)
    docs.add_static_files(app)

    return app


app = get_app()