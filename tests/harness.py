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

JD fixtures use `kept`/`removed` (block lists) plus `terms` (a subset
check: list of {canonical, weight?} that must all be present) and
`absent_terms` (canonicals that must not appear).

Unknown keys (top-level or inside `contact`/block/term entries) and
unknown section names fail loudly. Anything not mentioned is not
checked. `check`/`check_jd` return human-readable mismatch messages;
an empty list means pass.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ats_scanner.adapters.dictionary_loader import load_dictionary
from ats_scanner.adapters.extract import SignatureRoutedExtractor
from ats_scanner.core.dictionary import SkillEntry, build_index
from ats_scanner.core.errors import AppError
from ats_scanner.core.jd import CleanedJd, clean_jd
from ats_scanner.core.pipeline import analyze
from ats_scanner.core.report import SectionName
from ats_scanner.core.terms import JdTerm, extract_terms

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


# --- JD fixtures (same conventions, different facts) ---

_JD_ALLOWED_KEYS = frozenset({"kept", "removed", "terms", "absent_terms"})


@dataclass(frozen=True)
class JdFacts:
    """The comparable facts of one JD fixture run."""

    cleaned: CleanedJd
    terms: tuple[JdTerm, ...]


@lru_cache(maxsize=1)
def _jd_index() -> dict[str, SkillEntry]:
    """The real dictionary index, loaded once for all JD fixtures."""
    return build_index(load_dictionary())


def run_jd(path: Path) -> JdFacts:
    """Read, clean, and term-extract one JD fixture."""
    cleaned = clean_jd(path.read_text(encoding="utf-8"))
    return JdFacts(cleaned=cleaned, terms=extract_terms(cleaned, _jd_index()))


def check_jd(expected: dict[str, object], actual: JdFacts) -> list[str]:
    """Compare the expected subset against a JdFacts run; [] means pass.

    `kept` entries may carry start_line and kind; `removed` entries
    start_line and reason. `terms` entries carry canonical and an
    optional weight and must all be present (subset). `absent_terms`
    lists canonicals that must not appear. Unknown keys (top level or
    inside an entry) fail loudly; anything not mentioned is not checked.
    """
    messages: list[str] = []
    unknown = sorted(set(expected) - _JD_ALLOWED_KEYS)
    if unknown:
        allowed = ", ".join(sorted(_JD_ALLOWED_KEYS))
        messages.append(f"unknown expected key(s): {', '.join(unknown)} (allowed: {allowed})")
    _check_jd_blocks(
        "kept",
        expected.get("kept"),
        [(block.start_line, block.kind.value) for block in actual.cleaned.kept],
        "kind",
        messages,
    )
    _check_jd_blocks(
        "removed",
        expected.get("removed"),
        [(block.start_line, block.reason.value) for block in actual.cleaned.removed],
        "reason",
        messages,
    )
    _check_jd_terms(expected.get("terms"), actual.terms, messages)
    _check_jd_absent_terms(expected.get("absent_terms"), actual.terms, messages)
    return messages


def _check_jd_blocks(
    key: str,
    value: object,
    actual_pairs: list[tuple[int, str]],
    field: str,
    messages: list[str],
) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        messages.append(f"{key!r} must be a list of block objects")
        return
    entries: list[tuple[int, str | None]] = []
    for entry in value:
        if not isinstance(entry, dict):
            messages.append(f"{key}: each entry must be an object with 'start_line' and '{field}'")
            return
        unknown = sorted(set(entry) - {"start_line", field})
        if unknown:
            messages.append(f"{key}: unknown key(s) in entry: {', '.join(unknown)}")
            return
        start = entry.get("start_line")
        if not isinstance(start, int) or isinstance(start, bool):
            messages.append(f"{key}: 'start_line' must be an integer")
            return
        field_value = entry.get(field)
        entries.append((start, field_value if isinstance(field_value, str) else None))
    if len(entries) != len(actual_pairs):
        messages.append(f"{key}: expected {len(entries)} blocks, got {len(actual_pairs)}")
        return
    for index, ((exp_start, exp_field), (act_start, act_field)) in enumerate(
        zip(entries, actual_pairs, strict=True)
    ):
        if exp_start != act_start:
            messages.append(f"{key}[{index}]: expected start_line {exp_start}, got {act_start}")
        if exp_field is not None and exp_field != act_field:
            messages.append(f"{key}[{index}]: expected {field} {exp_field!r}, got {act_field!r}")


def _check_jd_terms(value: object, actual: tuple[JdTerm, ...], messages: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        messages.append("'terms' must be a list of {canonical, weight?} objects")
        return
    by_canonical = {term.canonical: term for term in actual}
    for entry in value:
        if not isinstance(entry, dict):
            messages.append("terms: each entry must be an object with 'canonical' and 'weight'")
            return
        unknown = sorted(set(entry) - {"canonical", "weight"})
        if unknown:
            messages.append(f"terms: unknown key(s) in entry: {', '.join(unknown)}")
            return
        canonical = entry.get("canonical")
        if not isinstance(canonical, str) or not canonical:
            messages.append("terms: 'canonical' must be a non-empty string")
            return
        term = by_canonical.get(canonical)
        if term is None:
            messages.append(f"terms: {canonical!r} was not extracted")
            continue
        weight = entry.get("weight")
        if weight is None:
            continue
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            messages.append(f"terms: 'weight' for {canonical!r} must be a number")
            return
        if float(weight) != term.weight:
            messages.append(f"terms: {canonical!r} expected weight {weight}, got {term.weight}")


def _check_jd_absent_terms(value: object, actual: tuple[JdTerm, ...], messages: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        messages.append("'absent_terms' must be a list of canonical strings")
        return
    present = {term.canonical for term in actual}
    unexpected = [canonical for canonical in value if canonical in present]
    if unexpected:
        messages.append(f"absent_terms: unexpectedly extracted: {', '.join(unexpected)}")
