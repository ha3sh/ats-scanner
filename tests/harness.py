"""Evaluation harness: run a fixture through extractor + pipeline, compare
a declared subset of the result (ROADMAP Day 4).

Convention: next to every fixture `name.ext` sits `name.ext.expected.json`
asserting a SUBSET of the result. Allowed keys, all optional:

- `reading_order`: list of "row"/"column", compared exactly
- `sections_found`: section names that must be found
- `sections_missing`: section names that must not be found
- `contact`: object with email/phone/linkedin -> found boolean
- `warning_codes`: compared as sets
- `error`: an error code; when present it must be the only key and
  extraction must raise AppError with exactly that code

Unknown keys (top-level or inside `contact`) and unknown section names
fail loudly. Anything not mentioned is not checked. `check` returns
human-readable mismatch messages; an empty list means pass.
"""

from dataclasses import dataclass
from pathlib import Path

from ats_scanner.adapters.extract import SignatureRoutedExtractor
from ats_scanner.core.errors import AppError
from ats_scanner.core.pipeline import analyze
from ats_scanner.core.report import SectionName

_ALLOWED_KEYS = frozenset(
    {
        "reading_order",
        "sections_found",
        "sections_missing",
        "contact",
        "warning_codes",
        "error",
    }
)
_CONTACT_KEYS = frozenset({"email", "phone", "linkedin"})
_SECTION_NAMES = frozenset(section.value for section in SectionName)


@dataclass(frozen=True)
class FixtureFacts:
    """The comparable facts of one fixture run, or the error code."""

    error: str | None
    reading_order: tuple[str, ...]
    sections_found: frozenset[str]
    sections_missing: frozenset[str]
    contact: dict[str, bool]
    warning_codes: frozenset[str]


def run_fixture(path: Path) -> FixtureFacts:
    """Extract and analyze one fixture; on AppError the facts carry the code."""
    data = path.read_bytes()
    try:
        document = SignatureRoutedExtractor().extract(data, path.name, "application/octet-stream")
    except AppError as exc:
        return FixtureFacts(
            error=exc.code.value,
            reading_order=(),
            sections_found=frozenset(),
            sections_missing=frozenset(),
            contact={},
            warning_codes=frozenset(),
        )
    result = analyze(document)
    return FixtureFacts(
        error=None,
        reading_order=tuple(result.reading_order),
        sections_found=frozenset(f.name.value for f in result.sections if f.found),
        sections_missing=frozenset(f.name.value for f in result.sections if not f.found),
        contact={
            "email": result.contact.email.found,
            "phone": result.contact.phone.found,
            "linkedin": result.contact.linkedin.found,
        },
        warning_codes=frozenset(warning.code.value for warning in document.warnings),
    )


def check(expected: dict[str, object], actual: FixtureFacts) -> list[str]:
    """Compare the expected subset against the facts; [] means pass."""
    messages: list[str] = []
    unknown = sorted(set(expected) - _ALLOWED_KEYS)
    if unknown:
        allowed = ", ".join(sorted(_ALLOWED_KEYS))
        messages.append(f"unknown expected key(s): {', '.join(unknown)} (allowed: {allowed})")

    if "error" in expected:
        if set(expected) != {"error"}:
            messages.append("'error' must be the only key in the expected file")
        expected_error = expected["error"]
        if not isinstance(expected_error, str):
            messages.append("'error' must be a string error code")
        elif actual.error is None:
            messages.append(f"expected error {expected_error!r}, but extraction succeeded")
        elif actual.error != expected_error:
            messages.append(f"expected error {expected_error!r}, got {actual.error!r}")
        return messages

    if actual.error is not None:
        messages.append(
            f"extraction raised error {actual.error!r}, but the expected file "
            "declares a successful result"
        )
        return messages

    _check_reading_order(expected, actual, messages)
    _check_sections(expected, actual, messages)
    _check_contact(expected, actual, messages)
    _check_warning_codes(expected, actual, messages)
    return messages


def _check_reading_order(
    expected: dict[str, object], actual: FixtureFacts, messages: list[str]
) -> None:
    value = expected.get("reading_order")
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        messages.append('\'reading_order\' must be a list of "row"/"column" strings')
        return
    if list(actual.reading_order) != value:
        messages.append(f"reading_order: expected {value}, got {list(actual.reading_order)}")


def _check_sections(expected: dict[str, object], actual: FixtureFacts, messages: list[str]) -> None:
    checks = (
        ("sections_found", actual.sections_found, "not found as expected"),
        ("sections_missing", actual.sections_missing, "unexpectedly found"),
    )
    for key, actual_names, complaint in checks:
        value = expected.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            messages.append(f"{key!r} must be a list of section names")
            continue
        unknown = sorted(set(value) - _SECTION_NAMES)
        if unknown:
            allowed = ", ".join(sorted(_SECTION_NAMES))
            messages.append(
                f"{key}: unknown section name(s): {', '.join(unknown)} (allowed: {allowed})"
            )
            continue
        unmet = [name for name in value if name not in actual_names]
        if unmet:
            messages.append(f"{key}: {complaint}: {', '.join(unmet)}")


def _check_contact(expected: dict[str, object], actual: FixtureFacts, messages: list[str]) -> None:
    value = expected.get("contact")
    if value is None:
        return
    if not isinstance(value, dict):
        messages.append("'contact' must be an object with email/phone/linkedin booleans")
        return
    unknown = sorted(set(value) - _CONTACT_KEYS)
    if unknown:
        allowed = ", ".join(sorted(_CONTACT_KEYS))
        messages.append(f"contact: unknown key(s): {', '.join(unknown)} (allowed: {allowed})")
        return
    for key in sorted(value):
        flag = value[key]
        if not isinstance(flag, bool):
            messages.append(f"contact.{key} must be a boolean")
            continue
        actual_found = actual.contact.get(key, False)
        if actual_found != flag:
            messages.append(
                f"contact.{key}: expected {'found' if flag else 'not found'}, "
                f"got {'found' if actual_found else 'not found'}"
            )


def _check_warning_codes(
    expected: dict[str, object], actual: FixtureFacts, messages: list[str]
) -> None:
    value = expected.get("warning_codes")
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        messages.append("'warning_codes' must be a list of warning code strings")
        return
    expected_set = set(value)
    if expected_set != set(actual.warning_codes):
        messages.append(
            f"warning_codes: expected {sorted(expected_set)}, got {sorted(actual.warning_codes)}"
        )
