"""core/alignment.py: informational title, seniority and experience checks.

Each check has three honest states (aligned / differs / unknown), evidence on
both sides, and no effect whatsoever on weighted coverage. Tests pin the
three states per check, messy real-world spellings, open date ranges, the
"bare years are not experience claims" rule, determinism and score isolation.
"""

from ats_scanner.core.alignment import check_alignment
from ats_scanner.core.dictionary import Dictionary, SkillCategory, SkillEntry, build_index
from ats_scanner.core.documents import ExtractedDocument, ExtractedPage
from ats_scanner.core.jd import clean_jd
from ats_scanner.core.pipeline import analyze, analyze_jd, analyze_terms
from ats_scanner.core.report import Alignment, AlignmentCheck, AlignmentStatus
from ats_scanner.core.score import score_coverage
from ats_scanner.core.sections import find_sections


def check(jd_text: str, *resume_pages: str) -> Alignment:
    sections = find_sections(resume_pages)
    return check_alignment(clean_jd(jd_text), resume_pages, sections)


def status(value: AlignmentCheck) -> str:
    return value.status.value


# --- title ---


def test_title_aligned_after_normalizing_case_and_punctuation() -> None:
    result = check(
        "Data Engineer at Bluebird Analytics\n\nWe build reliable data pipelines.",
        "Sam Sample\nData Engineer\nsam@example.com\nPython and SQL",
    )
    assert status(result.title) == AlignmentStatus.ALIGNED.value
    assert result.title.jd_evidence.text == "Data Engineer at Bluebird Analytics"
    assert result.title.jd_evidence.line == 1
    assert result.title.resume_evidence.text == "Data Engineer"
    assert (result.title.resume_evidence.page, result.title.resume_evidence.line) == (1, 2)


def test_title_two_lines_abbreviation_and_level_suffix() -> None:
    result = check(
        "Sr. Software Engineer\nat Bluebird Analytics\n\nWe build products.",
        "Jamie Sample\nSoftware Engineer II\njamie@example.com\nPython",
    )
    assert status(result.title) == AlignmentStatus.ALIGNED.value
    assert result.title.jd_evidence.text == "Sr. Software Engineer at Bluebird Analytics"
    assert status(result.seniority) == AlignmentStatus.DIFFERS.value


def test_title_differs_when_both_sides_are_clear() -> None:
    result = check(
        "Frontend Engineer at Bluebird Analytics\n\nWe build dashboards.",
        "Sam Sample\nData Engineer\nsam@example.com\nPython",
    )
    assert status(result.title) == AlignmentStatus.DIFFERS.value


def test_title_unknown_without_a_role_signal() -> None:
    result = check(
        "An exciting opportunity at Bluebird Analytics\n\nWe build products.",
        "Sam Sample\nExperienced professional\nsam@example.com\nPython",
    )
    assert status(result.title) == AlignmentStatus.UNKNOWN.value
    assert result.title.jd_evidence.text is None
    assert result.title.resume_evidence.text is None


# --- seniority ---


def test_seniority_aligned_and_differs() -> None:
    aligned = check(
        "Senior Frontend Engineer at Acme\n\nWe build dashboards.",
        "Sam Sample\nSenior Data Engineer\nsam@example.com",
    )
    differs = check(
        "Senior Frontend Engineer at Acme\n\nWe build dashboards.",
        "Sam Sample\nJunior Data Engineer\nsam@example.com",
    )
    assert status(aligned.seniority) == AlignmentStatus.ALIGNED.value
    assert status(differs.seniority) == AlignmentStatus.DIFFERS.value


def test_seniority_unknown_on_one_side_or_ambiguous_cues() -> None:
    one_side = check(
        "Frontend Engineer at Acme\n\nWe build dashboards.",
        "Sam Sample\nSenior Data Engineer\nsam@example.com",
    )
    ambiguous = check(
        "Junior or Senior Engineer at Acme\n\nWe build dashboards.",
        "Sam Sample\nData Engineer\nsam@example.com",
    )
    assert status(one_side.seniority) == AlignmentStatus.UNKNOWN.value
    assert status(ambiguous.seniority) == AlignmentStatus.UNKNOWN.value


# --- experience ---


