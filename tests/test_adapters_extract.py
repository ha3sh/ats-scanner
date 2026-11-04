"""In-memory extraction (PDF + DOCX + dispatcher): validation, happy path, no writes."""

import builtins
import io
import tempfile
import zipfile
from pathlib import Path

import docx
import pytest

from ats_scanner.adapters.extract import SignatureRoutedExtractor, read_bounded
from ats_scanner.config import (
    MAX_DOCX_ENTRIES,
    MAX_DOCX_UNCOMPRESSED_BYTES,
    MAX_FILE_BYTES,
    MAX_PAGES,
)
from ats_scanner.core.documents import ExtractedDocument, WarningCode
from ats_scanner.core.errors import AppError

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "resumes" / "resume_simple.pdf"
DOCX_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "resumes" / "resume_simple.docx"
TWO_COLUMN_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "resumes" / "resume_two_column.pdf"
)
SIDEBAR_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "resumes" / "resume_sidebar.pdf"

EN_DASH = "\u2013"  # used in date ranges and separators in the fixture
BULLET = "\u2022"  # used in list lines
REPLACEMENT_CHAR = "\ufffd"  # mojibake marker that must never leak into text

SECTION_HEADINGS = ("Summary", "Experience", "Education", "Skills")


def extract(data: bytes) -> ExtractedDocument:
    """Route the bytes by signature, exactly as the production path will."""
    return SignatureRoutedExtractor().extract(data, "resume.bin", "application/octet-stream")


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
    assert document.warnings == ()  # single column: no columns_suspected
    assert document.char_count == len(row_text)


