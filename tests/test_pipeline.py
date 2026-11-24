"""core/pipeline.py: reading order, sections and contact over the fixtures.

The pipeline chooses the reading order per page (column text when the
page has it, else row text) and feeds sections/contact detection. These
tests pin exact expectations for all four PDF/DOCX fixtures.
"""

from pathlib import Path

from ats_scanner.adapters.dictionary_loader import load_dictionary
from ats_scanner.adapters.extract import SignatureRoutedExtractor
from ats_scanner.core.dictionary import build_index
from ats_scanner.core.jd import BlockKind, RemovalReason
from ats_scanner.core.pipeline import PipelineResult, analyze, analyze_jd
from ats_scanner.core.report import SectionFinding, SectionName

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "resumes"
JD_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jds"


def analyze_fixture(name: str) -> PipelineResult:
    data = (FIXTURES / name).read_bytes()
    document = SignatureRoutedExtractor().extract(data, name, "application/octet-stream")
    return analyze(document)


def by_name(result: PipelineResult) -> dict[SectionName, SectionFinding]:
    return {finding.name: finding for finding in result.sections}


def test_analyze_jd_returns_the_cleaned_blocks_and_terms() -> None:
    text = (JD_FIXTURES / "jd_boilerplate.txt").read_text(encoding="utf-8")
    result = analyze_jd(text, build_index(load_dictionary()))
    assert [(block.start_line, block.kind) for block in result.cleaned.kept] == [
        (1, BlockKind.OTHER),
        (5, BlockKind.REQUIREMENTS),
        (9, BlockKind.RESPONSIBILITIES),
    ]
    assert [(block.start_line, block.reason) for block in result.cleaned.removed] == [
        (3, RemovalReason.EQUAL_OPPORTUNITY),
        (13, RemovalReason.BENEFITS),
        (17, RemovalReason.ABOUT_COMPANY),
        (20, RemovalReason.HOW_TO_APPLY),
    ]
    assert [(term.canonical, term.weight) for term in result.terms] == [
        ("Python", 2.0),
        ("SQL", 2.0),
    ]


def test_simple_pdf_row_order_sections_and_contact() -> None:
    result = analyze_fixture("resume_simple.pdf")
    assert result.reading_order == ("row",)
    sections = by_name(result)
    assert sections[SectionName.SUMMARY] == SectionFinding(
        name=SectionName.SUMMARY, found=True, heading="Summary", page=1, line=4
    )
    assert (sections[SectionName.EXPERIENCE].heading, sections[SectionName.EXPERIENCE].line) == (
        "Experience",
        7,
    )
    assert (sections[SectionName.EDUCATION].heading, sections[SectionName.EDUCATION].line) == (
        "Education",
        19,
    )
    assert (sections[SectionName.SKILLS].heading, sections[SectionName.SKILLS].line) == (
        "Skills",
        22,
    )
    assert not sections[SectionName.PROJECTS].found
    assert not sections[SectionName.CERTIFICATIONS].found
    assert sections[SectionName.CONTACT].found
    assert sections[SectionName.CONTACT].heading is None
    assert result.contact.email.value == "alex@example.com"
    assert result.contact.phone.value == "(555) 555-0100"
    assert (result.contact.email.page, result.contact.email.line) == (1, 3)
    assert not result.contact.linkedin.found


def test_simple_docx_row_order_sections_and_contact() -> None:
    result = analyze_fixture("resume_simple.docx")
    assert result.reading_order == ("row",)
    sections = by_name(result)
    assert sections[SectionName.SUMMARY].line == 4
    assert sections[SectionName.EXPERIENCE].line == 6
    assert sections[SectionName.EDUCATION].line == 18
    assert sections[SectionName.SKILLS].line == 21
    assert not sections[SectionName.PROJECTS].found
    assert not sections[SectionName.CERTIFICATIONS].found
    assert result.contact.email.value == "alex@example.com"
    assert result.contact.phone.found


def test_two_column_pdf_reads_column_order() -> None:
    result = analyze_fixture("resume_two_column.pdf")
    assert result.reading_order == ("column",)
    sections = by_name(result)
    for name, line in (
        (SectionName.SKILLS, 5),
        (SectionName.EDUCATION, 10),
        (SectionName.CERTIFICATIONS, 14),
        (SectionName.SUMMARY, 22),
        (SectionName.EXPERIENCE, 26),
    ):
        assert sections[name].found, name
        assert sections[name].page == 1
        assert sections[name].line == line, name
    assert not sections[SectionName.PROJECTS].found
    assert result.contact.email.value == "sam@example.com"
    assert result.contact.phone.value == "(555) 555-0142"
    assert (result.contact.email.page, result.contact.email.line) == (1, 3)


def test_sidebar_pdf_reads_column_order() -> None:
    result = analyze_fixture("resume_sidebar.pdf")
    assert result.reading_order == ("column",)
    sections = by_name(result)
    for name, line in (
        (SectionName.SKILLS, 5),
        (SectionName.EDUCATION, 10),
        (SectionName.CERTIFICATIONS, 14),
        (SectionName.SUMMARY, 22),
        (SectionName.EXPERIENCE, 26),
    ):
        assert sections[name].found, name
        assert sections[name].line == line, name
    assert not sections[SectionName.PROJECTS].found
    assert result.contact.email.value == "sam@example.com"
    assert result.contact.phone.value == "(555) 555-0142"
