"""Extractor implementations (pdfplumber, python-docx) and the dispatcher.

All implementations work only on in-memory bytes (SPEC §6): BytesIO, no
temp files, no disk writes, and error messages never carry document text —
they name the failure category and what to do next.

Validation always runs cheapest check first. The shared size cap and the
signature check happen in the dispatcher before anything is parsed; each
extractor still re-checks defensively so it stays correct standalone.

DOCX anti-bomb guard order (SPEC §5): the entry count and the sum of the
declared uncompressed sizes are read from the ZIP central directory (no
decompression), then `word/document.xml` is verified with a bounded
streaming read that stops above the cap, because declared sizes can lie.
"""

import io
import re
import zipfile
import zlib
from typing import IO

import docx
import pdfplumber
from docx.document import Document as DocxDocument
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

from ats_scanner.config import (
    MAX_DOCX_ENTRIES,
    MAX_DOCX_UNCOMPRESSED_BYTES,
    MAX_FILE_BYTES,
    MAX_PAGES,
)
from ats_scanner.core.documents import (
    ExtractedDocument,
    ExtractedPage,
    ExtractionWarning,
    WarningCode,
)
from ats_scanner.core.errors import AppError
from ats_scanner.core.layout import WordBox, column_order
from ats_scanner.core.ports import Extractor

_PDF_SIGNATURE = b"%PDF-"
_DOCX_SIGNATURE = b"PK\x03\x04"

_CHUNK_SIZE = 64 * 1024
_MAX_APP_XML_BYTES = 1024 * 1024

_MESSAGES = {
    "too_large": (
        "The file is larger than the 5 MB limit. "
        "Upload a PDF or DOCX file under 5 MB and try again."
    ),
    "unsupported_type": (
        "That file type is not supported. Upload a PDF or DOCX file and try again."
    ),
    "encrypted_pdf": (
        "The PDF is password-protected. Remove the password or save an unprotected "
        "copy, then try again."
    ),
    "bad_pdf": (
        "The PDF is corrupt or incomplete and could not be read. Re-export the PDF and try again."
    ),
    "bad_docx": (
        "The DOCX file is corrupt, incomplete, or leads to an uncompressed size "
        "beyond the cap. Re-export the file and try again."
    ),
    "too_many_pages": (
        f"The document has more than {MAX_PAGES} pages. Shorten it to {MAX_PAGES} "
        "pages or fewer and try again."
    ),
    "no_extractable_text": (
        "No readable text was found. Export the document with selectable text and try again."
    ),
}

_ATS_SEES_METHOD = "pdfplumber"


def _code_error(code: str) -> AppError:
    return AppError(code, _MESSAGES[code])


def read_bounded(stream: IO[bytes], cap: int) -> bytes:
    """Read a stream but stop as soon as the total goes above `cap` bytes."""
    chunks: list[bytes] = []
    remaining = cap
    while True:
        chunk = stream.read(_CHUNK_SIZE)
        if not chunk:
            break
        remaining -= len(chunk)
        if remaining < 0:
            raise _code_error("bad_docx")
        chunks.append(chunk)
    return b"".join(chunks)


class PdfplumberExtractor:
    """PDF extraction with pdfplumber; implements the Extractor protocol."""

    def extract(self, data: bytes, filename: str, content_type: str) -> ExtractedDocument:
        """Extract text from an in-memory PDF, or raise AppError."""
        del filename, content_type  # the signature decides the type, not metadata

        if len(data) == 0 or len(data) > MAX_FILE_BYTES:
            raise _code_error("too_large")
        if not data.startswith(_PDF_SIGNATURE):
            raise _code_error("unsupported_type")

        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                if pdf.doc.encryption is not None:
                    raise _code_error("encrypted_pdf")
                if len(pdf.pages) > MAX_PAGES:
                    raise _code_error("too_many_pages")
                row_texts: list[str] = []
                column_texts: list[str | None] = []
                warnings: list[ExtractionWarning] = []
                for number, page in enumerate(pdf.pages, start=1):
                    row_texts.append(page.extract_text() or "")
                    boxes = [
                        WordBox(
                            text=word["text"],
                            x0=word["x0"],
                            x1=word["x1"],
                            top=word["top"],
                            bottom=word["bottom"],
                        )
                        for word in page.extract_words()
                    ]
                    column_text = None if not boxes else column_order(boxes, page.width)
                    column_texts.append(column_text)
                    if column_text is not None:
                        warnings.append(
                            ExtractionWarning(
                                code=WarningCode.COLUMNS_SUSPECTED,
                                message=(
                                    f"Columns suspected on page {number}: the page may be "
                                    "laid out in two columns. Column order is a best-effort "
                                    "re-reading, row order is the extracted stream."
                                ),
                                page=number,
                            )
                        )
        except PDFPasswordIncorrect:
            raise _code_error("encrypted_pdf") from None
        except PdfminerException:
            raise _code_error("bad_pdf") from None

        if any(text.strip() for text in row_texts):
            return ExtractedDocument(
                pages=tuple(
                    ExtractedPage(
                        page_number=number + 1,
                        row_text=row_text,
                        column_text=column_text,
                    )
                    for number, (row_text, column_text) in enumerate(zip(row_texts, column_texts))
                ),
                method=_ATS_SEES_METHOD,
                warnings=tuple(warnings),
            )
        raise _code_error("no_extractable_text")


