"""Resume matching and near misses over the chosen reading order (pure; SPEC §3).

The JD and the resume use ONE matcher: both call `terms._line_matches`, so
maximal munch, plural retry, alias and exact_case rules cannot drift.

Before scanning, the chosen page text is normalized with a character map:
NFKC (ligatures included), soft hyphens removed, hyphenated line wraps
("Post-\\ngreSQL") joined, and other line breaks turned into spaces so a term
split over two lines still matches. Every normalized character carries the
offsets of the original character it came from, so evidence spans point back
into the text the UI actually renders.

Near misses are deliberately conservative and NEVER counted: one word per
JD term, at least six characters, edit distance 1 (2 from ten characters),
no exact_case terms, and never a variant that normalizes to a different
dictionary entry or alias (Java is not a near miss for JavaScript).
"""

import re
import unicodedata
from bisect import bisect_right
from collections.abc import Sequence
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from ats_scanner.core.dictionary import SkillEntry, normalize_term
from ats_scanner.core.report import (
    MatchedTerm,
    MissingTerm,
    NearMiss,
    ResumeSpan,
    SectionFinding,
    SectionName,
    TermAnalysis,
)
from ats_scanner.core.terms import JdTerm, _line_matches, max_phrase_words

_WORD = re.compile(r"[A-Za-z0-9.+#/]+")


class ResumeMatch(BaseModel):
    """One term found in the resume, with its original-text evidence."""

    model_config = ConfigDict(frozen=True)

    entry: SkillEntry
    surface: str = Field(min_length=1)
    page: int = Field(ge=1)
    line: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    context: str
    section: SectionName | None = None


class PreparedText(NamedTuple):
    """Normalized text plus a map back to the original character offsets."""

    text: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]


def _join_wrap(text: str, position: int) -> bool:
    """True when the '-' before `position` is followed by a line break."""
    saw_break = False
    while position < len(text):
        character = text[position]
        if character in "\r\n":
            saw_break = True
        elif not character.isspace():
            break
        position += 1
    return saw_break and position < len(text)


def prepare_text(text: str) -> PreparedText:
    """Normalize for matching while keeping exact offsets into `text`."""
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    position = 0
    while position < len(text):
        original = text[position]
        if original == "\u00ad":  # soft hyphen: invisible, never a word break
            position += 1
            continue
        if original == "-" and _join_wrap(text, position + 1):
            position += 1
            while position < len(text) and text[position].isspace():
                position += 1
            continue
        for piece in unicodedata.normalize("NFKC", original):
            characters.append(" " if piece in "\r\n\t" else piece)
            starts.append(position)
            ends.append(position + 1)
        position += 1
    return PreparedText("".join(characters), tuple(starts), tuple(ends))


def _line_starts(text: str) -> list[int]:
    return [0, *(index + 1 for index, character in enumerate(text) if character == "\n")]


def _line_at(starts: list[int], offset: int) -> int:
    return bisect_right(starts, offset)


def _context_at(text: str, line_starts: list[int], start: int, end: int) -> str:
    """The original line(s) holding a span, for human-readable evidence."""
    first = line_starts[_line_at(line_starts, start) - 1]
    next_line = _line_at(line_starts, end)
    last = line_starts[next_line] if next_line < len(line_starts) else len(text)
    return text[first:last].strip()


def _section_at(sections: Sequence[SectionFinding], page: int, line: int) -> SectionName | None:
    """The latest section heading at or before this page/line (if any)."""
    candidates = [
        finding
        for finding in sections
        if finding.found and finding.page is not None and finding.line is not None
        if (finding.page, finding.line) <= (page, line)
    ]
    if not candidates:
        return None
    latest = max(
        candidates,
        key=lambda finding: (
            finding.page or 0,
            finding.line or 0,
            list(SectionName).index(finding.name),
        ),
    )
    return latest.name


