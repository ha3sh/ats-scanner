"""Golden sample report: tests/fixtures/report.sample.json (ROADMAP Day 4).

The sample is the full /api/analyze JSON for resume_sidebar.pdf,
generated through the real endpoint with TestClient (synthetic data
only). The only non-deterministic field is meta.duration_ms: it is
stored as 0 and normalised before comparing. If a deliberate report
change breaks these tests, regenerate the sample with
`uv run python tests/update_sample.py` and review the diff.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ats_scanner.adapters.extract import SignatureRoutedExtractor
from ats_scanner.api import create_app
from ats_scanner.core.report import AnalysisReport

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "resumes" / "resume_sidebar.pdf"
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "report.sample.json"

_REGENERATE = (
    "The golden sample is out of date. If the report change is deliberate, "
    "regenerate it with `uv run python tests/update_sample.py` and review the diff."
)


def analyzed_json() -> dict[str, Any]:
    """One fresh analysis of resume_sidebar.pdf through the real endpoint."""
    client = TestClient(create_app(SignatureRoutedExtractor()))
    response = client.post(
        "/api/analyze",
        files={"resume": ("resume_sidebar.pdf", FIXTURE.read_bytes(), "application/pdf")},
    )
    assert response.status_code == 200
    report: dict[str, Any] = response.json()
    return report


def normalised(report: dict[str, Any]) -> dict[str, Any]:
    """Deep copy with meta.duration_ms forced to 0 before comparing."""
    normalised_report = copy.deepcopy(report)
    normalised_report["meta"]["duration_ms"] = 0
    return normalised_report


def sample_json() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(SAMPLE.read_text(encoding="utf-8"))
    return loaded


def test_sample_file_validates_against_the_report_model() -> None:
    try:
        report = AnalysisReport.model_validate(sample_json())
    except ValidationError as exc:
        pytest.fail(f"{_REGENERATE}\n\n{exc}")
    assert report.meta.filename == "resume_sidebar.pdf"


def test_fresh_analysis_matches_the_sample() -> None:
    fresh = normalised(analyzed_json())
    assert fresh == sample_json(), _REGENERATE


def test_two_runs_are_identical_after_normalising_duration() -> None:
    first = normalised(analyzed_json())
    second = normalised(analyzed_json())
    assert first == second, "the report is not deterministic between two identical requests"
