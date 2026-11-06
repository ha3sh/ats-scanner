"""JD cleaning: strip boilerplate blocks (pure; SPEC §3 step 1).

Conservative: only WHOLE blocks are ever removed — a block under a
recognised boilerplate heading, or a standalone paragraph dominated by
equal-opportunity phrases (MIN_EEO_PHRASES or more distinct phrases).
A requirement block that merely mentions "benefits" or "diversity"
stays: it sits under a content heading, or carries a single mention.

Blocks are heading-led sections (a recognised heading plus the
paragraphs that follow it, up to the next recognised heading or
heading-like line) or blank-line-separated paragraphs. A heading-like
line we do not recognise (at most 6 words, ends with ":") ends the
current section; its paragraph is kept as kind "other". Text before any
heading is kind "other" and kept unless EEO-dominated. Original 1-based
line numbers are preserved so later evidence spans can point into the
pasted text.
"""

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class BlockKind(StrEnum):
    """Kinds of kept blocks."""

    REQUIREMENTS = "requirements"
    PREFERRED = "preferred"
    RESPONSIBILITIES = "responsibilities"
    OTHER = "other"


class RemovalReason(StrEnum):
    """Why a block was removed."""

    EQUAL_OPPORTUNITY = "equal_opportunity"
    BENEFITS = "benefits"
    ABOUT_COMPANY = "about_company"
    HOW_TO_APPLY = "how_to_apply"


class KeptBlock(BaseModel):
    """A block that stays, with its place in the original text."""

    model_config = ConfigDict(frozen=True)

    text: str
    start_line: int = Field(ge=1)
    kind: BlockKind


class RemovedBlock(BaseModel):
    """A block that was removed, with its place in the original text."""

    model_config = ConfigDict(frozen=True)

    text: str
    start_line: int = Field(ge=1)
    reason: RemovalReason


class CleanedJd(BaseModel):
    """The JD split into kept and removed blocks (SPEC §3 step 1)."""

    model_config = ConfigDict(frozen=True)

    kept: tuple[KeptBlock, ...]
    removed: tuple[RemovedBlock, ...]

    @property
    def cleaned_text(self) -> str:
        """The kept blocks, joined — the auditable denominator input."""
        return "\n\n".join(block.text for block in self.kept)


# One alias table: normalized heading -> the kind it starts (BlockKind)
# or the reason the whole section under it is removed (RemovalReason).
JD_HEADING_ALIASES: dict[str, BlockKind | RemovalReason] = {
    # requirements
    "requirements": BlockKind.REQUIREMENTS,
    "required": BlockKind.REQUIREMENTS,
    "qualifications": BlockKind.REQUIREMENTS,
    "required qualifications": BlockKind.REQUIREMENTS,
    "minimum qualifications": BlockKind.REQUIREMENTS,
    "required skills": BlockKind.REQUIREMENTS,
    "required experience": BlockKind.REQUIREMENTS,
    "must have": BlockKind.REQUIREMENTS,
    # preferred
    "preferred": BlockKind.PREFERRED,
    "preferred qualifications": BlockKind.PREFERRED,
    "preferred skills": BlockKind.PREFERRED,
    "nice to have": BlockKind.PREFERRED,
    "bonus": BlockKind.PREFERRED,
    "bonus points": BlockKind.PREFERRED,
    # responsibilities
    "responsibilities": BlockKind.RESPONSIBILITIES,
    "key responsibilities": BlockKind.RESPONSIBILITIES,
    "your responsibilities": BlockKind.RESPONSIBILITIES,
    "what you will do": BlockKind.RESPONSIBILITIES,
    "what you'll do": BlockKind.RESPONSIBILITIES,
    # benefits boilerplate
    "benefits": RemovalReason.BENEFITS,
    "benefits and perks": RemovalReason.BENEFITS,
    "perks": RemovalReason.BENEFITS,
    "perks and benefits": RemovalReason.BENEFITS,
    "compensation and benefits": RemovalReason.BENEFITS,
    "what we offer": RemovalReason.BENEFITS,
    # about-company boilerplate
    "about us": RemovalReason.ABOUT_COMPANY,
    "about the company": RemovalReason.ABOUT_COMPANY,
    "our company": RemovalReason.ABOUT_COMPANY,
    "who we are": RemovalReason.ABOUT_COMPANY,
    "our mission": RemovalReason.ABOUT_COMPANY,
    "our story": RemovalReason.ABOUT_COMPANY,
    # how-to-apply boilerplate
    "how to apply": RemovalReason.HOW_TO_APPLY,
    "apply now": RemovalReason.HOW_TO_APPLY,
    "to apply": RemovalReason.HOW_TO_APPLY,
    "application process": RemovalReason.HOW_TO_APPLY,
    # equal-opportunity boilerplate
    "equal opportunity": RemovalReason.EQUAL_OPPORTUNITY,
    "equal opportunity employer": RemovalReason.EQUAL_OPPORTUNITY,
    "equal employment opportunity": RemovalReason.EQUAL_OPPORTUNITY,
    "eeo": RemovalReason.EQUAL_OPPORTUNITY,
    "eeo statement": RemovalReason.EQUAL_OPPORTUNITY,
    "diversity": RemovalReason.EQUAL_OPPORTUNITY,
    "diversity and inclusion": RemovalReason.EQUAL_OPPORTUNITY,
    "inclusion and diversity": RemovalReason.EQUAL_OPPORTUNITY,
}

