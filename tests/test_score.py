"""core/score.py: weighted coverage, exact numerators and invariants (SPEC §3).

The score is deliberately small: no rounding of weights, no alignment, no
near-miss credit. Tests pin the exact numerator/denominator, the required and
other sub-coverages, the explicit zero-term state, and the invariants that make
the number trustworthy (determinism, order independence, monotonicity).
"""

from ats_scanner.core.dictionary import SkillCategory
from ats_scanner.core.report import (
    MatchedTerm,
    MissingTerm,
    NearMiss,
    ResumeSpan,
    SectionName,
    TermAnalysis,
)
from ats_scanner.core.score import score_coverage
from ats_scanner.core.terms import JdTerm


def jd_term(canonical: str, weight: float) -> JdTerm:
    return JdTerm(
        canonical=canonical,
        category=SkillCategory.TOOL,
        weight=weight,
        required=weight == 2.0,
        occurrences=1,
        surface=canonical,
        line=1,
        context=f"Requirements: {canonical}",
    )


def matched(term: JdTerm) -> MatchedTerm:
    return MatchedTerm(
        term=term.surface,
        canonical=term.canonical,
        weight=term.weight,
        jd_context=term.context,
        resume_context=f"Skills: {term.canonical}",
        resume_span=ResumeSpan(
            page=1, line=2, start_char=7, end_char=13, section=SectionName.SKILLS
        ),
    )


def missing(term: JdTerm) -> MissingTerm:
    return MissingTerm(term=term.surface, weight=term.weight, jd_context=term.context)


def analysis(matched_terms: tuple[MatchedTerm, ...], terms: tuple[JdTerm, ...]) -> TermAnalysis:
    matched_canonicals = {item.canonical for item in matched_terms}
    return TermAnalysis(
        matched=matched_terms,
        missing=tuple(missing(term) for term in terms if term.canonical not in matched_canonicals),
        near_misses=(),
    )


def test_exact_numerator_and_denominator() -> None:
    terms = (jd_term("JavaScript", 2.0), jd_term("REST", 2.0), jd_term("TypeScript", 1.0))
    score = score_coverage(analysis((matched(terms[0]),), terms))
    assert (score.covered_weight, score.total_weight) == (2.0, 5.0)
    assert score.pct == 40
    assert (score.required.covered, score.required.total) == (2.0, 4.0)
    assert (score.other.covered, score.other.total) == (0.0, 1.0)
    assert score.state == "terms"


def test_zero_overlap_scores_zero() -> None:
    terms = (jd_term("JavaScript", 2.0), jd_term("TypeScript", 1.0))
    score = score_coverage(analysis((), terms))
    assert (score.covered_weight, score.total_weight) == (0.0, 3.0)
    assert score.pct == 0


def test_full_overlap_scores_one() -> None:
    terms = (jd_term("JavaScript", 2.0), jd_term("TypeScript", 1.0))
    score = score_coverage(analysis(tuple(matched(term) for term in terms), terms))
    assert (score.covered_weight, score.total_weight) == (3.0, 3.0)
    assert score.pct == 100


def test_zero_jd_terms_has_no_division_and_an_explicit_state() -> None:
    score = score_coverage(analysis((), ()))
    assert (score.covered_weight, score.total_weight) == (0.0, 0.0)
    assert score.pct == 0
    assert score.state == "no_terms"
    assert (score.required.covered, score.required.total) == (0.0, 0.0)
    assert (score.other.covered, score.other.total) == (0.0, 0.0)


def test_determinism_and_order_independence() -> None:
    first = jd_term("JavaScript", 2.0)
    second = jd_term("TypeScript", 1.0)
    a = score_coverage(analysis((matched(first),), (first, second)))
    b = score_coverage(analysis((matched(first),), (second, first)))
    assert a == b
    assert a == score_coverage(analysis((matched(first),), (first, second)))


def test_adding_a_matched_term_never_lowers_the_score() -> None:
    first = jd_term("JavaScript", 2.0)
    second = jd_term("TypeScript", 1.0)
    before = score_coverage(analysis((matched(first),), (first, second)))
    after = score_coverage(analysis((matched(first), matched(second)), (first, second)))
    assert after.covered_weight >= before.covered_weight
    assert after.total_weight == before.total_weight


def test_a_near_miss_never_changes_the_score() -> None:
    term = jd_term("Docker", 2.0)
    without = score_coverage(analysis((), (term,)))
    near = NearMiss(term=term.surface, found_variant="Dockr", distance=1, counted=False)
    with_near = TermAnalysis(matched=(), missing=(missing(term),), near_misses=(near,))
    assert score_coverage(with_near) == without
    assert near.counted is False


def test_definition_is_visible_and_never_called_an_ats_score() -> None:
    score = score_coverage(analysis((), ()))
    assert "coverage" in score.definition.lower()
    assert "ATS score" not in score.definition
