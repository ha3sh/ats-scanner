"""Column-order detection for one page of text (pure core; SPEC §4).

No pdfplumber here and no I/O: the caller (the PDF adapter) reduces a page
to frozen WordBox values (text, x0, x1, top, bottom) plus the page width,
and this module decides how the text is best read, or abstains.

v1 heuristic — deliberately conservative, "never guess", every doubt
returns None:

- At most two columns.
- A gutter is a vertical band at least 3% of the page width
  (MIN_GUTTER_FRACTION) that contains no word at all (checked word by
  word, so the rows of the two columns may share a baseline), and that
  starts after 5% of the page width and ends before 95% (MIN_SIDE_
  FRACTION), so there is genuinely text on both sides.
- Substantial text on both sides: each side holds at least 25% of the
  page's words (MIN_SIDE_WORD_FRACTION) and at least MIN_SIDE_LINES
  separate column lines.
- Fewer than MIN_WORDS words on the page: no verdict at all.
- Header: the lines above the topmost column line; each must span across
  the gutter (extend past both of its edges). Reads first, then the left
  column top to bottom, then the right.
- Ragged overlap — any non-header word whose span crosses the gutter — is
  impossible inside a real gutter, so crossing words disqualify it. A
  qualifying second gutter inside either side would mean three or more
  columns: None.

Either the evidence is strong enough to reorder the text, or the answer
is None and the row order stays the only view.
"""

from collections.abc import Sequence
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict

MIN_WORDS = 12
MIN_GUTTER_FRACTION = 0.03
MIN_SIDE_FRACTION = 0.05
MIN_SIDE_WORD_FRACTION = 0.25
MIN_SIDE_LINES = 5
MAX_HEADER_LINES = 4
SUB_GUTTER_CHECK_DEPTH = 2


class WordBox(BaseModel):
    """One word's bounding box, in PDF top-down coordinates."""

    model_config = ConfigDict(frozen=True)

    text: str
    x0: float
    x1: float
    top: float
    bottom: float


class _Line(NamedTuple):
    """A visual line: its words in x order, plus the line bounding box."""

    words: tuple[WordBox, ...]
    x0: float
    x1: float
    top: float


class _Gutter(NamedTuple):
    """A qualifying vertical whitespace band between two columns."""

    x0: float
    x1: float


def column_order(words: Sequence[WordBox], page_width: float) -> str | None:
    """Column-order text for one page, or None when the layout is not
    convincingly columnar.

    Every doubt returns None: few words, no, narrow, or crossed gutter,
    header lines that do not span the gutter, or more than two columns.
    Text is never reordered on weak evidence.
    """
    if page_width <= 0 or len(words) < MIN_WORDS:
        return None
    lines = _lines(words)
    for header_count in range(min(MAX_HEADER_LINES, len(lines) - 1) + 1):
        header, body = lines[:header_count], lines[header_count:]
        gutter = _best_gutter(body, page_width, SUB_GUTTER_CHECK_DEPTH)
        if gutter is None:
            continue
        if header_count > 0 and not all(
            line.x0 < gutter.x0 and line.x1 > gutter.x1 for line in header
        ):
            continue  # a header must span across the gutter
        body_words = [word for line in body for word in line.words]
        left_words = _side_words(body_words, gutter.x0, right=False)
        right_words = _side_words(body_words, gutter.x1, right=True)
        return _compose(lines[:header_count], left_words, right_words)
    return None


def _lines(words: Sequence[WordBox]) -> list[_Line]:
    """Cluster words into visual lines by vertical centre overlap."""
    ordered = sorted(words, key=(lambda box: (box.top, box.x0)))
    groups: list[list[WordBox]] = []
    for box in ordered:
        if groups:
            anchor = groups[-1][-1]
            half = min(box.bottom - box.top, anchor.bottom - anchor.top) / 2
            mid_a = (box.top + box.bottom) / 2
            mid_b = (anchor.top + anchor.bottom) / 2
            if abs(mid_a - mid_b) <= half:
                groups[-1].append(box)
                continue
        groups.append([box])
    return [
        _Line(
            words=tuple(sorted(group, key=(lambda box: box.x0))),
            x0=min(box.x0 for box in group),
            x1=max(box.x1 for box in group),
            top=min(box.top for box in group),
        )
        for group in groups
    ]


def _best_gutter(
    lines: Sequence[_Line],
    page_width: float,
    depth: int,
) -> _Gutter | None:
    """The widest qualifying gutter between two column word sets, or None.

    A gutter qualifies when it is wide enough and interior, the words on
    each side meet both thresholds, and (for depth > 0) neither side
    itself contains a qualifying gutter — three or more columns, so no
    two-column reading is offered.
    """
    body_words = [word for line in lines for word in line.words]
    candidates = _gaps(body_words)
    best: _Gutter | None = None
    best_width = 0.0
    for gutter in candidates:
        if not _wide_enough(gutter, page_width):
            continue
        if not _sides_substantial(body_words, gutter, page_width, depth):
            continue
        if gutter.x1 - gutter.x0 > best_width:
            best, best_width = gutter, gutter.x1 - gutter.x0
    return best


def _gaps(words: Sequence[WordBox]) -> list[_Gutter]:
    """Empty vertical bands between the merged word x-spans."""
    merged = _merged_spans(words)
    return [
        _Gutter(x0=merged[index][1], x1=merged[index + 1][0]) for index in range(len(merged) - 1)
    ]


def _wide_enough(gutter: _Gutter, page_width: float) -> bool:
    width = gutter.x1 - gutter.x0
    return (
        width >= MIN_GUTTER_FRACTION * page_width
        and gutter.x0 >= MIN_SIDE_FRACTION * page_width
        and gutter.x1 <= (1 - MIN_SIDE_FRACTION) * page_width
    )


def _side_words(words: Sequence[WordBox], edge: float, right: bool) -> list[WordBox]:
    """Words sitting entirely on one side of an x edge."""
    if right:
        return [word for word in words if word.x0 >= edge]
    return [word for word in words if word.x1 <= edge]


def _sides_substantial(
    body_words: Sequence[WordBox],
    gutter: _Gutter,
    page_width: float,
    depth: int,
) -> bool:
    """Both sides hold enough words and enough separate column lines, and
    neither side hides a second qualifying gutter (> two columns)."""
    if not body_words:
        return False
    for right in (False, True):
        edge = gutter.x1 if right else gutter.x0
        side = _side_words(body_words, edge, right=right)
        if len(side) < MIN_SIDE_WORD_FRACTION * len(body_words):
            return False
        if len(_lines(side)) < MIN_SIDE_LINES:
            return False
        if depth > 0 and len(_gaps(side)) > 0 and _best_gutter(_lines(side), page_width, depth - 1):
            return False
    return True


def _merged_spans(words: Sequence[WordBox]) -> list[list[float]]:
    """Union of word x-spans, merged: [start, end] per covered run."""
    spans = sorted((word.x0, word.x1) for word in words)
    merged: list[list[float]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _compose(
    header: Sequence[_Line],
    left_words: Sequence[WordBox],
    right_words: Sequence[WordBox],
) -> str:
    """Header block, then left column lines, then right column lines.

    Column lines are re-clustered from the side's words only, so a visual
    row shared by the two columns splits into one left and one right line.
    """
    blocks: list[list[_Line]] = [
        list(header) if header else [],
        _lines(left_words),
        _lines(right_words),
    ]
    text_blocks = []
    for block in blocks:
        if not block:
            continue
        text_blocks.append("\n".join(" ".join(word.text for word in line.words) for line in block))
    return "\n\n".join(text_blocks)