def build_two_column_pdf() -> bytes:
    """A one-page PDF with a full-width header line and two columns of text.

    Positioning uses absolute Td (a fresh text object starts at the origin,
    so 72 710 Td is exactly the point the existing build_pdf relies on).
    Left column at x=72, right column at x=340: the empty band between the
    widest left word (~237) and the right column is ~17% of the 612 pt page.
    """
    header = "Full width header across the gutter that separates the columns"
    lines: list[tuple[int, int, str]] = [(72, 730, header)]
    for row in range(1, 9):
        y = 710 - (row - 1) * 15
        lines.append((72, y, f"Left row {row} alpha beta gamma delta"))
        lines.append((340, y, f"Right row {row} epsilon zeta eta theta"))

    stream = " ".join(f"BT /F1 10 Tf {x} {y} Td ({text}) Tj ET" for x, y, text in lines).encode(
        "ascii"
    )

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    objects: list[tuple[int, bytes]] = []
    objects.append((1, b"<</Type/Catalog/Pages 2 0 R>>"))
    objects.append((2, b"<</Type/Pages/Kids[3 0 R]/Count 1>>"))
    objects.append(
        (
            3,
            "<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R"
            "/Resources<</Font<</F1 5 0 R>>>>>>".encode("ascii"),
        )
    )
    objects.append(
        (
            4,
            b"<</Length "
            + str(len(stream)).encode("ascii")
            + b">>stream\n"
            + stream
            + b"\nendstream",
        )
    )
    objects.append((5, b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"))

    offsets: dict[int, int] = {}
    for obj_number, content in objects:
        offsets[obj_number] = buffer.tell()
        buffer.write(f"{obj_number} 0 obj\n".encode("ascii"))
        buffer.write(content)
        buffer.write(b"\nendobj\n")

    xref_position = buffer.tell()
    buffer.write("xref\n0 6\n".encode("ascii"))
    buffer.write(b"0000000000 65535 f \n")
    for obj_number in range(1, 6):
        buffer.write(f"{offsets[obj_number]:010d} 00000 n \n".encode("ascii"))
    buffer.write(
        f"trailer<</Size 6/Root 1 0 R>>\nstartxref\n{xref_position}\n%%EOF\n".encode("ascii")
    )
    return buffer.getvalue()


def test_two_column_pdf_reported_in_row_order_interleaves() -> None:
    document = extract(build_two_column_pdf())
    assert document.method == "pdfplumber"
    assert len(document.pages) == 1
    lines = document.pages[0].row_text.splitlines()
    assert "Full width header across the gutter that separates the columns" in lines[0]
    # Row order interleaves: every visual line carries a left and a right
    # fragment of the same printed row.
    for row in range(1, 9):
        assert f"Left row {row}" in lines[row]
        assert f"Right row {row}" in lines[row]


def test_two_column_pdf_reported_in_column_order_separates() -> None:
    document = extract(build_two_column_pdf())
    page = document.pages[0]
    column_text = page.column_text
    assert column_text is not None
    # Column order separates: header first, then the full left block, then
    # the full right block.
    assert column_text.index("Full width header") < column_text.index("Left row 1")
    order = [
        column_text.index(marker)
        for marker in (
            "Left row 1",
            "Left row 4",
            "Left row 8",
            "Right row 1",
            "Right row 4",
            "Right row 8",
        )
    ]
    assert order == sorted(order), column_text
    # The evidence for the two views: a warning names the page.
    assert [(warning.code, warning.page) for warning in document.warnings] == [
        (WarningCode.COLUMNS_SUSPECTED, 1)
    ]


def test_two_column_fixture_is_still_detected() -> None:
    document = extract(TWO_COLUMN_FIXTURE.read_bytes())
    page = document.pages[0]
    column_text = page.column_text
    assert column_text is not None
    lines = column_text.splitlines()
    assert lines[0] == "Sam Sample"
    # Sidebar ("Skills") before main ("Summary"), header first.
    assert lines.index("Skills") < lines.index("Summary")
    assert [(warning.code, warning.page) for warning in document.warnings] == [
        (WarningCode.COLUMNS_SUSPECTED, 1)
    ]


def test_sidebar_fixture_is_detected_with_left_anchored_header() -> None:
    document = extract(SIDEBAR_FIXTURE.read_bytes())
    page = document.pages[0]
    column_text = page.column_text
    assert column_text is not None
    assert [(warning.code, warning.page) for warning in document.warnings] == [
        (WarningCode.COLUMNS_SUSPECTED, 1)
    ]
    lines = column_text.splitlines()
    # The header block is read first, exactly as printed on the page.
    assert lines[:3] == [
        "Sam Sample",
        "Data Engineer",
        "sam@example.com | (555) 555-0142 | Springfield, USA",
    ]
    # Then the sidebar block, then the main block.
    names = [line for line in lines if line.strip()]
    assert names[3] == "Skills"
    assert "Certifications" in names
    assert names.index("Certifications") < names.index("Summary")


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


def test_zip_signature_bytes_that_are_not_a_zip_are_bad_docx() -> None:
    """DOCX support now exists, so the PK signature routes to the DOCX path."""
    with pytest.raises(AppError) as excinfo:
        extract(b"PK\x03\x04" + b"\x00" * 100)
    assert excinfo.value.code == "bad_docx"


def test_dispatcher_routes_by_signature_not_metadata() -> None:
    assert extract(FIXTURE.read_bytes()).method == "pdfplumber"
    assert extract(DOCX_FIXTURE.read_bytes()).method == "python-docx"


# --- DOCX limits -----------------------------------------------------------


def test_docx_limits_have_the_locked_values() -> None:
    assert MAX_DOCX_UNCOMPRESSED_BYTES == 25 * 1024 * 1024
    assert MAX_DOCX_ENTRIES == 1000


def test_bounded_read_stops_above_the_cap() -> None:
    stream = io.BytesIO(b"\x00" * (MAX_DOCX_UNCOMPRESSED_BYTES + 1))
    with pytest.raises(AppError) as excinfo:
        read_bounded(stream, MAX_DOCX_UNCOMPRESSED_BYTES)
    assert excinfo.value.code == "bad_docx"


def make_zip(entries: dict[str, bytes]) -> bytes:
    """A real ZIP archive built with plain stdlib zipfile."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_docx_happy_path_extracts_the_fixture() -> None:
    document = extract(DOCX_FIXTURE.read_bytes())
    assert document.method == "python-docx"
    row_text = document.pages[0].row_text
    assert "Alex Example" in row_text
    assert "alex@example.com" in row_text
    assert "March 2021" in row_text
    assert "PostgreSQL" in row_text
    positions = [row_text.index(heading) for heading in SECTION_HEADINGS]
    assert positions == sorted(positions)


def test_docx_is_one_page_with_column_order_unfilled() -> None:
    document = extract(DOCX_FIXTURE.read_bytes())
    assert len(document.pages) == 1
    assert document.pages[0].column_text is None


def test_pk_bytes_with_a_broken_zip_are_bad_docx() -> None:
    packed = make_zip({"word/document.xml": b"<doc/>"})[:-40]  # truncated central dir
    with pytest.raises(AppError) as excinfo:
        extract(packed)
    assert excinfo.value.code == "bad_docx"


def test_zip_without_document_xml_is_unsupported() -> None:
    packed = make_zip({"[Content_Types].xml": b"<Types/>", "sheets/sheet1.xml": b"<s/>"})
    with pytest.raises(AppError) as excinfo:
        extract(packed)
    assert excinfo.value.code == "unsupported_type"


def test_zip_bomb_is_rejected_without_full_decompression() -> None:
    bomb = make_zip(
        {
            "word/document.xml": b"\x00" * (MAX_DOCX_UNCOMPRESSED_BYTES + 1),
        }
    )
    assert len(bomb) < 1024 * 1024  # the archive itself is tiny
    with pytest.raises(AppError) as excinfo:
        extract(bomb)
    assert excinfo.value.code == "bad_docx"


def test_too_many_zip_entries_is_bad_docx() -> None:
    names = {f"docx-junk/part{index:04d}.xml": b"<x/>" for index in range(1001)}
    packed = make_zip(names)
    with pytest.raises(AppError) as excinfo:
        extract(packed)
    assert excinfo.value.code == "bad_docx"


def make_docx_with_pages_hint(pages: int) -> bytes:
    """A valid python-docx package whose app.xml re-added with a Pages hint.

    python-docx generates the body live so the package is genuinely OOXML.
    """
    package = io.BytesIO()
    native = docx.Document()
    native.add_paragraph("Alex Example")
    native.save(package)
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(package) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries["docProps/app.xml"] = f"<Properties><Pages>{pages}</Pages></Properties>".encode("ascii")
    return make_zip(entries)


def test_docx_pages_hint_above_max_is_too_many_pages() -> None:
    with pytest.raises(AppError) as excinfo:
        extract(make_docx_with_pages_hint(200))
    assert excinfo.value.code == "too_many_pages"


def test_docx_pages_hint_below_max_does_not_block() -> None:
    document = extract(make_docx_with_pages_hint(2))
    assert document.method == "python-docx"
    assert "Alex Example" in document.pages[0].row_text


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


@pytest.mark.parametrize(
    ("fixture_path", "expected_method"),
    [(FIXTURE, "pdfplumber"), (DOCX_FIXTURE, "python-docx")],
)
def test_extractor_never_creates_files(
    monkeypatch: pytest.MonkeyPatch, fixture_path: Path, expected_method: str
) -> None:
    data = fixture_path.read_bytes()

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
    assert document.method == expected_method
