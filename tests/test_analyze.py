"""POST /api/analyze: file-only multipart today, JD joins on Day 5.

Covers the response shape, DI of the Extractor, privacy (no disk writes for
uploads up to MAX_FILE_BYTES), oversize rejection, and log hygiene.
"""

import builtins
import io
import logging
import random
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from ats_scanner.adapters.extract import SignatureRoutedExtractor
from ats_scanner.api import create_app
from ats_scanner.config import DICTIONARY_VERSION, ENGINE_VERSION, MAX_FILE_BYTES
from ats_scanner.core.documents import ExtractedDocument, ExtractedPage
from ats_scanner.core.errors import AppError
from ats_scanner.core.ports import Extractor
from ats_scanner.core.report import SCHEMA_VERSION

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "resumes"
PDF_FIXTURE = FIXTURE_DIR / "resume_simple.pdf"
DOCX_FIXTURE = FIXTURE_DIR / "resume_simple.docx"

_PDF_DOCUMENT_TEXT = "Alex Example"  # never allowed in logs


def client_for(extractor: Extractor | None = None) -> TestClient:
    return TestClient(create_app(extractor))


def post_resume(client: TestClient, data: bytes, filename: str, content_type: str) -> Response:
    return client.post(
        "/api/analyze",
        files={"resume": (filename, data, content_type)},
    )


class SpyExtractor:
    """Counts calls so tests can prove a request never reached extraction."""

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, data: bytes, filename: str, content_type: str) -> ExtractedDocument:
        self.calls += 1
        return ExtractedDocument(
            pages=(ExtractedPage(page_number=1, row_text=_PDF_DOCUMENT_TEXT),),
            method="fake",
        )


def test_analyze_returns_report_for_the_pdf_fixture() -> None:
    client = client_for(SignatureRoutedExtractor())
    response = post_resume(client, PDF_FIXTURE.read_bytes(), "resume_simple.pdf", "application/pdf")
    assert response.status_code == 200
    report: dict[str, Any] = response.json()
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["engine_version"] == ENGINE_VERSION
    assert report["dictionary_version"] == DICTIONARY_VERSION
    meta = report["meta"]
    assert meta["filename"] == "resume_simple.pdf"
    assert meta["size_bytes"] == PDF_FIXTURE.stat().st_size
    assert meta["page_count"] == 1
    assert meta["method"] == "pdfplumber"
    assert meta["duration_ms"] >= 0
    extracted = report["extracted_text"]
    assert extracted["method"] == "pdfplumber"
    assert extracted["char_count"] == len(extracted["pages"][0]["row_text"])
    assert extracted["pages"][0]["page_number"] == 1
    assert extracted["pages"][0]["column_text"] is None


def test_analyze_returns_report_for_the_docx_fixture() -> None:
    client = client_for(SignatureRoutedExtractor())
    response = post_resume(
        client, DOCX_FIXTURE.read_bytes(), "resume_simple.docx", "application/octet-stream"
    )
    assert response.status_code == 200
    extracted = response.json()["extracted_text"]
    assert extracted["method"] == "python-docx"
    assert "Alex Example" in extracted["pages"][0]["row_text"]


def test_signature_decides_not_filename_or_content_type() -> None:
    client = client_for(SignatureRoutedExtractor())
    response = post_resume(client, PDF_FIXTURE.read_bytes(), "resume.txt", "text/plain")
    assert response.status_code == 200
    assert response.json()["extracted_text"]["method"] == "pdfplumber"


def test_analyze_errors_come_back_in_one_envelope() -> None:
    client = client_for(SignatureRoutedExtractor())
    cases = [
        (b"plain text bytes", "file.pdf", "text/plain", 415, "unsupported_type"),
        (b"%PDF-1.7\nnot a pdf", "file.pdf", "application/pdf", 422, "bad_pdf"),
        (b"PK\x03\x04" + b"\x00" * 100, "file.docx", "application/octet-stream", 422, "bad_docx"),
    ]
    for data, filename, content_type, status, code in cases:
        response = post_resume(client, data, filename, content_type)
        assert response.status_code == status, code
        body: dict[str, str] = response.json()
        assert set(body) == {"code", "message"}, code
        assert body["code"] == code, code


def test_missing_resume_field_is_invalid_request() -> None:
    client = client_for(SignatureRoutedExtractor())
    response = client.post("/api/analyze")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_cache_control_no_store_on_analyze() -> None:
    client = client_for(SpyExtractor())
    response = post_resume(client, b"anything", "f.pdf", "application/pdf")
    assert response.headers["cache-control"] == "no-store"