def match_resume(
    pages: Sequence[str],
    sections: Sequence[SectionFinding],
    index: dict[str, SkillEntry],
) -> tuple[ResumeMatch, ...]:
    """Match dictionary terms over the text the pipeline chose to read."""
    if not index:
        return ()
    max_words = max_phrase_words(index)
    line_starts = [_line_starts(page) for page in pages]
    matches: list[ResumeMatch] = []
    for page_number, (original, starts_of_lines) in enumerate(
        zip(pages, line_starts, strict=True), 1
    ):
        prepared = prepare_text(original)
        for hit in _line_matches(prepared.text, index, max_words):
            start = prepared.starts[hit.start]
            end = prepared.ends[hit.end - 1]
            line = _line_at(starts_of_lines, start)
            matches.append(
                ResumeMatch(
                    entry=hit.entry,
                    surface=hit.surface,
                    page=page_number,
                    line=line,
                    start_char=start,
                    end_char=end,
                    context=_context_at(original, starts_of_lines, start, end),
                    section=_section_at(sections, page_number, line),
                )
            )
    matches.sort(
        key=lambda match: (match.page, match.line, match.start_char, match.entry.canonical)
    )
    return tuple(matches)


def _edit_distance(first: str, second: str, limit: int) -> int:
    """Levenshtein distance, capped; stdlib only, short words only."""
    if abs(len(first) - len(second)) > limit:
        return limit + 1
    previous = list(range(len(second) + 1))
    for row, left_character in enumerate(first, 1):
        current = [row]
        for column, right_character in enumerate(second, 1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def near_misses(
    terms: Sequence[JdTerm],
    pages: Sequence[str],
    index: dict[str, SkillEntry],
) -> tuple[NearMiss, ...]:
    """Close resume variants for unmatched terms, shown but never counted."""
    if not index:
        return ()
    # One pass over the resume, bucketed by word length: a term only looks
    # at buckets within its allowed distance, so this stays linear in size.
    variants: dict[str, str] = {}
    buckets: dict[int, list[str]] = {}
    for page in pages:
        prepared = prepare_text(page)
        for token in _WORD.findall(prepared.text):
            normalized = normalize_term(token)
            if normalized in variants:
                continue
            variants[normalized] = token
            buckets.setdefault(len(normalized), []).append(normalized)

    found: list[NearMiss] = []
    for term in terms:
        target = normalize_term(term.canonical)
        if " " in target or len(target) < 6:
            continue
        entry = index.get(target)
        if entry is None or entry.exact_case:
            continue
        allowed = 2 if len(target) >= 10 else 1
        best: tuple[int, str] | None = None
        for length in range(len(target) - allowed, len(target) + allowed + 1):
            for candidate in buckets.get(length, ()):
                known = index.get(candidate)
                if candidate == target or (known is not None and known is not entry):
                    continue
                distance = _edit_distance(target, candidate, allowed)
                if 1 <= distance <= allowed and (best is None or (distance, candidate) < best):
                    best = (distance, candidate)
        if best is not None:
            distance, candidate = best
            found.append(
                NearMiss(
                    term=term.surface,
                    found_variant=variants[candidate],
                    distance=distance,
                    counted=False,
                )
            )
    return tuple(found)


def build_term_analysis(
    terms: Sequence[JdTerm],
    matches: Sequence[ResumeMatch],
    pages: Sequence[str],
    index: dict[str, SkillEntry],
) -> TermAnalysis:
    """Explain every JD term; near misses are added but never scored."""
    first_by_canonical: dict[str, ResumeMatch] = {}
    for resume_match in matches:
        first_by_canonical.setdefault(resume_match.entry.canonical, resume_match)

    matched: list[MatchedTerm] = []
    missing: list[JdTerm] = []
    for term in terms:
        entry = index.get(normalize_term(term.canonical))
        found = first_by_canonical.get(entry.canonical) if entry is not None else None
        if found is None:
            missing.append(term)
            continue
        matched.append(
            MatchedTerm(
                term=term.surface,
                canonical=term.canonical,
                weight=term.weight,
                jd_context=term.context,
                resume_context=found.context,
                resume_span=ResumeSpan(
                    page=found.page,
                    line=found.line,
                    start_char=found.start_char,
                    end_char=found.end_char,
                    section=found.section,
                ),
            )
        )
    return TermAnalysis(
        matched=tuple(matched),
        missing=tuple(
            MissingTerm(term=term.surface, weight=term.weight, jd_context=term.context)
            for term in missing
        ),
        near_misses=near_misses(missing, pages, index),
    )
