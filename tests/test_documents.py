"""Document model and Extractor contract (core/, no parser library)."""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from ats_scanner.core.documents import ExtractedDocument, ExtractedPage, ExtractionWarning
from ats_scanner.core.errors import AppError
from ats_scanner.core.ports import Extractor


def _two_page_document(row_texts: tuple[str, ...]) -> ExtractedDocument:
    return ExtractedDocument(
        pages=tuple(
            ExtractedPage(page_number=number + 1, row_text=text)
            for number, text in enumerate(row_texts)
        ),
        method="test",
    )


def test_column_order_defaults_to_not_filled() -> None:
    page = ExtractedPage(page_number=1, row_text="skills and experience")
    assert page.column_text is None


def test_page_may_hold_the_same_text_in_both_orders() -> None:
    page = ExtractedPage(page_number=1, row_text="same", column_text="same")
    assert page.row_text == page.column_text


def test_character_count_sums_across_pages() -> None:
    document = _two_page_document(("abc", "de"))
    assert document.char_count == 5


def test_character_count_counts_non_bmp_characters_as_one() -> None:
    document = _two_page_document(("a😀b",))  # U+1F600: one code point, two UTF-16 units
    assert document.char_count == 3


def test_character_count_is_computed_not_stored() -> None:
    assert "char_count" not in ExtractedDocument.model_fields


def test_models_are_frozen_immutability() -> None:
    page = ExtractedPage(page_number=1, row_text="text")
    document = _two_page_document(("abc",))
    with pytest.raises(ValidationError):
        page.row_text = "changed"
    with pytest.raises(ValidationError):
        document.method = "changed"


def test_pages_cannot_grow_after_creation() -> None:
    document = _two_page_document(("abc",))
    assert isinstance(document.pages, tuple)
    with pytest.raises((AttributeError, TypeError)):
        document.pages.append(ExtractedPage(page_number=2, row_text="x"))  # type: ignore[attr-defined]


def test_warning_carries_code_sentence_and_optional_page() -> None:
    warning = ExtractionWarning(code="columns_suspected", message="...", page=1)
    bare = ExtractionWarning(code="emoji", message="...")
    assert warning.page == 1
    assert bare.page is None


def test_empty_document_is_valid_but_has_zero_characters() -> None:
    document = ExtractedDocument(pages=(), method="test")
    assert document.char_count == 0


class FakeExtractor:
    """In-memory implementation: no pdfplumber, no python-docx."""

    def extract(self, data: bytes, filename: str, content_type: str) -> ExtractedDocument:
        return ExtractedDocument(
            pages=(ExtractedPage(page_number=1, row_text=data.decode("utf-8")),),
            method="fake",
        )


def test_fake_in_memory_extractor_satisfies_the_protocol() -> None:
    extractor: Extractor = FakeExtractor()  # mypy structurally checks this
    document = extractor.extract(b"hello", "resume.txt", "text/plain")
    assert document.char_count == len("hello")
    assert document.method == "fake"


class FailingExtractor:
    def extract(self, data: bytes, filename: str, content_type: str) -> ExtractedDocument:
        raise AppError("no_extractable_text", "The document has no text.")


def test_extractor_failure_is_an_app_error_with_a_spec_code() -> None:
    extractor: Extractor = FailingExtractor()
    raises: Callable[..., object] = extractor.extract
    with pytest.raises(AppError) as excinfo:
        raises(b"", "scan.pdf", "application/pdf")
    assert excinfo.value.code == "no_extractable_text"
