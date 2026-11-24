"""Weighted JD term coverage (pure; SPEC §3 formula).

This module computes coverage and nothing else: no alignment, no findings,
no layout heuristics. Weights are exposed as exact sums — the frontend does
the division for display, but the report carries the numerator and the
denominator unrounded so every percentage is auditable.

Required terms (weight 2.0) and other/preferred terms (weight 1.0) have
their own exact numerator and denominator. Near misses live in
`TermAnalysis.near_misses` and are deliberately absent from every sum.
"""

from ats_scanner.core.report import CoveragePart, CoverageScore, TermAnalysis
from ats_scanner.core.terms import REQUIRED_WEIGHT

DEFINITION = "coverage = sum(weight(matched terms)) / sum(weight(all terms))"


def score_coverage(analysis: TermAnalysis) -> CoverageScore:
    """Return exact weighted sums and the derived integer percentage."""
    covered_required = sum(
        item.weight for item in analysis.matched if item.weight == REQUIRED_WEIGHT
    )
    covered_other = sum(item.weight for item in analysis.matched if item.weight != REQUIRED_WEIGHT)
    total_required = sum(item.weight for item in analysis.missing if item.weight == REQUIRED_WEIGHT)
    total_other = sum(item.weight for item in analysis.missing if item.weight != REQUIRED_WEIGHT)
    covered = covered_required + covered_other
    total = covered + total_required + total_other
    pct = round(100 * covered / total) if total else 0
    return CoverageScore(
        covered_weight=covered,
        total_weight=total,
        pct=pct,
        required=CoveragePart(covered=covered_required, total=covered_required + total_required),
        other=CoveragePart(covered=covered_other, total=covered_other + total_other),
        definition=DEFINITION,
        state="terms" if total else "no_terms",
    )
