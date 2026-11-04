"""Routes, request validation, error envelope.

Transport only: version reporting, the error envelope, response headers
(SPEC §5), and the analyze endpoint. Business logic lives in core/; the
Extractor is injected by the caller (main.build_app()), so this module
imports nothing from adapters. cpu-bound extraction runs in a threadpool:
the endpoint is a plain sync function, which FastAPI moves off the event
loop (docs.fastapi.tiangolo.com, "Faster sync endpoints / run_in_threadpool").
"""

import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.formparsers import MultiPartParser
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ats_scanner.config import (
    APP_VERSION,
    DICTIONARY_VERSION,
    ENGINE_VERSION,
    MAX_FILE_BYTES,
    MAX_JD_CHARS,
    MAX_PAGES,
)
from ats_scanner.core.errors import AppError, ErrorCode
from ats_scanner.core.pipeline import analyze as analyze_pipeline
from ats_scanner.core.ports import Extractor
from ats_scanner.core.report import (
    SCHEMA_VERSION,
    AnalysisReport,
    ExtractedText,
    ExtractedTextPage,
    ReportMeta,
)

# SPEC §5 error table: every code with its HTTP status.
ERROR_STATUSES: dict[ErrorCode, int] = {
    ErrorCode.UNSUPPORTED_TYPE: 415,
    ErrorCode.TOO_LARGE: 413,
    ErrorCode.TOO_MANY_PAGES: 422,
    ErrorCode.ENCRYPTED_PDF: 422,
    ErrorCode.NO_EXTRACTABLE_TEXT: 422,
    ErrorCode.BAD_PDF: 422,
    ErrorCode.BAD_DOCX: 422,
    ErrorCode.JD_TOO_SHORT: 422,
    ErrorCode.JD_TOO_LONG: 422,
    ErrorCode.INVALID_REQUEST: 422,
}

_VALIDATION_MESSAGE = (
    "The request was not valid. Check the uploaded file and job description fields, then try again."
)

_TOO_LARGE_MESSAGE = (
    "The uploaded file is larger than the 5 MB limit. Try a smaller PDF or DOCX file."
)

_BODY_CAP = MAX_FILE_BYTES + 64 * 1024  # multipart framing allowance

_UPLOAD_MEMORY_LIMIT = _BODY_CAP  # spool threshold: at or above the body cap

# Starlette 1.9 spools a file part to a real temp file once it exceeds
# MultiPartParser.spool_max_size (default 1 MB). Request.form() does not
# forward that value, so the class attribute is the only knob. Raising it to
# the enforced body cap keeps every upload in RAM: the body-cap middleware
# rejects anything larger before the multipart parser runs.
SingleUserMultipartParser = MultiPartParser
SingleUserMultipartParser.spool_max_size = _UPLOAD_MEMORY_LIMIT

_LOG = logging.getLogger("ats_scanner.api")


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


