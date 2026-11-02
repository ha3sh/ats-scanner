"""Pydantic report models: the API response contract (SPEC §5 report shape).

v1 for today's step: schema/versions, meta, and the extracted text the
"What the ATS sees" tab shows. Later days extend with verdict, score,
terms, findings, alignment, suggestions, disclaimers.
"""

from pydantic import BaseModel, ConfigDict, Field

from ats_scanner.core.documents import ExtractionWarning

SCHEMA_VERSION: int = 1


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


class AnalysisReport(BaseModel):
    """The response of POST /api/analyze; grows with the pipeline."""

    model_config = ConfigDict(frozen=True)

    schema_version: int
    engine_version: str
    dictionary_version: int
    meta: ReportMeta
    extracted_text: ExtractedText
