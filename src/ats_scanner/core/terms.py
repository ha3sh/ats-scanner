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
capitalization, and — being ordinary words — need stricter context
than ambiguous entries. A bare match counts only when it is preceded
by a cue ("experience with", "experience in", "years of", "proficiency
in", "knowledge of", "skilled in", "programming in", "written in",
"using", "in", "with") or when it sits in a list: directly separated
by a comma, a slash, "and" or "or" from another non-ambiguous
dictionary term ("Four years of Go", "Python, R and SQL", "Go and
Rust" count; "Plan C" does not). A match joined by a hyphen or "&" to
the next or previous character never counts ("C-level", "R&D",
"Go-to-market", "R/W"). Known limitation: a bullet-initial "- Go for
control planes" has no cue and no list neighbour, so it is missed.
Ambiguous (non-exact_case) entries keep the line-anchor rule: the
surface itself carries punctuation ("node.js", "express.js"), or it
spans more than one word ("spring boot", "microsoft excel"), or the
same line contains another non-ambiguous, non-exact-case dictionary
term. So "Experience with Excel, SQL and Python" hits, while "excel at
teamwork", "Express your ideas" and "this spring" do not.

Plural matching: when a phrase's last token has no dictionary match,
the matcher retries once with its singular ("ies"->"y", then "es",
then "s"; last token only, and only when the exact form is not a key),
so "REST APIs" matches the "rest api" alias while "Kubernetes" is
never turned into "kubernete".

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

# A bare exact_case match counts when immediately preceded by one of
# these cues (single token, or a two-token phrase).
_EXACT_CASE_CUES = frozenset({"using", "in", "with"})
_EXACT_CASE_CUE_PHRASES = frozenset(
    {
        "experience with",
        "experience in",
        "years of",
        "proficiency in",
        "knowledge of",
        "skilled in",
        "programming in",
        "written in",
    }
)
# A match joined by one of these characters to the next or previous
# character is a compound, not a skill mention: C-level, R&D, R/W.
_JOINS = frozenset({"-", "&"})
_LIST_AND_OR = frozenset({"and", "or"})


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


class _Span(NamedTuple):
    """One maximal-munch match: its token span, entry, and surface."""

    start: int
    end: int
    entry: SkillEntry
    surface: str


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


def _singular(token: str) -> str:
    """One simple singular step: ies->y, then es, then s."""
    if token.endswith("ies") and len(token) > 3:
        return token[:-3] + "y"
    if token.endswith("es") and len(token) > 2:
        return token[:-2]
    if token.endswith("s") and len(token) > 1:
        return token[:-1]
    return token


def _longest_match(
    tokens: list[_Token], position: int, line: str, index: dict[str, SkillEntry], max_words: int
) -> _Span | None:
    """The longest dictionary phrase at this position, plural-retried."""
    for width in range(min(max_words, len(tokens) - position), 0, -1):
        span = tokens[position : position + width]
        key = " ".join(token.norm for token in span)
        entry = index.get(key)
        if entry is None:
            # Plural retry: singularize the last token only, and only
            # when the exact form is not a key (we are here because it
            # is not), so "REST APIs" matches "rest api" while
            # "Kubernetes" is never turned into "kubernete".
            singular = _singular(span[-1].norm)
            if singular != span[-1].norm:
                key = " ".join([*(token.norm for token in span[:-1]), singular])
                entry = index.get(key)
        if entry is None:
            continue
        surface = line[tokens[position].start : tokens[position + width - 1].end]
        if entry.exact_case and not _exact_case_ok(entry, key, surface):
            continue
        return _Span(position, position + width - 1, entry, surface)
    return None


def _is_anchor(entry: SkillEntry) -> bool:
    """Non-ambiguous, non-exact-case: licenses bare words on its line."""
    return entry.ambiguous is False and entry.exact_case is False


def _plain(line: str, start: int, end: int) -> bool:
    return not any(character in _JOINS for character in line[start:end])


def _anchor_at(spans: list[_Span], token_index: int, side: str) -> bool:
    return any(getattr(span, side) == token_index and _is_anchor(span.entry) for span in spans)


def _list_side(
    tokens: list[_Token],
    span: _Span,
    line: str,
    spans: list[_Span],
    left: bool,
) -> bool:
    """True when the match is list-separated from an anchor term.

    Direct: "SQL, R" (comma or slash in the gap). Via a connector:
    "SQL and R" (an "and"/"or" token, anchor on the other side). A
    standalone slash token between them ("SQL / R") also separates.
    """
    step = -1 if left else 1
    edge = span.start if left else span.end
    connector_index = edge + step
    beyond_index = edge + 2 * step
    beyond = 0 <= beyond_index < len(tokens)
    if beyond and tokens[connector_index].norm in _LIST_AND_OR | {"/"}:
        anchor_side = "end" if left else "start"
        return _anchor_at(spans, beyond_index, anchor_side) and _plain(
            line,
            min(tokens[beyond_index].end, tokens[connector_index].start),
            max(tokens[beyond_index].end, tokens[connector_index].start),
        )
    if 0 <= connector_index < len(tokens):
        gap = (
            line[tokens[connector_index].end : tokens[edge].start]
            if left
            else line[tokens[edge].end : tokens[connector_index].start]
        )
        anchor_side = "end" if left else "start"
        return ("," in gap or "/" in gap) and _anchor_at(spans, connector_index, anchor_side)
    return False


def _exact_case_licensed(tokens: list[_Token], span: _Span, line: str, spans: list[_Span]) -> bool:
    """The stricter context rule for bare exact_case matches (C, Go, R)."""
    first, last = tokens[span.start], tokens[span.end]
    before = line[first.start - 1] if first.start > 0 else ""
    after = line[last.end] if last.end < len(line) else ""
    if before in _JOINS or after in _JOINS:
        return False
    if span.start >= 1 and tokens[span.start - 1].norm in _EXACT_CASE_CUES:
        return True
    if span.start >= 2 and (
        f"{tokens[span.start - 2].norm} {tokens[span.start - 1].norm}" in _EXACT_CASE_CUE_PHRASES
    ):
        return True
    return _list_side(tokens, span, line, spans, left=True) or _list_side(
        tokens, span, line, spans, left=False
    )


def _line_matches(line: str, index: dict[str, SkillEntry], max_words: int) -> list[_Raw]:
    """Maximal-munch matches on one line, then the context filters."""
    tokens = _tokenize(line)
    spans: list[_Span] = []
    position = 0
    while position < len(tokens):
        span = _longest_match(tokens, position, line, index, max_words)
        if span is None:
            position += 1
            continue
        spans.append(span)
        position = span.end + 1
    # Ambiguous bare words need an anchor: a non-ambiguous,
    # non-exact-case term elsewhere on the same line.
    anchored = any(_is_anchor(span.entry) for span in spans)
    survivors: list[_Raw] = []
    for span in spans:
        if span.entry.exact_case:
            licensed = _exact_case_licensed(tokens, span, line, spans)
        elif span.entry.ambiguous:
            licensed = span.end > span.start or _has_punctuation(span.surface) or anchored
        else:
            licensed = True
        if licensed:
            survivors.append(
                _Raw(entry=span.entry, surface=span.surface, words=span.end - span.start + 1)
            )
    return survivors


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
