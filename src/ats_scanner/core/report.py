"""Pydantic report models: the API response contract (SPEC §5 report shape).

Grows with the pipeline: schema/versions, meta, extracted text, reading
order, sections, contact, the JD view (cleaned blocks and terms), matched
terms and weighted coverage. Later days add verdict, findings, alignment,
suggestions, disclaimers.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ats_scanner.core.documents import ExtractionWarning
from ats_scanner.core.jd import CleanedJd
from ats_scanner.core.terms import JdTerm

SCHEMA_VERSION: int = 1

ReadingOrder = Literal["row", "column"]


class SectionName(StrEnum):
    """The seven sections, in the fixed report order (SPEC §4)."""

    CONTACT = "contact"
    SUMMARY = "summary"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"


class ReportMeta(BaseModel):
    """One line about what was analyzed (and how long it took)."""

    model_config = ConfigDict(frozen=True)

    filename: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    page_count: int = Field(ge=1)
    method: str
    duration_ms: int = Field(ge=0)
    warnings: tuple[ExtractionWarning, ...] = ()


class ExtractedTextPage(BaseModel):
    """One page as the ATS tab renders it."""

    model_config = ConfigDict(frozen=True)

    page_number: int = Field(ge=1)
    row_text: str
    column_text: str | None = None


class ExtractedText(BaseModel):
    """Pages plus derived character count (documents.char_count semantics)."""

    model_config = ConfigDict(frozen=True)

    pages: tuple[ExtractedTextPage, ...]
    char_count: int = Field(ge=0)
    method: str
    warnings: tuple[ExtractionWarning, ...] = ()


class SectionFinding(BaseModel):
    """One of the seven sections, found or not (SPEC §4 "Sections detected")."""

    model_config = ConfigDict(frozen=True)

    name: SectionName
    found: bool
    heading: str | None = None
    """The exact heading line that triggered the match; None when absent."""
    page: int | None = Field(default=None, ge=1)
    line: int | None = Field(default=None, ge=1)
    """1-based line in the page's chosen reading order."""


class ContactItem(BaseModel):
    """One contact detail: found or not, with value and location."""

    model_config = ConfigDict(frozen=True)

    found: bool
    value: str | None = None
    page: int | None = Field(default=None, ge=1)
    line: int | None = Field(default=None, ge=1)


class ContactInfo(BaseModel):
    """Email, phone and LinkedIn, each independent."""

    model_config = ConfigDict(frozen=True)

    email: ContactItem
    phone: ContactItem
    linkedin: ContactItem


class JdAnalysis(BaseModel):
    """The pasted JD split into blocks plus the dictionary terms found."""

    model_config = ConfigDict(frozen=True)

    cleaned: CleanedJd
    terms: tuple[JdTerm, ...]


class ResumeSpan(BaseModel):
    """Where a matched term sits in the resume's chosen reading order.

    Char offsets are code-point offsets in the original page text (the
    same string the UI renders); the line is 1-based in that page. They
    point at the original surface, including a hyphenated line wrap.
    """

    model_config = ConfigDict(frozen=True)

    page: int = Field(ge=1)
    line: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    section: SectionName | None = None


class MatchedTerm(BaseModel):
    """A JD term found in the resume, with evidence on both sides (SPEC §5)."""

    model_config = ConfigDict(frozen=True)

    term: str = Field(min_length=1)
    """The JD surface form, e.g. "REST APIs"."""
    canonical: str = Field(min_length=1)
    weight: float
    jd_context: str
    resume_context: str
    resume_span: ResumeSpan


class MissingTerm(BaseModel):
    """A JD term with no resume match: term, weight and JD evidence."""

    model_config = ConfigDict(frozen=True)

    term: str = Field(min_length=1)
    weight: float
    jd_context: str


class NearMiss(BaseModel):
    """A close resume variant that is shown but NEVER counted (SPEC §3)."""

    model_config = ConfigDict(frozen=True)

    term: str = Field(min_length=1)
    found_variant: str = Field(min_length=1)
    distance: int = Field(ge=1)
    counted: Literal[False] = False


class TermAnalysis(BaseModel):
    """The explainable denominator: every JD term plus near misses."""

    model_config = ConfigDict(frozen=True)

    matched: tuple[MatchedTerm, ...]
    missing: tuple[MissingTerm, ...]
    near_misses: tuple[NearMiss, ...]


class CoveragePart(BaseModel):
    """One class's exact weight sums: no rounding, no division."""

    model_config = ConfigDict(frozen=True)

    covered: float = Field(ge=0)
    total: float = Field(ge=0)


class CoverageScore(BaseModel):
    """Weighted JD term coverage only; alignment is reported separately."""

    model_config = ConfigDict(frozen=True)

    covered_weight: float = Field(ge=0)
    total_weight: float = Field(ge=0)
    pct: int = Field(ge=0, le=100)
    required: CoveragePart
    other: CoveragePart
    definition: str
    state: Literal["terms", "no_terms"]


class AnalysisReport(BaseModel):
    """The response of POST /api/analyze; grows with the pipeline."""

    model_config = ConfigDict(frozen=True)

    schema_version: int
    engine_version: str
    dictionary_version: int
    meta: ReportMeta
    extracted_text: ExtractedText
    reading_order: tuple[ReadingOrder, ...]
    """Per page: "column" when the page has column text, else "row"."""
    sections: tuple[SectionFinding, ...]
    """Always all seven sections, fixed order (SPEC §4)."""
    contact: ContactInfo
    jd: JdAnalysis
    """The job description as pasted (cleaned blocks) and its terms."""
    terms: TermAnalysis
    """Matched, missing and near-miss terms, each with evidence."""
    score: CoverageScore
    """Weighted JD term coverage; numerator and denominator exposed exactly."""
