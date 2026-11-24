"""The analysis pipeline (pure).

Over the extracted document it chooses the reading order per page — column
text when the page has it, else row text — and runs section, contact and
term matching over that text. Over the pasted JD it cleans boilerplate
blocks and extracts dictionary terms. It then explains matched/missing terms
and computes weighted coverage. api.py stays transport only (SPEC §3–§5).
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from ats_scanner.core.alignment import check_alignment
from ats_scanner.core.contact import find_contact
from ats_scanner.core.dictionary import SkillEntry
from ats_scanner.core.documents import ExtractedDocument
from ats_scanner.core.jd import clean_jd
from ats_scanner.core.match import ResumeMatch, build_term_analysis, match_resume
from ats_scanner.core.report import (
    Alignment,
    ContactInfo,
    CoverageScore,
    JdAnalysis,
    ReadingOrder,
    SectionFinding,
    TermAnalysis,
)
from ats_scanner.core.score import score_coverage
from ats_scanner.core.sections import find_sections
from ats_scanner.core.terms import JdTerm, extract_terms


class PipelineResult(BaseModel):
    """Everything the pipeline derives beyond the extracted text."""

    model_config = ConfigDict(frozen=True)

    sections: tuple[SectionFinding, ...]
    contact: ContactInfo
    reading_order: tuple[ReadingOrder, ...]
    chosen: tuple[str, ...]
    """The per-page text actually read (column when present, else row)."""
    matches: tuple[ResumeMatch, ...]
    """Dictionary terms found in that text, with original-text spans."""


def analyze(document: ExtractedDocument, index: dict[str, SkillEntry]) -> PipelineResult:
    """Reading order, sections, contact and matched resume terms."""
    chosen: list[str] = []
    reading_order: list[ReadingOrder] = []
    for page in document.pages:
        if page.column_text is not None:
            chosen.append(page.column_text)
            reading_order.append("column")
        else:
            chosen.append(page.row_text)
            reading_order.append("row")
    contact = find_contact(chosen)
    contact_found = contact.email.found or contact.phone.found
    sections = find_sections(chosen, contact_found=contact_found)
    return PipelineResult(
        sections=sections,
        contact=contact,
        reading_order=tuple(reading_order),
        chosen=tuple(chosen),
        matches=match_resume(chosen, sections, index),
    )


def analyze_terms(
    terms: Sequence[JdTerm],
    pipeline: PipelineResult,
    index: dict[str, SkillEntry],
) -> tuple[TermAnalysis, CoverageScore]:
    """Explain every JD term and score only exact matches."""
    analysis = build_term_analysis(terms, pipeline.matches, pipeline.chosen, index)
    return analysis, score_coverage(analysis)


def analyze_alignment(jd: JdAnalysis, pipeline: PipelineResult) -> Alignment:
    """Informational comparison only; it never receives or changes a score."""
    return check_alignment(jd.cleaned, pipeline.chosen, pipeline.sections)


def analyze_jd(jd_text: str, index: dict[str, SkillEntry]) -> JdAnalysis:
    """Clean the pasted JD and extract dictionary terms from kept blocks."""
    cleaned = clean_jd(jd_text)
    return JdAnalysis(cleaned=cleaned, terms=extract_terms(cleaned, index))
