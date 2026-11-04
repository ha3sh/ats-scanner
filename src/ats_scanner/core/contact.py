"""Contact detection: email, phone and LinkedIn (pure; SPEC §4).

Line-based over the chosen reading order. Values are returned in the
report only — never logged or echoed elsewhere (SPEC §6).

Phone: a loose international matcher. A candidate is a maximal run of
digits and phone punctuation (spaces, dots, dashes, en/em dashes,
parentheses, a single leading plus) containing 9 to 15 digits in total,
not glued to a longer alphanumeric token — so date ranges ("2014 -
2018"), years, version strings ("3.12.4") and short numbers never match.
Email: trailing punctuation stripped. LinkedIn: scheme and "www."
stripped, trailing punctuation removed.
"""

import re
from collections.abc import Callable, Sequence

from ats_scanner.core.report import ContactInfo, ContactItem

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# One leading "+", an optional opening parenthesis, digits, and phone
# punctuation between digits.
_PHONE = re.compile(r"\+?\(?[0-9][0-9\s().\-\u2013\u2014]*[0-9]")

_LINKEDIN = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+")

_TRIM = " \t.,;:!?"


def _first(pages: Sequence[str], find: Callable[[str], str | None]) -> ContactItem:
    for page_number, text in enumerate(pages, start=1):
        for line_number, line in enumerate(text.splitlines(), start=1):
            value = find(line)
            if value is not None:
                return ContactItem(found=True, value=value, page=page_number, line=line_number)
    return ContactItem(found=False)


def _email_in(line: str) -> str | None:
    match = _EMAIL.search(line)
    if match is None:
        return None
    return match.group(0).rstrip(_TRIM)


def _phone_in(line: str) -> str | None:
    for match in _PHONE.finditer(line):
        candidate = match.group(0)
        before = line[match.start() - 1] if match.start() > 0 else " "
        after = line[match.end()] if match.end() < len(line) else " "
        if before.isalnum() or after.isalnum():
            continue  # glued to a longer token (versions, identifiers)
        digits = sum(character.isdigit() for character in candidate)
        if not 9 <= digits <= 15:
            continue
        return candidate.strip().rstrip(_TRIM).lstrip(_TRIM)
    return None


def _linkedin_in(line: str) -> str | None:
    match = _LINKEDIN.search(line)
    if match is None:
        return None
    value = re.sub(r"^(?:https?://)?(?:www\.)?", "", match.group(0))
    return value.rstrip("/" + _TRIM)


def find_contact(pages: Sequence[str]) -> ContactInfo:
    """First email, phone and LinkedIn occurrence across the pages."""
    return ContactInfo(
        email=_first(pages, _email_in),
        phone=_first(pages, _phone_in),
        linkedin=_first(pages, _linkedin_in),
    )