class DocxExtractor:
    """DOCX extraction with python-docx; implements the Extractor protocol."""

    def extract(self, data: bytes, filename: str, content_type: str) -> ExtractedDocument:
        """Extract text from an in-memory DOCX, or raise AppError."""
        del filename, content_type

        if len(data) == 0 or len(data) > MAX_FILE_BYTES:
            raise _code_error("too_large")

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_DOCX_ENTRIES:
                    raise _code_error("bad_docx")
                if sum(info.file_size for info in infos) > MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise _code_error("bad_docx")
                names = {info.filename for info in infos}
                if "word/document.xml" not in names:
                    raise _code_error("unsupported_type")
                # Declared sizes can lie: re-read the document part with a
                # bounded streaming read that stops above the cap.
                with archive.open("word/document.xml") as part:
                    read_bounded(part, MAX_DOCX_UNCOMPRESSED_BYTES)
                if "docProps/app.xml" in names:
                    with archive.open("docProps/app.xml") as part:
                        app_xml = read_bounded(part, _MAX_APP_XML_BYTES)
                    pages = _declared_pages(app_xml)
                    if pages is not None and pages > MAX_PAGES:
                        raise _code_error("too_many_pages")
        except (zipfile.BadZipFile, zlib.error, EOFError):
            raise _code_error("bad_docx") from None

        try:
            lines = _document_line_texts(docx.Document(io.BytesIO(data)))
        except Exception:  # noqa: BLE001 - any parse failure is a bad DOCX
            raise _code_error("bad_docx") from None

        if any(line.strip() for line in lines):
            return ExtractedDocument(
                pages=(ExtractedPage(page_number=1, row_text="\n".join(lines)),),
                method="python-docx",
            )
        raise _code_error("no_extractable_text")


def _document_line_texts(document: DocxDocument) -> list[str]:
    """Body paragraphs and table cell text, interleaved in document order.

    Headers, footers, and text boxes are deliberately not read yet (Day 7
    owns format findings); this is body content only.
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    lines: list[str] = []
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            lines.append(item.text)
        elif isinstance(item, Table):
            for row in item.rows:
                for cell in row.cells:
                    lines.append(cell.text)
    return lines


def _declared_pages(app_xml: bytes) -> int | None:
    """The `<Pages>` hint from docProps/app.xml, or None when absent."""
    match = re.search(rb"<Pages>(\d+)</Pages>", app_xml)
    if match:
        return int(match.group(1))
    return None


class SignatureRoutedExtractor:
    """The one Extractor implementation behind the API: routes by signature.

    `%PDF-` goes to the PDF extractor, `PK\\x03\\x04` to the DOCX extractor,
    anything else is `unsupported_type`. Filename and content type are
    ignored (SPEC §5: the signature decides the type).
    """

    def extract(self, data: bytes, filename: str, content_type: str) -> ExtractedDocument:
        """Route the bytes to the right extractor by file signature."""
        del filename, content_type

        if len(data) == 0 or len(data) > MAX_FILE_BYTES:
            raise _code_error("too_large")
        if data.startswith(_PDF_SIGNATURE):
            return PdfplumberExtractor().extract(data, "skip", "skip")
        if data.startswith(_DOCX_SIGNATURE):
            return DocxExtractor().extract(data, "skip", "skip")
        raise _code_error("unsupported_type")


# Structural check at import time: the dispatcher satisfies the core protocol.
satisfies_extractor_protocol: Extractor = SignatureRoutedExtractor()
