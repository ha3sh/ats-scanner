"""The analysis pipeline over an extracted document (pure).

Chooses the reading order per page — column text when the page has it,
else row text — and runs section and contact detection over that text.
api.py stays transport only and calls this (SPEC §4, §5).
"""

from pydantic import BaseModel, ConfigDict

from ats_scanner.core.contact import find_contact
from ats_scanner.core.documents import ExtractedDocument
from ats_scanner.core.report import ContactInfo, ReadingOrder, SectionFinding
from ats_scanner.core.sections import find_sections


class PipelineResult(BaseModel):
    """Everything the pipeline derives beyond the extracted text."""

    model_config = ConfigDict(frozen=True)

    sections: tuple[SectionFinding, ...]
    contact: ContactInfo
    reading_order: tuple[ReadingOrder, ...]


def analyze(document: ExtractedDocument) -> PipelineResult:
    """Sections, contact and the per-page reading order."""
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
    return PipelineResult(
        sections=find_sections(chosen, contact_found=contact_found),
        contact=contact,
        reading_order=tuple(reading_order),
    )
