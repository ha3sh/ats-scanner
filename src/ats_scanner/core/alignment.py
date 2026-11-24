"""Informational title, seniority and experience alignment (pure; SPEC §3).

Every check has three honest states: aligned, differs, or unknown. "unknown"
is the default whenever either side gives no clear signal — this module never
guesses, never reports pass/fail, and never touches the score. Each state
carries the exact JD line (1-based) and resume line (page + 1-based line) it
came from, so the UI can show why it was said.

Conservative choices where the SPEC is silent:

- Title: role nouns (engineer, developer, ...) must appear on both sides;
  company suffixes, case, punctuation, "Sr."/"Jr." and level suffixes (II/III)
  are normalized away before token comparison. Equal or subset token sets are
  aligned; otherwise both sides are clear and it is "differs".
- Seniority: the fixed ladder intern → junior → mid → senior → lead →
  principal; II/III/IV map to mid/senior/lead. More than one distinct cue on
  a side is ambiguous and becomes unknown, not a guess.
- Experience: JD "3+ years" / "2-4 years" / "three years" give a minimum;
  resume explicit "X years of experience" wins over derived dates. Date
  ranges are merged (no double counting); an open "present" ends in December
  of the latest year the resume itself mentions (never the wall clock, so
  reports stay deterministic). Bare year runs ("2013") are not claims.
  A resume meeting the JD minimum is aligned, even when it exceeds it.
"""

import re
import unicodedata
from collections.abc import Sequence
from typing import NamedTuple

from ats_scanner.core.jd import CleanedJd
from ats_scanner.core.report import (
    Alignment,
    AlignmentCheck,
    AlignmentStatus,
    JdEvidence,
    ResumeEvidence,
    SectionFinding,
    SectionName,
)

_ROLE_NOUNS = frozenset(
    {
        "engineer",
        "developer",
        "architect",
        "analyst",
        "scientist",
        "manager",
        "designer",
        "consultant",
        "administrator",
        "specialist",
        "lead",
    }
)
_ABBREVIATIONS = {
    "sr": "senior",
    "jr": "junior",
    "eng": "engineer",
    "dev": "developer",
    "mgr": "manager",
}
_LEVELS = {
    "intern": 0,
    "junior": 1,
    "mid": 2,
    "midlevel": 2,
    "senior": 3,
    "lead": 4,
    "principal": 5,
    "ii": 2,
    "iii": 3,
    "iv": 4,
}
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}
_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_NUMBER_PATTERN = rf"(?:\d{{1,2}}|{'|'.join(_NUMBER_WORDS)})"
_YEARS = re.compile(
    rf"\b(?P<first>{_NUMBER_PATTERN})\s*(?P<plus>\+)?\s*"
    rf"(?:(?P<range>-|–|—|to)\s*(?P<second>{_NUMBER_PATTERN})\s*)?"
    r"(?:years?|yrs?)\b",
    re.IGNORECASE,
)
_DATE_PATTERN = rf"(?:(?:{_MONTH_PATTERN})\s+)?(?:19|20)\d{{2}}"
_DATE_RANGE = re.compile(
    rf"(?P<start>{_DATE_PATTERN})\s*(?:-|–|—|to)\s*"
    rf"(?P<end>{_DATE_PATTERN}|present|current|now)",
    re.IGNORECASE,
)
_OPEN_END = frozenset({"present", "current", "now"})


class _JdLine(NamedTuple):
    text: str
    line: int


class _ResumeLine(NamedTuple):
    text: str
    page: int
    line: int


class _YearsClaim(NamedTuple):
    minimum: int
    maximum: int | None = None


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#]+", unicodedata.normalize("NFKC", text).lower())


def _jd_lines(cleaned: CleanedJd) -> tuple[_JdLine, ...]:
    lines: list[_JdLine] = []
    for block in cleaned.kept:
        for offset, text in enumerate(block.text.splitlines()):
            stripped = text.strip()
            if stripped:
                lines.append(_JdLine(stripped, block.start_line + offset))
    return tuple(lines)


def _resume_lines(pages: Sequence[str]) -> tuple[_ResumeLine, ...]:
    lines: list[_ResumeLine] = []
    for page_number, text in enumerate(pages, start=1):
        for line_number, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            if stripped:
                lines.append(_ResumeLine(stripped, page_number, line_number))
    return tuple(lines)


def _title_core(text: str) -> str:
    """Drop company/location suffixes; keep the role itself."""
    return re.split(
        r"\s*[|;·,]\s*|\s+-\s+|\s+(?:at|for|with)\s+", text, maxsplit=1, flags=re.IGNORECASE
    )[0]