# A standalone paragraph counts as EEO-dominated when this many DISTINCT
# phrases appear in it. One phrase is a mere mention and stays.
EQUAL_OPPORTUNITY_PHRASES: tuple[str, ...] = (
    "equal opportunity",
    "equal employment opportunity",
    "eeo",
    "affirmative action",
    "without regard to",
    "veteran status",
    "protected status",
    "protected characteristic",
    "national origin",
    "gender identity",
    "sexual orientation",
    "reasonable accommodation",
    "diversity",
    "inclusion",
)
MIN_EEO_PHRASES = 2

# A heading-like line we do not recognise: at most this many words and
# ending with ":". It ends the current section instead of being absorbed.
MAX_UNRECOGNISED_HEADING_WORDS = 6

_HEADING_STRIP = " \t-*\u2013\u2014.,;:!?"


def _normalize_heading(line: str) -> str:
    """Lowercase, trimmed, edge punctuation and bullets stripped."""
    return " ".join(line.strip().strip(_HEADING_STRIP).lower().split())


def _paragraph_spans(lines: Sequence[str]) -> list[tuple[int, int]]:
    """Inclusive (start, end) indices of the non-blank line runs."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, line in enumerate(lines):
        if line.strip():
            if start is None:
                start = index
        elif start is not None:
            spans.append((start, index - 1))
            start = None
    if start is not None:
        spans.append((start, len(lines) - 1))
    return spans


def _equal_opportunity_phrases_in(text: str) -> set[str]:
    lowered = text.lower()
    return {phrase for phrase in EQUAL_OPPORTUNITY_PHRASES if phrase in lowered}


def _is_unrecognised_heading(line: str) -> bool:
    """Heading-like but not in the alias table: short and ends with ":"."""
    text = line.strip()
    return text.endswith(":") and len(text.split()) <= MAX_UNRECOGNISED_HEADING_WORDS


def clean_jd(text: str) -> CleanedJd:
    """Split a pasted JD into kept and removed blocks (deterministic)."""
    lines = text.splitlines()
    kept: list[KeptBlock] = []
    removed: list[RemovedBlock] = []
    current: tuple[int, int, BlockKind | RemovalReason] | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        start, end, intent = current
        block_text = "\n".join(lines[start : end + 1])
        if isinstance(intent, BlockKind):
            kept.append(KeptBlock(text=block_text, start_line=start + 1, kind=intent))
        else:
            removed.append(RemovedBlock(text=block_text, start_line=start + 1, reason=intent))
        current = None

    for para_start, para_end in _paragraph_spans(lines):
        first_line = lines[para_start]
        intent = JD_HEADING_ALIASES.get(_normalize_heading(first_line))
        if intent is not None:
            # A recognised heading starts a new section that owns the
            # paragraphs after it, up to the next recognised heading or
            # heading-like line.
            flush()
            current = (para_start, para_end, intent)
            continue
        if _is_unrecognised_heading(first_line):
            # A heading-like line we do not recognise ends the current
            # section; its own paragraph is handled like standalone text
            # below (kept as "other" unless EEO-dominated).
            flush()
        if current is not None:
            current = (current[0], para_end, current[2])
            continue
        else:
            block_text = "\n".join(lines[para_start : para_end + 1])
            phrases = _equal_opportunity_phrases_in(block_text)
            if len(phrases) >= MIN_EEO_PHRASES:
                removed.append(
                    RemovedBlock(
                        text=block_text,
                        start_line=para_start + 1,
                        reason=RemovalReason.EQUAL_OPPORTUNITY,
                    )
                )
            else:
                kept.append(
                    KeptBlock(
                        text=block_text,
                        start_line=para_start + 1,
                        kind=BlockKind.OTHER,
                    )
                )
    flush()
    return CleanedJd(kept=tuple(kept), removed=tuple(removed))
