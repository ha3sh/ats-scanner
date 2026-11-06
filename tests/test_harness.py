"""tests/harness.py: the fixture evaluation harness (ROADMAP Day 4).

Meta-tests pin `check` behaviour: a matching subset passes, a mismatch
fails with a readable message, unknown keys and unknown section/contact
names fail loudly, unmentioned keys are ignored, and error expectations
behave (match, mismatch, success-where-error-expected, error-must-be-
alone). One parametrized test runs every .pdf/.docx fixture in
tests/fixtures/resumes/ against its `name.ext.expected.json` subset and
fails when either side is missing.
"""

import json
from pathlib import Path

import pytest

from ats_scanner.core.dictionary import SkillCategory
from ats_scanner.core.jd import BlockKind, CleanedJd, KeptBlock, RemovalReason, RemovedBlock
from ats_scanner.core.terms import JdTerm
from harness import FixtureFacts, JdFacts, check, check_jd, run_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "resumes"

OK_FACTS = FixtureFacts(
    error=None,
    reading_order=("row",),
    sections_found=frozenset({"contact", "summary"}),
    sections_missing=frozenset({"projects"}),
    contact={"email": True, "phone": False, "linkedin": False},
    warning_codes=frozenset(),
)

ERROR_FACTS = FixtureFacts(
    error="bad_pdf",
    reading_order=(),
    sections_found=frozenset(),
    sections_missing=frozenset(),
    contact={},
    warning_codes=frozenset(),
)


def test_check_passes_on_a_matching_subset() -> None:
    assert check({"sections_found": ["contact"], "reading_order": ["row"]}, OK_FACTS) == []


def test_check_reports_a_mismatch_readably() -> None:
    messages = check({"reading_order": ["column"]}, OK_FACTS)
    assert len(messages) == 1
    assert "column" in messages[0] and "row" in messages[0]


def test_check_fails_loudly_on_unknown_keys() -> None:
    messages = check({"score": 99}, OK_FACTS)
    assert len(messages) == 1
    assert "score" in messages[0]


def test_check_ignores_keys_that_are_not_mentioned() -> None:
    assert check({}, OK_FACTS) == []


def test_check_fails_on_unknown_section_names() -> None:
    messages = check({"sections_found": ["nosuch"]}, OK_FACTS)
    assert len(messages) == 1
    assert "nosuch" in messages[0]


def test_check_fails_on_unknown_contact_keys() -> None:
    messages = check({"contact": {"fax": True}}, OK_FACTS)
    assert len(messages) == 1
    assert "fax" in messages[0]


def test_check_reports_a_wrong_contact_flag() -> None:
    messages = check({"contact": {"email": False}}, OK_FACTS)
    assert len(messages) == 1
    assert "email" in messages[0]


def test_check_reports_an_unexpectedly_found_section() -> None:
    messages = check({"sections_missing": ["summary"]}, OK_FACTS)
    assert len(messages) == 1
    assert "summary" in messages[0]


def test_warning_codes_compare_as_sets() -> None:
    facts = FixtureFacts(
        error=None,
        reading_order=("column",),
        sections_found=frozenset(),
        sections_missing=frozenset(),
        contact={},
        warning_codes=frozenset({"columns_suspected"}),
    )
    assert check({"warning_codes": ["columns_suspected"]}, facts) == []
    messages = check({"warning_codes": []}, facts)
    assert len(messages) == 1
    assert "columns_suspected" in messages[0]


def test_error_expectation_matches() -> None:
    assert check({"error": "bad_pdf"}, ERROR_FACTS) == []


def test_error_expectation_mismatch_is_readable() -> None:
    messages = check({"error": "unsupported_type"}, ERROR_FACTS)
    assert len(messages) == 1
    assert "unsupported_type" in messages[0] and "bad_pdf" in messages[0]


def test_error_expectation_against_a_successful_run_fails() -> None:
    messages = check({"error": "bad_pdf"}, OK_FACTS)
    assert len(messages) == 1
    assert "succeeded" in messages[0]


def test_error_must_be_the_only_key() -> None:
    messages = check({"error": "bad_pdf", "reading_order": ["row"]}, ERROR_FACTS)
    assert len(messages) == 1
    assert "only" in messages[0]


