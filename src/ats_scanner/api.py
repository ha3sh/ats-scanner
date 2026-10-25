"""Routes, request validation, error envelope.

Transport only: version reporting, the error envelope, and response headers
(SPEC §5). Business logic lives in core/; wiring lives in main.py.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from ats_scanner.config import (
    APP_VERSION,
    DICTIONARY_VERSION,
    ENGINE_VERSION,
    MAX_FILE_BYTES,
    MAX_JD_CHARS,
    MAX_PAGES,
)

# SPEC §5 error table: every code with its HTTP status.
ERROR_STATUSES: dict[str, int] = {
    "unsupported_type": 415,
    "too_large": 413,
    "too_many_pages": 422,
    "encrypted_pdf": 422,
    "no_extractable_text": 422,
    "bad_docx": 422,
    "jd_too_short": 422,
    "jd_too_long": 422,
    "invalid_request": 422,
}

_VALIDATION_MESSAGE = (
    "The request was not valid. Check the uploaded file and job description fields, then try again."
)


class AppError(Exception):
    """An error carrying a SPEC §5 code and one human sentence."""

    def __init__(self, code: str, message: str) -> None:
        if code not in ERROR_STATUSES:
            raise ValueError(f"{code!r} is not a SPEC error code")
        self.code = code
        self.message = message
        super().__init__(message)


class ErrorEnvelope(BaseModel):
    """The one error shape every error response uses (SPEC §5)."""

    code: str
    message: str


class Limits(BaseModel):
    max_file_bytes: int
    max_pages: int
    max_jd_chars: int


class HealthResponse(BaseModel):
    version: str
    engine_version: str
    dictionary_version: int
    limits: Limits


def create_app() -> FastAPI:
    """Build a fresh app instance; tests and the launcher each get their own."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Day 2 wires the Extractor adapter and the dictionary load here.
        yield

    app = FastAPI(title="ats-scanner", lifespan=lifespan)

    @app.middleware("http")
    async def _api_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        # Belt and braces: uvicorn does not send this today; the guarantee
        # must not depend on the server staying polite.
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]
        return response

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=ERROR_STATUSES[exc.code],
            content=ErrorEnvelope(code=exc.code, message=exc.message).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=ERROR_STATUSES["invalid_request"],
            content=ErrorEnvelope(code="invalid_request", message=_VALIDATION_MESSAGE).model_dump(),
        )

    @app.get("/api/health", response_model=HealthResponse)
    async def _health() -> HealthResponse:
        return HealthResponse(
            version=APP_VERSION,
            engine_version=ENGINE_VERSION,
            dictionary_version=DICTIONARY_VERSION,
            limits=Limits(
                max_file_bytes=MAX_FILE_BYTES,
                max_pages=MAX_PAGES,
                max_jd_chars=MAX_JD_CHARS,
            ),
        )

    return app
