"""SPEC §5 error codes and the transport-agnostic AppError.

Pure Python: no FastAPI, no I/O. Adapters and core raise AppError when a
document or request fails; api.py turns the code into an HTTP status and
the JSON envelope.

StrEnum over Literal: callers need the closed set at runtime (to reject
unknown codes and to test the code/status map against the enum), which a
typing-only Literal cannot provide.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    """The closed set of SPEC §5 error codes."""

    UNSUPPORTED_TYPE = "unsupported_type"
    TOO_LARGE = "too_large"
    TOO_MANY_PAGES = "too_many_pages"
    ENCRYPTED_PDF = "encrypted_pdf"
    NO_EXTRACTABLE_TEXT = "no_extractable_text"
    BAD_DOCX = "bad_docx"
    JD_TOO_SHORT = "jd_too_short"
    JD_TOO_LONG = "jd_too_long"
    INVALID_REQUEST = "invalid_request"


class AppError(Exception):
    """An error carrying a SPEC §5 code and one human sentence."""

    code: ErrorCode
    message: str

    def __init__(self, code: "ErrorCode | str", message: str) -> None:
        try:
            self.code = ErrorCode(code)
        except ValueError as exc:
            raise ValueError(f"{code!r} is not a SPEC error code") from exc
        self.message = message
        super().__init__(message)
