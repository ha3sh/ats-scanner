"""Regenerate tests/fixtures/report.sample.json (ROADMAP Day 4).

Usage: uv run python tests/update_sample.py

Runs resume_sidebar.pdf through the real /api/analyze endpoint with
TestClient and rewrites the golden sample, with meta.duration_ms stored
as 0 (the only non-deterministic field). The script does not inspect the
working tree — the diff is what the developer reviews.
"""

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from ats_scanner.adapters.extract import SignatureRoutedExtractor
from ats_scanner.api import create_app

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "resumes" / "resume_sidebar.pdf"
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "report.sample.json"


def main() -> None:
    client = TestClient(create_app(SignatureRoutedExtractor()))
    response = client.post(
        "/api/analyze",
        files={"resume": ("resume_sidebar.pdf", FIXTURE.read_bytes(), "application/pdf")},
    )
    if response.status_code != 200:
        raise SystemExit(f"/api/analyze failed: {response.status_code} {response.text}")
    report: dict[str, Any] = response.json()
    report["meta"]["duration_ms"] = 0
    SAMPLE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {SAMPLE} (meta.duration_ms stored as 0)")


if __name__ == "__main__":
    main()