def _title_tokens(text: str) -> frozenset[str]:
    tokens = {_ABBREVIATIONS.get(word, word) for word in _words(_title_core(text))}
    return frozenset(token for token in tokens if token.isalpha() and token not in _LEVELS)


def _role_tokens(text: str) -> frozenset[str]:
    return _title_tokens(text) & _ROLE_NOUNS


def _jd_title(cleaned: CleanedJd) -> _JdLine | None:
    """The first kept block's title, joining a two-line title."""
    for block in cleaned.kept:
        lines = [
            _JdLine(text.strip(), block.start_line + offset)
            for offset, text in enumerate(block.text.splitlines())
            if text.strip()
        ]
        if not lines:
            continue
        text = lines[0].text
        if len(lines) > 1 and not lines[1].text.endswith(":") and len(lines[1].text.split()) <= 6:
            text = f"{text} {lines[1].text}"
        return _JdLine(text, lines[0].line)
    return None


def _resume_title(
    lines: Sequence[_ResumeLine], sections: Sequence[SectionFinding]
) -> _ResumeLine | None:
    """Most recent title from experience, else the headline (both conservative."""
    experience = next(
        (
            finding
            for finding in sections
            if finding.name is SectionName.EXPERIENCE
            and finding.found
            and finding.page is not None
            and finding.line is not None
        ),
        None,
    )
    if experience is not None and experience.page is not None and experience.line is not None:
        after_heading = (
            line for line in lines if (line.page, line.line) > (experience.page, experience.line)
        )
        for line in after_heading:
            if _role_tokens(line.text):
                return line
    for line in lines[:5]:
        if _role_tokens(line.text):
            return line
    return None


def _levels(text: str) -> frozenset[int]:
    return frozenset(
        _LEVELS[_ABBREVIATIONS.get(word, word)]
        for word in _words(text)
        if _ABBREVIATIONS.get(word, word) in _LEVELS
    )


def _jd_seniority(cleaned: CleanedJd, title: _JdLine | None) -> tuple[int, _JdLine] | None:
    if title is not None:
        levels = _levels(title.text)
        if len(levels) == 1:
            return next(iter(levels)), title
    found = [(level, line) for line in _jd_lines(cleaned) for level in sorted(_levels(line.text))]
    distinct = {level for level, _ in found}
    if len(distinct) == 1:
        level = next(iter(distinct))
        return level, next(line for candidate, line in found if candidate == level)
    return None


def _resume_seniority(
    lines: Sequence[_ResumeLine], title: _ResumeLine | None
) -> tuple[int, _ResumeLine] | None:
    candidates: Sequence[_ResumeLine] = (title,) if title is not None else lines[:5]
    found = [(level, line) for line in candidates for level in sorted(_levels(line.text))]
    distinct = {level for level, _ in found}
    if len(distinct) == 1:
        level = next(iter(distinct))
        return level, next(line for candidate, line in found if candidate == level)
    return None


def _number_value(token: str) -> int:
    lowered = token.lower()
    return _NUMBER_WORDS.get(lowered, int(lowered) if lowered.isdigit() else 0)


def _parse_years(text: str) -> tuple[_YearsClaim, ...]:
    claims: list[_YearsClaim] = []
    for match in _YEARS.finditer(text):
        first = _number_value(match.group("first"))
        if first == 0:
            continue
        second = match.group("second")
        maximum = _number_value(second) if match.group("range") and second else None
        claim = _YearsClaim(first, maximum if maximum else None)
        if claim not in claims:
            claims.append(claim)
    return tuple(claims)


def _jd_experience(cleaned: CleanedJd) -> tuple[_YearsClaim, _JdLine] | None:
    claims: list[tuple[_YearsClaim, _JdLine]] = [
        (claim, line) for line in _jd_lines(cleaned) for claim in _parse_years(line.text)
    ]
    distinct = {claim for claim, _ in claims}
    if len(distinct) == 1:
        claim = next(iter(distinct))
        return claim, next(line for candidate, line in claims if candidate == claim)
    return None


def _parse_date(token: str, *, end: bool = False) -> int:
    """Map a date to an absolute month index; month-less dates span the year."""
    words = _words(token)
    year = next(
        (int(word) for word in words if len(word) == 4 and word[:2] in {"19", "20"}),
        0,
    )
    month = next((_MONTHS[word] for word in words if word in _MONTHS), None)
    return year * 12 + ((month if month is not None else 12 if end else 1) - 1)


