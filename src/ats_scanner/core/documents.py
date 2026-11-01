"""Extracted-document model shared with adapters.

The one shape all downstream steps consume (SPEC §4 "Row order and column
order views"): not a PDF or DOCX object. Frozen so a page cannot be mutated
after extraction, and the character count is derived, never stored, so it
cannot drift from the text. Counts are Python `len`s — code points — so emoji
and other non-BMP characters count as one character, matching the
frontend's `Array.from` helper.
"""

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ExtractionWarning(BaseModel):
    """A layout note that is not a hard error."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    page: int | None = None
    """1-based page the warning applies to; None when it spans the file."""


class ExtractedPage(BaseModel):
    """One page in two possible reading orders."""

    model_config = ConfigDict(frozen=True)

    page_number: int = Field(ge=1)
    row_text: str
    """The raw document stream, line by line (SPEC §4 row order)."""
    column_text: str | None = None
    """Column-clustered order; the adapter fills it on Day 3."""


class ExtractedDocument(BaseModel):
    """The whole extracted document, plus method and warnings."""

    model_config = ConfigDict(frozen=True)

    pages: tuple[ExtractedPage, ...] = ()
    method: str = Field(min_length=1)
    warnings: tuple[ExtractionWarning, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def char_count(self) -> int:
        """Code points of the row-order text across all pages."""
        return sum(len(page.row_text) for page in self.pages)
