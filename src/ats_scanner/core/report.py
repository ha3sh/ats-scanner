"""Pydantic report models: the API response contract (SPEC §5 report shape).

Grows with the pipeline: today schema/versions, meta, extracted text,
reading order, sections and contact. Later days add verdict, score,
terms, findings, alignment, suggestions, disclaimers.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ats_scanner.core.documents import ExtractionWarning

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