def test_injected_fake_extractor_is_the_one_used() -> None:
    spy = SpyExtractor()
    client = client_for(spy)
    response = post_resume(client, b"anything", "f.pdf", "application/pdf")
    assert response.status_code == 200
    assert spy.calls == 1
    assert response.json()["extracted_text"]["method"] == "fake"
    assert response.json()["meta"]["method"] == "fake"


def test_oversize_content_length_is_rejected_before_parsing() -> None:
    spy = SpyExtractor()
    client = client_for(spy)
    big = random.Random(1).randbytes(MAX_FILE_BYTES + 65_536 + 1)
    response = post_resume(client, big, "big.bin", "application/octet-stream")
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"
    assert spy.calls == 0


def _multipart_body(payload: bytes, boundary: str = "atsboundary123456") -> bytes:
    return (
        f"--{boundary}\r\n".encode("ascii")
        + b'Content-Disposition: form-data; name="resume"; filename="x.bin"\r\n'
        + b"Content-Type: application/octet-stream\r\n\r\n"
        + payload
        + f"\r\n--{boundary}--\r\n".encode("ascii")
    )


def test_oversize_body_without_content_length_is_capped_while_reading() -> None:
    spy = SpyExtractor()
    client = client_for(spy)
    big = random.Random(2).randbytes(MAX_FILE_BYTES + 65_536 + 1)
    body = _multipart_body(big)
    response = client.post(
        "/api/analyze",
        content=iter([body]),  # no Content-Length: chunked transfer encoding
        headers={"Content-Type": "multipart/form-data; boundary=atsboundary123456"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "too_large"
    assert spy.calls == 0


def make_docx_with_padding() -> bytes:
    """The DOCX fixture plus one ~2 MB incompressible extra entry."""
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(DOCX_FIXTURE.read_bytes())) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries["py.bin"] = random.Random(7).randbytes(2 * 1024 * 1024)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_upload_up_to_max_stays_in_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """~2 MB upload succeeds with tempfile creation and open-for-write banned."""
    data = make_docx_with_padding()
    assert len(data) < MAX_FILE_BYTES

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("uploads must never touch the filesystem")

    def refuse_writes(path: object, mode: str = "r", *args: object, **kwargs: object) -> object:
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            raise AssertionError(f"write-mode open forbidden: {mode}")
        raise AssertionError("no file opens expected during an upload")

    monkeypatch.setattr(tempfile, "TemporaryFile", refuse, raising=False)
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", refuse, raising=False)
    monkeypatch.setattr(tempfile, "mkstemp", refuse, raising=False)
    monkeypatch.setattr(tempfile, "mkdtemp", refuse, raising=False)
    monkeypatch.setattr(builtins, "open", refuse_writes, raising=False)

    client = client_for(SignatureRoutedExtractor())
    response = post_resume(client, data, "padded.docx", "application/octet-stream")
    assert response.status_code == 200
    assert response.json()["extracted_text"]["char_count"] > 0


def test_logs_carry_metadata_only(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ats_scanner.api")
    client = client_for(SignatureRoutedExtractor())

    success = post_resume(client, PDF_FIXTURE.read_bytes(), "resume_simple.pdf", "application/pdf")
    assert success.status_code == 200
    failure = post_resume(client, b"some plain text", "x.pdf", "text/plain")
    assert failure.status_code == 415

    messages = [record.getMessage() for record in caplog.records]
    assert any("result=ok" in message for message in messages)
    assert any("result=unsupported_type" in message for message in messages)
    joined = "\n".join(messages)
    assert _PDF_DOCUMENT_TEXT not in joined
    for message in messages:
        assert "result=" in message
        assert "duration_ms=" in message
        assert "size_bytes=" in message
        assert "filename=" in message


def test_log_error_lines_carry_the_code_not_the_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class TextEchoExtractor:
        def extract(self, data: bytes, filename: str, content_type: str) -> ExtractedDocument:
            del filename, content_type
            raise AppError("no_extractable_text", "The document has no text.")

    caplog.set_level(logging.INFO, logger="ats_scanner.api")
    client = client_for(TextEchoExtractor())
    response = post_resume(client, b"PADDED PAYLOAD TEXT", "x.pdf", "text/plain")
    assert response.status_code == 422
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert "PADDED PAYLOAD TEXT" not in joined
    assert "result=no_extractable_text" in joined