JD_CLEANED = CleanedJd(
    kept=(
        KeptBlock(text="intro", start_line=1, kind=BlockKind.OTHER),
        KeptBlock(text="- Python", start_line=3, kind=BlockKind.REQUIREMENTS),
    ),
    removed=(RemovedBlock(text="- PTO", start_line=5, reason=RemovalReason.BENEFITS),),
)

JD_TERMS = (
    JdTerm(
        canonical="Python",
        category=SkillCategory.LANGUAGE,
        weight=2.0,
        required=True,
        occurrences=1,
        surface="Python",
        line=3,
        context="- Python",
    ),
)

JD_FACTS = JdFacts(cleaned=JD_CLEANED, terms=JD_TERMS)


def test_check_jd_passes_on_a_matching_subset() -> None:
    expected = {
        "kept": [{"start_line": 1, "kind": "other"}, {"start_line": 3}],
        "removed": [{"start_line": 5, "reason": "benefits"}],
    }
    assert check_jd(expected, JD_FACTS) == []


def test_check_jd_reports_a_mismatch_readably() -> None:
    expected: dict[str, object] = {
        "kept": [{"start_line": 1, "kind": "other"}, {"start_line": 3, "kind": "other"}],
    }
    messages = check_jd(expected, JD_FACTS)
    assert len(messages) == 1
    assert "requirements" in messages[0]


def test_check_jd_fails_loudly_on_unknown_keys() -> None:
    messages = check_jd({"score": 1}, JD_FACTS)
    assert len(messages) == 1
    assert "score" in messages[0]


def test_check_jd_fails_on_unknown_keys_inside_entries() -> None:
    messages = check_jd({"kept": [{"start_line": 1, "text": "intro"}]}, JD_FACTS)
    assert len(messages) == 1
    assert "text" in messages[0]


def test_check_jd_ignores_unmentioned_lists() -> None:
    assert check_jd({}, JD_FACTS) == []


def test_check_jd_reports_a_block_count_mismatch() -> None:
    messages = check_jd({"removed": []}, JD_FACTS)
    assert len(messages) == 1
    assert "0 blocks" in messages[0]


def test_check_jd_terms_subset_passes() -> None:
    assert check_jd({"terms": [{"canonical": "Python", "weight": 2.0}]}, JD_FACTS) == []


def test_check_jd_terms_reports_a_missing_term() -> None:
    messages = check_jd({"terms": [{"canonical": "SQL"}]}, JD_FACTS)
    assert len(messages) == 1
    assert "SQL" in messages[0]


def test_check_jd_terms_reports_a_weight_mismatch() -> None:
    messages = check_jd({"terms": [{"canonical": "Python", "weight": 1.0}]}, JD_FACTS)
    assert len(messages) == 1
    assert "1.0" in messages[0] and "2.0" in messages[0]


def test_check_jd_terms_fails_on_unknown_keys_inside_entries() -> None:
    messages = check_jd({"terms": [{"canonical": "Python", "line": 3}]}, JD_FACTS)
    assert len(messages) == 1
    assert "line" in messages[0]


def test_check_jd_absent_terms_pass_and_fail() -> None:
    assert check_jd({"absent_terms": ["SQL"]}, JD_FACTS) == []
    messages = check_jd({"absent_terms": ["Python"]}, JD_FACTS)
    assert len(messages) == 1
    assert "Python" in messages[0]


FIXTURE_NAMES = sorted(
    {
        *(path.name for path in FIXTURES.iterdir() if path.suffix in {".pdf", ".docx"}),
        *(path.name.removesuffix(".expected.json") for path in FIXTURES.glob("*.expected.json")),
    }
)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_every_fixture_matches_its_expected_subset(name: str) -> None:
    fixture = FIXTURES / name
    expected_path = FIXTURES / f"{name}.expected.json"
    assert fixture.exists(), f"{expected_path.name} has no fixture file beside it"
    assert expected_path.exists(), f"{fixture.name} has no {fixture.name}.expected.json"
    facts = run_fixture(fixture)
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    messages = check(expected, facts)
    assert not messages, "\n".join(messages)
