"""JD term extraction: dictionary-only matching over kept blocks (SPEC §3).

Scans KEPT blocks only — a term inside a removed Benefits or
equal-opportunity block never enters the denominator.

Matching is maximal munch: at every token position the longest
dictionary phrase wins, so "machine learning" never also counts as a
bare word and "spring boot" beats "spring". Tokens keep ".", "+", "#"
and "/" inside (node.js, c++, ci/cd); hyphens and underscores split
exactly like normalize_term, so "scikit-learn" matches as its two
normalized words.

exact_case entries (C, Go, R) match only with the dictionary's exact
capitalization. They — like ambiguous entries — are ordinary words, so
a bare single-word surface also needs context before it counts: either
the surface itself carries punctuation ("node.js", "express.js"), or
it spans more than one word ("spring boot", "microsoft excel"), or the
same line contains another non-ambiguous, non-exact-case dictionary
term. So "Experience with Excel, SQL and Python" hits, while "excel at
teamwork", "Express your ideas", "this spring" and a sentence-initial
"Go to market" do not.

Weights: an occurrence weighs 2.0 (required) when it sits in a
requirements block or its line contains a required cue (required,
must, minimum, proficiency in, strong); a preferred block or a line
with a preferred cue (nice to have, preferred, bonus, a plus) forces
1.0 and overrides required cues. Known limitation, documented in SPEC
§3: negation is not parsed, so "X is not required" contains the cue
and counts as required.

One JdTerm per canonical: the weight is the maximum over its
occurrences, occurrences are counted, and surface/line/context come
from the first occurrence with the maximum weight. Terms are ordered
by weight descending, occurrences descending, first line, canonical;
at most MAX_TERMS are kept, deterministically. Uncovered JD terms —
words the dictionary does not know — are the subject of a later step;
this step is dictionary-only.
"""

import re
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from ats_scanner.core.dictionary import SkillCategory, SkillEntry, normalize_term
from ats_scanner.core.jd import BlockKind, CleanedJd

MAX_TERMS = 60
REQUIRED_WEIGHT = 2.0
OTHER_WEIGHT = 1.0

_REQUIRED_CUE = re.compile(r"\b(?:required|must|minimum|strong|proficiency in)\b")
_PREFERRED_CUE = re.compile(r"\b(?:nice to have|preferred|bonus|a plus)\b")

# Tokens keep . + # / inside (node.js, c++, c#, ci/cd); everything else
# separates. Hyphens and underscores are turned to spaces first, exactly
# like normalize_term, so "scikit-learn" matches as two words.
_TOKEN = re.compile(r"[A-Za-z0-9.+#/]+")


class JdTerm(BaseModel):
    """One dictionary term found in the cleaned JD (SPEC §3 steps 2-5)."""

    model_config = ConfigDict(frozen=True)

    canonical: str = Field(min_length=1)
    category: SkillCategory
    weight: float
    required: bool
    occurrences: int = Field(ge=1)
    surface: str = Field(min_length=1)
    line: int = Field(ge=1)
    context: str


class _Token(NamedTuple):
    """One token: its char span in the line and its normalized text."""

    start: int
    end: int
    norm: str


class _Raw(NamedTuple):
    """One raw match before the ambiguity filter and weighting."""

    entry: SkillEntry
    surface: str
    words: int


class _Hit(NamedTuple):
    """One surviving occurrence, placed in the original text."""

    entry: SkillEntry
    surface: str
    line: int
    context: str


def _tokenize(line: str) -> list[_Token]:
    """Split a line into normalized tokens with their original char spans."""
    prepared = line.replace("-", " ").replace("_", " ")
    tokens: list[_Token] = []
    for match in _TOKEN.finditer(prepared):
        raw = match.group()
        text = raw.lstrip("/").rstrip("./")
        if not text:
            continue
        start = match.start() + len(raw) - len(raw.lstrip("/"))
        tokens.append(_Token(start, start + len(text), normalize_term(text)))
    return tokens


def _max_phrase_words(index: dict[str, SkillEntry]) -> int:
    return max((len(key.split()) for key in index), default=1)


def _exact_case_ok(entry: SkillEntry, key: str, surface: str) -> bool:
    """The surface must equal a dictionary spelling of the key verbatim."""
    return surface in [
        text for text in (entry.canonical, *entry.aliases) if normalize_term(text) == key
    ]


def _has_punctuation(surface: str) -> bool:
    return any(not (character.isalnum() or character.isspace()) for character in surface)


def _line_matches(line: str, index: dict[str, SkillEntry], max_words: int) -> list[_Raw]:
    """Maximal-munch matches on one line, then the ambiguity filter."""
    tokens = _tokenize(line)
    matches: list[_Raw] = []
    position = 0
    while position < len(tokens):
        found: _Raw | None = None
        for width in range(min(max_words, len(tokens) - position), 0, -1):
            key = " ".join(token.norm for token in tokens[position : position + width])
            entry = index.get(key)
            if entry is None:
                continue
            surface = line[tokens[position].start : tokens[position + width - 1].end]
            if entry.exact_case and not _exact_case_ok(entry, key, surface):
                continue
            found = _Raw(entry=entry, surface=surface, words=width)
            break
        if found is None:
            position += 1
            continue
        matches.append(found)
        position += found.words
    # An ambiguous (or exact-case) bare word needs an anchor: a
    # non-ambiguous, non-exact-case term elsewhere on the same line.
    anchored = any(
        match.entry.ambiguous is False and match.entry.exact_case is False for match in matches
    )
    return [
        match for match in matches if match.words > 1 or _has_punctuation(match.surface) or anchored
    ]


def _occurrence_weight(kind: BlockKind, line: str) -> float:
    lowered = line.lower()
    if kind is BlockKind.PREFERRED or _PREFERRED_CUE.search(lowered):
        return OTHER_WEIGHT
    if kind is BlockKind.REQUIREMENTS or _REQUIRED_CUE.search(lowered):
        return REQUIRED_WEIGHT
    return OTHER_WEIGHT


def extract_terms(cleaned: CleanedJd, index: dict[str, SkillEntry]) -> tuple[JdTerm, ...]:
    """Extract dictionary terms from the kept blocks (deterministic)."""
    if not index:
        return ()
    max_words = _max_phrase_words(index)
    counts: dict[str, int] = {}
    best: dict[str, tuple[_Hit, float]] = {}
    for block in cleaned.kept:
        for offset, line in enumerate(block.text.splitlines()):
            line_number = block.start_line + offset
            for match in _line_matches(line, index, max_words):
                canonical = match.entry.canonical
                counts[canonical] = counts.get(canonical, 0) + 1
                weight = _occurrence_weight(block.kind, line)
                current = best.get(canonical)
                if current is None or weight > current[1]:
                    hit = _Hit(
                        entry=match.entry, surface=match.surface, line=line_number, context=line
                    )
                    best[canonical] = (hit, weight)
    terms = [
        JdTerm(
            canonical=canonical,
            category=hit.entry.category,
            weight=weight,
            required=weight == REQUIRED_WEIGHT,
            occurrences=counts[canonical],
            surface=hit.surface,
            line=hit.line,
            context=hit.context,
        )
        for canonical, (hit, weight) in best.items()
    ]
    terms.sort(key=lambda term: (-term.weight, -term.occurrences, term.line, term.canonical))
    return tuple(terms[:MAX_TERMS])
