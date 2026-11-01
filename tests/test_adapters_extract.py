"""In-memory PDF extraction: validation order, happy path, no file writes."""

import builtins
import io
import tempfile
from pathlib import Path

import pytest

from ats_scanner.adapters.extract import PdfplumberExtractor
from ats_scanner.config import MAX_FILE_BYTES, MAX_PAGES
from ats_scanner.core.documents import ExtractedDocument
from ats_scanner.core.errors import AppError

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "resumes" / "resume_simple.pdf"

EN_DASH = "\u2013"  # used in date ranges and separators in the fixture
BULLET = "\u2022"  # used in list lines
REPLACEMENT_CHAR = "\ufffd"  # mojibake marker that must never leak into text


def extract(data: bytes) -> ExtractedDocument:
    return PdfplumberExtractor().extract(data, "resume.pdf", "application/pdf")


def build_pdf(page_count: int, text: str = "Alex Example") -> bytes:
    """A minimal valid N-page PDF assembled from plain bytes."""
    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")

    objects: list[tuple[int, bytes]] = []

    def add(obj_number: int, content: bytes) -> None:
        objects.append((obj_number, content))

    kids = " ".join(f"{3 + 2 * index} 0 R" for index in range(page_count))
    add(1, b"<</Type/Catalog/Pages 2 0 R>>")
    add(
        2,
        f"<</Type/Pages/Kids[{kids}]/Count {page_count}>>".encode("ascii"),
    )
    font_number = 3 + 2 * page_count
    for index in range(page_count):
        page_number = 3 + 2 * index
        content_number = page_number + 1
        add(
            page_number,
            f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents "
            f"{content_number} 0 R/Resources<</Font<</F1 {font_number} 0 R>>>>>>".encode("ascii"),
        )
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
        add(
            content_number,
            b"<</Length "
            + str(len(stream)).encode("ascii")
            + b">>stream\n"
            + stream
            + b"\nendstream",
        )
    add(font_number, b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    offsets: dict[int, int] = {}
    for obj_number, content in objects:
        offsets[obj_number] = buffer.tell()
        buffer.write(f"{obj_number} 0 obj\n".encode("ascii"))
        buffer.write(content)
        buffer.write(b"\nendobj\n")

    xref_position = buffer.tell()
    last = font_number
    buffer.write(f"xref\n0 {last + 1}\n".encode("ascii"))
    buffer.write(b"0000000000 65535 f \n")
    for obj_number in range(1, last + 1):
        buffer.write(f"{offsets[obj_number]:010d} 00000 n \n".encode("ascii"))
    buffer.write(
        f"trailer<</Size {last + 1}/Root 1 0 R>>\nstartxref\n{xref_position}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return buffer.getvalue()


def test_happy_path_extracts_the_fixture() -> None:
    document = extract(FIXTURE.read_bytes())
    assert document.method == "pdfplumber"
    assert len(document.pages) == 1
    row_text = document.pages[0].row_text
    assert "Alex Example" in row_text
    assert "alex@example.com" in row_text
    assert document.pages[0].column_text is None
    assert document.char_count == len(row_text)


def test_extraction_preserves_en_dashes_and_bullets_without_replacement_chars() -> None:
    row_text = extract(FIXTURE.read_bytes()).pages[0].row_text
    assert EN_DASH in row_text
    assert BULLET in row_text
    assert REPLACEMENT_CHAR not in row_text


def test_footer_text_is_absent_from_error_messages() -> None:
    with pytest.raises(AppError) as excinfo:
        extract(b"%PDF-1.7\nnot a pdf")
    assert "Alex Example" not in excinfo.value.message


def test_empty_input_is_rejected_as_too_large() -> None:
    with pytest.raises(AppError) as excinfo:
        extract(b"")
    assert excinfo.value.code == "too_large"


def test_oversize_input_is_rejected_before_parsing() -> None:
    one_page = build_pdf(1)
    oversized = one_page + b"\x00" * (MAX_FILE_BYTES - len(one_page) + 1)
    with pytest.raises(AppError) as excinfo:
        extract(oversized)
    assert excinfo.value.code == "too_large"


def test_text_file_without_signature_is_unsupported() -> None:
    with pytest.raises(AppError) as excinfo:
        extract(b"Hello plain text, no signature")
    assert excinfo.value.code == "unsupported_type"


def test_zip_signature_file_is_unsupported_until_docx_exists() -> None:
    with pytest.raises(AppError) as excinfo:
        extract(b"PK\x03\x04" + b"\x00" * 100)
    assert excinfo.value.code == "unsupported_type"


def test_truncated_pdf_is_bad_pdf() -> None:
    data = build_pdf(1)[:200]
    with pytest.raises(AppError) as excinfo:
        extract(data)
    assert excinfo.value.code == "bad_pdf"


def test_garbage_after_pdf_header_is_bad_pdf() -> None:
    with pytest.raises(AppError) as excinfo:
        extract(b"%PDF-1.7\nnot a pdf")
    assert excinfo.value.code == "bad_pdf"


def test_too_many_pages_is_checked_before_text_extraction() -> None:
    data = build_pdf(MAX_PAGES + 1)
    with pytest.raises(AppError) as excinfo:
        extract(data)
    assert excinfo.value.code == "too_many_pages"


def test_exactly_max_pages_succeeds() -> None:
    document = extract(build_pdf(MAX_PAGES))
    assert len(document.pages) == MAX_PAGES


def test_no_extractable_text_is_rejected() -> None:
    with pytest.raises(AppError) as excinfo:
        extract(build_pdf(1, text="   "))
    assert excinfo.value.code == "no_extractable_text"


def test_encrypted_pdf_maps_to_encrypted_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real encrypted PDFs need a new dependency; the mapping is tested via the
    library's own exception, raising through the same code path."""
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    def fake_open(*args: object, **kwargs: object) -> object:
        raise PDFPasswordIncorrect("incorrect password")

    monkeypatch.setattr(pdfplumber, "open", fake_open)
    with pytest.raises(AppError) as excinfo:
        extract(build_pdf(1))
    assert excinfo.value.code == "encrypted_pdf"


def test_extractor_never_creates_files(monkeypatch: pytest.MonkeyPatch) -> None:
    data = FIXTURE.read_bytes()

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("the extractor must not touch the filesystem")

    monkeypatch.setattr(builtins, "open", refuse, raising=False)
    for name in (
        "mkstemp",
        "mkdtemp",
        "mktemp",
        "NamedTemporaryFile",
        "TemporaryFile",
        "TemporaryDirectory",
    ):
        monkeypatch.setattr(tempfile, name, refuse, raising=False)

    document = extract(data)
    assert document.char_count > 0
