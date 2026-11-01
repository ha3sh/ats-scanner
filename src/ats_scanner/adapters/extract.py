"""Extractor implementations (pdfplumber, python-docx).

PdfplumberExtractor works only on in-memory bytes (SPEC §6): BytesIO, no
temp files, no disk writes, and error messages never carry document text —
they name the failure category and what to do next.
"""

import io

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

from ats_scanner.config import MAX_FILE_BYTES, MAX_PAGES
from ats_scanner.core.documents import ExtractedDocument, ExtractedPage
from ats_scanner.core.errors import AppError
from ats_scanner.core.ports import Extractor

_PDF_SIGNATURE = b"%PDF-"

_MESSAGES = {
    "too_large": ("The file is larger than the 5 MB limit. Export a smaller PDF and try again."),
    "unsupported_type": ("That file type is not supported. Upload a PDF file and try again."),
    "encrypted_pdf": (
        "The PDF is password-protected. Remove the password or save an unprotected "
        "copy, then try again."
    ),
    "bad_pdf": (
        "The PDF is corrupt or incomplete and could not be read. Re-export the PDF and try again."
    ),
    "too_many_pages": (
        f"The PDF has more than {MAX_PAGES} pages. Reduce it to {MAX_PAGES} pages or "
        "fewer and try again."
    ),
    "no_extractable_text": (
        "No readable text was found. If this is a scanned document, export it as a "
        "PDF with selectable text and try again."
    ),
}

_ATS_SEES_METHOD = "pdfplumber"


def _code_error(code: str) -> AppError:
    return AppError(code, _MESSAGES[code])


class PdfplumberExtractor:
    """PDF extraction with pdfplumber; implements the Extractor protocol.

    Validation runs cheapest check first: size, signature, then the document
    itself — encryption, page count, and only then text extraction (SPEC §5).
    """

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
                row_texts = [page.extract_text() or "" for page in pdf.pages]
        except PDFPasswordIncorrect:
            raise _code_error("encrypted_pdf") from None
        except PdfminerException:
            raise _code_error("bad_pdf") from None

        if any(text.strip() for text in row_texts):
            return ExtractedDocument(
                pages=tuple(
                    ExtractedPage(page_number=number + 1, row_text=text)
                    for number, text in enumerate(row_texts)
                ),
                method=_ATS_SEES_METHOD,
            )
        raise _code_error("no_extractable_text")


# Structural check at import time: the implementation satisfies the core protocol.
satisfies_extractor_protocol: Extractor = PdfplumberExtractor()