def test_experience_aligned_from_explicit_claims() -> None:
    result = check(
        "Frontend Engineer at Acme\n\nThree years of JavaScript required.",
        "Sam Sample\nData Engineer\nData engineer with six years of experience building pipelines",
    )
    assert status(result.experience) == AlignmentStatus.ALIGNED.value
    assert "six years" in (result.experience.resume_evidence.text or "")


def test_experience_differs_from_explicit_claims() -> None:
    result = check(
        "Frontend Engineer at Acme\n\nFive years of experience required.",
        "Sam Sample\nData Engineer\nTwo years of experience with Python",
    )
    assert status(result.experience) == AlignmentStatus.DIFFERS.value


def test_experience_range_and_word_numbers() -> None:
    included = check(
        "Frontend Engineer at Acme\n\n2-4 years of experience required.",
        "Sam Sample\nData Engineer\nThree years of experience with Python",
    )
    below = check(
        "Frontend Engineer at Acme\n\n2-4 years of experience required.",
        "Sam Sample\nData Engineer\nOne year of experience with Python",
    )
    assert status(included.experience) == AlignmentStatus.ALIGNED.value
    assert status(below.experience) == AlignmentStatus.DIFFERS.value


def test_open_range_uses_the_latest_year_in_the_resume_and_ignores_bare_years() -> None:
    result = check(
        "Frontend Engineer at Acme\n\nFive years of experience required.",
        "Sam Sample\nData Engineer\nExperience\nData Engineer, Acme\nApril 2020 - Present\n2013",
    )
    assert status(result.experience) == AlignmentStatus.DIFFERS.value
    assert "April 2020 - Present" in (result.experience.resume_evidence.text or "")


def test_bare_year_runs_are_not_experience_claims() -> None:
    result = check(
        "Frontend Engineer at Acme\n\nFive years of experience required.",
        "Sam Sample\nData Engineer\n2013\n2020",
    )
    assert status(result.experience) == AlignmentStatus.UNKNOWN.value
    assert result.experience.resume_evidence.text is None


def test_no_signal_means_unknown_on_all_checks() -> None:
    result = check(
        "An exciting opportunity at Acme\n\nWe make things.",
        "Sam Sample\nExperienced professional\nsam@example.com\nPython",
    )
    assert [status(value) for value in (result.title, result.seniority, result.experience)] == [
        AlignmentStatus.UNKNOWN.value
    ] * 3


def test_alignment_is_deterministic() -> None:
    jd_text = "Senior Frontend Engineer at Acme\n\nThree years of JavaScript required."
    resume = "Sam Sample\nSenior Software Engineer\nSix years of experience\nApril 2020 - Present"
    assert check(jd_text, resume) == check(jd_text, resume)


def test_alignment_never_changes_the_score() -> None:
    index = build_index(
        Dictionary(
            version=1,
            source="test",
            entries=(
                SkillEntry(canonical="JavaScript", category=SkillCategory.LANGUAGE),
                SkillEntry(canonical="REST", category=SkillCategory.PRACTICE),
            ),
        )
    )
    base = "\n\nRequirements:\n- Three years of JavaScript\n- Experience with REST APIs"
    junior_text = "Junior Data Engineer at Acme\n\nWe build pipelines." + base
    senior_text = "Principal Frontend Engineer at Acme\n\nWe build dashboards." + base
    resume = "Sam Sample\nJunior Data Engineer\nOne year of experience"
    sections = find_sections((resume,))
    document = ExtractedDocument(
        pages=(ExtractedPage(page_number=1, row_text=resume),), method="test"
    )
    pipeline = analyze(document, index)
    junior_jd = analyze_jd(junior_text, index)
    senior_jd = analyze_jd(senior_text, index)
    junior_terms, junior_score = analyze_terms(junior_jd.terms, pipeline, index)
    senior_terms, senior_score = analyze_terms(senior_jd.terms, pipeline, index)
    junior_alignment = check_alignment(clean_jd(junior_text), (resume,), sections)
    senior_alignment = check_alignment(clean_jd(senior_text), (resume,), sections)
    assert junior_alignment != senior_alignment
    assert junior_score == senior_score
    assert junior_terms == senior_terms
    assert score_coverage(junior_terms) == score_coverage(senior_terms)