def _derived_months(lines: Sequence[_ResumeLine]) -> tuple[int, _ResumeLine] | None:
    """Total months from merged date ranges, or None without a clear range."""
    parsed: list[tuple[int, int | None, _ResumeLine]] = []
    years: set[int] = set()
    for line in lines:
        for match in _DATE_RANGE.finditer(line.text):
            start = _parse_date(match.group("start"))
            years.add(start // 12)
            end_token = match.group("end")
            if end_token.lower() in _OPEN_END:
                parsed.append((start, None, line))
            else:
                end = _parse_date(end_token, end=True)
                years.add(end // 12)
                parsed.append((start, end, line))
    if not parsed or not years:
        return None
    reference_end = max(years) * 12 + 11  # December of the latest resume year
    spans = sorted(
        (start, (end if end is not None else reference_end) + 1, line)
        for start, end, line in parsed
        if end is None or end >= start
    )
    if not spans:
        return None
    first, last, evidence = spans[0]
    total = 0
    for start, end, _ in spans[1:]:
        if start <= last:
            last = max(last, end)
        else:
            total += last - first
            first, last = start, end
    total += last - first
    return total, evidence


def _resume_experience(
    lines: Sequence[_ResumeLine],
) -> tuple[float, _ResumeLine] | None:
    claims: list[tuple[_YearsClaim, _ResumeLine]] = [
        (claim, line)
        for line in lines
        if "experien" in line.text.lower()
        for claim in _parse_years(line.text)
    ]
    distinct = {claim for claim, _ in claims}
    if len(distinct) == 1:
        claim = next(iter(distinct))
        line = next(source for candidate, source in claims if candidate == claim)
        return float(claim.minimum), line
    derived = _derived_months(lines)
    if derived is not None:
        months, line = derived
        return months / 12, line
    return None


def _jd_evidence(line: _JdLine | None) -> JdEvidence:
    if line is None:
        return JdEvidence()
    return JdEvidence(text=line.text, line=line.line)


def _resume_evidence(line: _ResumeLine | None) -> ResumeEvidence:
    if line is None:
        return ResumeEvidence()
    return ResumeEvidence(text=line.text, page=line.page, line=line.line)


def _check(
    status: AlignmentStatus, jd: _JdLine | None, resume: _ResumeLine | None
) -> AlignmentCheck:
    return AlignmentCheck(
        status=status,
        jd_evidence=_jd_evidence(jd),
        resume_evidence=_resume_evidence(resume),
    )


def check_alignment(
    cleaned: CleanedJd,
    resume_pages: Sequence[str],
    sections: Sequence[SectionFinding],
) -> Alignment:
    """Compare JD and resume on title, seniority and experience (informational)."""
    resume_all = _resume_lines(resume_pages)
    jd_title = _jd_title(cleaned)
    resume_title = _resume_title(resume_all, sections)

    jd_tokens = _title_tokens(jd_title.text) if jd_title is not None else frozenset()
    resume_tokens = _title_tokens(resume_title.text) if resume_title is not None else frozenset()
    if (
        jd_title is None
        or resume_title is None
        or not _role_tokens(jd_title.text)
        or not _role_tokens(resume_title.text)
    ):
        title = _check(AlignmentStatus.UNKNOWN, None, None)
    elif jd_tokens == resume_tokens or jd_tokens <= resume_tokens or resume_tokens <= jd_tokens:
        title = _check(AlignmentStatus.ALIGNED, jd_title, resume_title)
    else:
        title = _check(AlignmentStatus.DIFFERS, jd_title, resume_title)

    jd_seniority = _jd_seniority(cleaned, jd_title)
    resume_seniority = _resume_seniority(resume_all, resume_title)
    if jd_seniority is None or resume_seniority is None:
        seniority = _check(AlignmentStatus.UNKNOWN, None, None)
    else:
        jd_level, jd_line = jd_seniority
        resume_level, resume_line = resume_seniority
        state = AlignmentStatus.ALIGNED if jd_level == resume_level else AlignmentStatus.DIFFERS
        seniority = _check(state, jd_line, resume_line)

    jd_experience = _jd_experience(cleaned)
    resume_experience = _resume_experience(resume_all)
    if jd_experience is None or resume_experience is None:
        experience = _check(AlignmentStatus.UNKNOWN, None, None)
    else:
        claim, jd_line = jd_experience
        years, resume_line = resume_experience
        state = AlignmentStatus.ALIGNED if years >= claim.minimum else AlignmentStatus.DIFFERS
        experience = _check(state, jd_line, resume_line)

    return Alignment(title=title, seniority=seniority, experience=experience)