async def _send_envelope(send: Send, code: str, message: str) -> None:
    """Send an error envelope as a raw ASGI response (used before routing)."""
    status = ERROR_STATUSES[ErrorCode(code)]
    payload = ErrorEnvelope(code=code, message=message).model_dump()
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class CapBodyMiddleware:
    """Pure ASGI: reject /api/analyze bodies above the cap; keep the body in RAM.

    Two gates (SPEC §5 "cap while reading"): a Content-Length header above
    cap is rejected before the body stream is consumed further, and the body
    itself is read in chunks and discarded mid-flight if it exceeds the cap
    (covers chunked uploads that carry no Content-Length). Accepted bodies
    are replayed to the app from memory, so nothing below the cap spools.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/analyze"):
            await self.app(scope, receive, send)
            return

        content_length = next(
            (value for key, value in scope["headers"] if key == b"content-length"),
            None,
        )
        if content_length is not None and int(content_length) > _BODY_CAP:
            await _send_envelope(send, "too_large", _TOO_LARGE_MESSAGE)
            return

        raw: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return  # client disconnected before finishing
            body = message.get("body", b"")
            total += len(body)
            if total > _BODY_CAP:
                await _send_envelope(send, "too_large", _TOO_LARGE_MESSAGE)
                return
            raw.append(body)
            if not message.get("more_body", False):
                break

        accumulator = _ReplayReceive(raw, receive)
        await self.app(scope, accumulator, send)


class _ReplayReceive:
    """Replay a fully-read request body to the app as ASGI receive messages."""

    def __init__(self, chunks: list[bytes], receive: Receive) -> None:
        self._messages: list[Message] = []
        for index, chunk in enumerate(chunks):
            self._messages.append(
                {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": index < len(chunks) - 1,
                }
            )
        self._index = 0
        self._receive = receive

    async def __call__(self) -> Message:
        if self._index < len(self._messages):
            message = self._messages[self._index]
            self._index += 1
            return message
        return await self._receive()


def _log_result(result: str, filename: str, size_bytes: int, duration_ms: int) -> None:
    """The one per-request log line: metadata only, never document text."""
    _LOG.info(
        "result=%s filename=%s size_bytes=%d duration_ms=%d",
        result,
        filename,
        size_bytes,
        duration_ms,
    )


def create_app(extractor: Extractor | None = None) -> FastAPI:
    """Build a fresh app; `extractor` is the one used by /api/analyze.

    api.py does not import adapters: main.build_app() injects the
    SignatureRoutedExtractor; tests inject fakes.
    """
    resolved_extractor = extractor

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Day 2 wiring note: the dictionary load will join here on Day 5.
        yield

    app = FastAPI(title="ats-scanner", lifespan=lifespan)
    app.add_middleware(CapBodyMiddleware)

    @app.middleware("http")
    async def _api_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        if "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]
        return response

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=ERROR_STATUSES[exc.code],
            content=ErrorEnvelope(code=exc.code.value, message=exc.message).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=ERROR_STATUSES[ErrorCode.INVALID_REQUEST],
            content=ErrorEnvelope(
                code=ErrorCode.INVALID_REQUEST.value, message=_VALIDATION_MESSAGE
            ).model_dump(),
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

    @app.post("/api/analyze", response_model=AnalysisReport)
    def _analyze(
        resume: UploadFile = File(...),  # noqa: B008 - the FastAPI dependency idiom
    ) -> AnalysisReport:
        """Extract text from the uploaded resume (sync: runs in a threadpool)."""
        started = time.perf_counter()
        filename = resume.filename or ""
        try:
            if resolved_extractor is None:
                raise RuntimeError("create_app(expected an injected Extractor)")
            data = resume.file.read()
            size_bytes = len(data)
            content_type = resume.content_type or ""
            document = resolved_extractor.extract(data, filename, content_type)
            pipeline = analyze_pipeline(document)
            duration_ms = int((time.perf_counter() - started) * 1000)
            report = AnalysisReport(
                schema_version=SCHEMA_VERSION,
                engine_version=ENGINE_VERSION,
                dictionary_version=DICTIONARY_VERSION,
                meta=ReportMeta(
                    filename=filename,
                    size_bytes=size_bytes,
                    page_count=len(document.pages),
                    method=document.method,
                    duration_ms=duration_ms,
                    warnings=document.warnings,
                ),
                extracted_text=ExtractedText(
                    pages=tuple(
                        ExtractedTextPage(
                            page_number=page.page_number,
                            row_text=page.row_text,
                            column_text=page.column_text,
                        )
                        for page in document.pages
                    ),
                    char_count=document.char_count,
                    method=document.method,
                    warnings=document.warnings,
                ),
                reading_order=pipeline.reading_order,
                sections=pipeline.sections,
                contact=pipeline.contact,
            )
            _log_result("ok", filename, size_bytes, duration_ms)
            return report
        except AppError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            _log_result(exc.code.value, filename, resume.size or 0, duration_ms)
            raise

    return app
