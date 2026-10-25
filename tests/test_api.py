"""API surface tests: health endpoint, headers, and the error envelope."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ats_scanner.api import ERROR_STATUSES, AppError, create_app
from ats_scanner.config import (
    APP_VERSION,
    DICTIONARY_VERSION,
    ENGINE_VERSION,
    MAX_FILE_BYTES,
    MAX_JD_CHARS,
    MAX_PAGES,
)


def test_health_reports_versions_and_limits() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "version": APP_VERSION,
        "engine_version": ENGINE_VERSION,
        "dictionary_version": DICTIONARY_VERSION,
        "limits": {
            "max_file_bytes": MAX_FILE_BYTES,
            "max_pages": MAX_PAGES,
            "max_jd_chars": MAX_JD_CHARS,
        },
    }


def test_every_error_code_maps_to_its_status_and_envelope() -> None:
    for code, status in sorted(ERROR_STATUSES.items()):
        app = create_app()

        def raise_code(c: str = code) -> None:
            raise AppError(c, f"boom: {c}")

        app.add_api_route("/boom", raise_code, methods=["GET"])
        client = TestClient(app)
        response = client.get("/boom")
        assert response.status_code == status, code
        assert response.json() == {"code": code, "message": f"boom: {code}"}


def test_unknown_error_code_is_rejected_by_the_setup() -> None:
    """AppError refuses codes outside SPEC §5, so the map stays exhaustive."""
    import pytest

    with pytest.raises(ValueError, match="not a SPEC error code"):
        AppError("not_a_code", "boom")


def test_request_validation_error_uses_the_envelope() -> None:
    app = create_app()

    def echo(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    app.add_api_route("/items/{item_id}", echo, methods=["GET"])
    client = TestClient(app)
    response = client.get("/items/not-an-int")
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == "invalid_request"
    assert isinstance(body["message"], str) and body["message"]


def test_api_responses_carry_no_store_and_no_powered_by() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.headers["cache-control"] == "no-store"
    assert "x-powered-by" not in response.headers


def test_error_responses_carry_the_headers_too() -> None:
    app = create_app()

    def raise_code() -> None:
        raise AppError("too_large", "boom")

    app.add_api_route("/api/boom", raise_code, methods=["GET"])
    client = TestClient(app)
    response = client.get("/api/boom")
    assert response.headers["cache-control"] == "no-store"
    assert "x-powered-by" not in response.headers


def test_create_app_returns_a_fresh_instance_each_call() -> None:
    first = create_app()
    second = create_app()
    assert isinstance(first, FastAPI)
    assert first is not second
