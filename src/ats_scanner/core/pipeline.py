"""The analysis pipeline (pure).

Over the extracted document it chooses the reading order per page —
column text when the page has it, else row text — and runs section and
contact detection over that text. Over the pasted JD it cleans boilerplate
blocks and extracts dictionary terms. api.py stays transport only and
calls these (SPEC §3, §4, §5).
"""

from pydantic import BaseModel, ConfigDict

from ats_scanner.core.contact import find_contact
from ats_scanner.core.dictionary import SkillEntry
from ats_scanner.core.documents import ExtractedDocument
from ats_scanner.core.jd import clean_jd
from ats_scanner.core.report import ContactInfo, JdAnalysis, ReadingOrder, SectionFinding
from ats_scanner.core.sections import find_sections
from ats_scanner.core.terms import extract_terms


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


def analyze_jd(jd_text: str, index: dict[str, SkillEntry]) -> JdAnalysis:
    """Clean the pasted JD and extract dictionary terms from kept blocks."""
    cleaned = clean_jd(jd_text)
    return JdAnalysis(cleaned=cleaned, terms=extract_terms(cleaned, index))
