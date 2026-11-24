"""core/match.py: one dictionary matcher over resume text (pure; SPEC §3).

Covers exact, plural and alias matches, normalized line wraps and terms
split across a line break, exact_case false positives, page/line/char
spans, section attribution, near-miss guards, determinism and linear-time
behaviour on large input.
"""

import time

from ats_scanner.core.dictionary import Dictionary, SkillCategory, SkillEntry, build_index
from ats_scanner.core.match import ResumeMatch, match_resume, near_misses
from ats_scanner.core.report import NearMiss, SectionName
from ats_scanner.core.sections import find_sections
from ats_scanner.core.terms import JdTerm


def entry(
    canonical: str,
    *aliases: str,
    category: SkillCategory = SkillCategory.TOOL,
    exact_case: bool = False,
    ambiguous: bool = False,
) -> SkillEntry:
    return SkillEntry(
        canonical=canonical,
        aliases=aliases,
        category=category,
        exact_case=exact_case,
        ambiguous=ambiguous,
    )


TEST_INDEX = build_index(
    Dictionary(
        version=1,
        source="test",
        entries=(
            entry("Python", category=SkillCategory.LANGUAGE),
            entry("SQL", category=SkillCategory.LANGUAGE),
            entry("Go", category=SkillCategory.LANGUAGE, exact_case=True),
            entry("R", category=SkillCategory.LANGUAGE, exact_case=True),
            entry("C", category=SkillCategory.LANGUAGE, exact_case=True),
            entry("Docker", category=SkillCategory.DEVOPS),
            entry("PostgreSQL", "postgres", "pg", category=SkillCategory.DATABASE),
            entry("Kubernetes", "k8s", category=SkillCategory.DEVOPS),
            entry("React", "reactjs", category=SkillCategory.FRAMEWORK),
            entry("Java", category=SkillCategory.LANGUAGE),
            entry("JavaScript", "js", category=SkillCategory.LANGUAGE),
            entry(
                "REST",
                "rest api",
                "restful",
                category=SkillCategory.PRACTICE,
                ambiguous=True,
            ),
            entry("Machine Learning", "ml", category=SkillCategory.PRACTICE),
            entry("Fortran", category=SkillCategory.LANGUAGE, exact_case=True),
        ),
    )
)


def match_texts(*pages: str, index: dict[str, SkillEntry] = TEST_INDEX) -> tuple[ResumeMatch, ...]:
    sections = find_sections(pages)
    return match_resume(pages, sections, index)


def by_canonical(matches: tuple[ResumeMatch, ...], canonical: str) -> ResumeMatch:
    return next(match for match in matches if match.entry.canonical == canonical)


def jd_term(canonical: str, surface: str | None = None) -> JdTerm:
    return JdTerm(
        canonical=canonical,
        category=SkillCategory.TOOL,
        weight=2.0,
        required=True,
        occurrences=1,
        surface=surface or canonical,
        line=1,
        context=surface or canonical,
    )


def test_exact_match_carries_page_line_offsets_and_context() -> None:
    match = by_canonical(match_texts("Skills\nPython"), "Python")
    assert (match.page, match.line) == (1, 2)
    assert (match.start_char, match.end_char) == (7, 13)
    assert match.surface == "Python"
    assert match.context == "Python"
    assert match.section is None or match.section is SectionName.SKILLS


def test_section_attribution_uses_the_latest_heading() -> None:
    text = "Skills\nPython\n\nExperience\nData Engineer\nGo and SQL"
    matches = match_texts(text)
    assert by_canonical(matches, "Python").section is SectionName.SKILLS
    assert by_canonical(matches, "SQL").section is SectionName.EXPERIENCE
    assert by_canonical(matches, "Go").section is SectionName.EXPERIENCE


def test_plural_and_alias_matches() -> None:
    matches = match_texts("REST APIs, Docker containers, postgres and k8s")
    assert {"REST", "Docker", "PostgreSQL", "Kubernetes"} <= {
        match.entry.canonical for match in matches
    }
    rest = by_canonical(matches, "REST")
    assert rest.surface == "REST APIs"


def test_hyphenated_line_wrap_joins_the_word() -> None:
    match = by_canonical(match_texts("Built with Post-\ngreSQL"), "PostgreSQL")
    assert match.line == 1
    assert match.surface == "PostgreSQL"
    assert (match.start_char, match.end_char) == (11, 23)


def test_terms_split_across_a_line_break_match() -> None:
    match = by_canonical(match_texts("Machine\nLearning pipelines"), "Machine Learning")
    assert match.surface == "Machine Learning"
    assert match.line == 1
    assert (match.start_char, match.end_char) == (0, 16)


def test_exact_case_false_positives_do_not_count() -> None:
    matches = match_texts("Present to C-level execs with Python.\nWe plan R&D budgets.")
    canonicals = {match.entry.canonical for match in matches}
    assert "C" not in canonicals
    assert "R" not in canonicals
    assert "Python" in canonicals


def test_exact_case_still_matches_with_context() -> None:
    matches = match_texts("Experience with Go, R and Python.")
    assert {"Go", "R"} <= {match.entry.canonical for match in matches}


def test_matching_is_deterministic() -> None:
    text = "Python, SQL, Docker and REST APIs"
    assert match_texts(text) == match_texts(text)


def test_near_miss_is_reported_for_a_long_single_word() -> None:
    found = near_misses((jd_term("Docker"),), ("Dockr in production",), TEST_INDEX)
    assert found == (NearMiss(term="Docker", found_variant="Dockr", distance=1, counted=False),)


def test_short_words_never_produce_near_misses() -> None:
    assert near_misses((jd_term("React"),), ("Reach for the stars",), TEST_INDEX) == ()


def test_distance_two_is_allowed_only_from_ten_characters() -> None:
    assert near_misses((jd_term("Kubernetes"),), ("Kubernxxes",), TEST_INDEX) != ()
    assert near_misses((jd_term("Docker"),), ("Dockxx",), TEST_INDEX) == ()


def test_near_miss_skips_a_variant_that_is_another_dictionary_entry() -> None:
    index = build_index(
        Dictionary(
            version=1,
            source="test",
            entries=(
                entry("Kubernetes", category=SkillCategory.TOOL),
                entry("Kubernete", category=SkillCategory.TOOL),
            ),
        )
    )
    assert near_misses((jd_term("Kubernetes"),), ("Kubernete",), index) == ()


def test_near_miss_skips_exact_case_terms() -> None:
    assert near_misses((jd_term("Fortran"),), ("Fortrn",), TEST_INDEX) == ()


def test_large_input_stays_linear_enough() -> None:
    filler = "the team ships dashboards and reports for operators every week "
    text = filler * 2000 + " Python"
    started = time.perf_counter()
    matches = match_texts(text)
    elapsed = time.perf_counter() - started
    assert by_canonical(matches, "Python")
    assert elapsed < 5.0, f"matching took {elapsed:.2f}s"
