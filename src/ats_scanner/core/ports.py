"""Extractor, TermExtractor, SuggestionProvider.

Protocols belong to core/ and are implemented by adapters/
(adapters/extract.py in v1). Only Extractor is designed so far; the other
two arrive with their features.
"""

from typing import Protocol, runtime_checkable

from ats_scanner.core.documents import ExtractedDocument


@runtime_checkable
class Extractor(Protocol):
    """Turns uploaded file bytes into the normalized extracted document.

    Implementations must raise AppError with a SPEC §5 code from
    core/errors.py when the file is invalid, too large, encrypted, or has no
    extractable text. No I/O beyond what the bytes require; no network.
    """

    def extract(self, data: bytes, filename: str, content_type: str) -> ExtractedDocument:
        """Extract text from an in-memory file, or raise AppError."""
        ...
