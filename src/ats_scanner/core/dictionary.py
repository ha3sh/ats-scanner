"""The skills dictionary: models, normalization, index (pure; SPEC §3).

core/ does no file I/O: the loader in adapters/dictionary_loader.py reads
and validates src/ats_scanner/data/dictionary.json and passes the
Dictionary into core functions as an argument.

normalize_term is the one normalization used everywhere: lowercase,
hyphens and underscores to spaces, whitespace collapsed — keeping ".",
"+" and "/" so "node.js", "c++", "c#" and "ci/cd" survive.

build_index maps every normalized canonical and alias to its entry and
raises ValueError on any collision (two entries claiming one term), so
a bad dictionary fails loudly instead of matching silently wrong.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SkillCategory(StrEnum):
    """The small closed set of skill categories."""

    LANGUAGE = "language"
    FRAMEWORK = "framework"
    LIBRARY = "library"
    DATABASE = "database"
    CLOUD = "cloud"
    DEVOPS = "devops"
    DATA = "data"
    TESTING = "testing"
    PRACTICE = "practice"
    TOOL = "tool"


class SkillEntry(BaseModel):
    """One skill: a canonical display name plus its accepted aliases.

    exact_case and ambiguous control how the matcher treats the entry:

    - exact_case (short names: C, Go, R) means "match only with this
      capitalization" — the bare name alone is too ambiguous otherwise.
    - ambiguous means "the bare name or an alias is also an ordinary
      word" — the matcher must later require skill context before
      counting it (e.g. Express, Spring, Vault, REST).
    """

    model_config = ConfigDict(frozen=True)

    canonical: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    category: SkillCategory
    exact_case: bool = False
    ambiguous: bool = False

    @field_validator("canonical")
    @classmethod
    def canonical_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("canonical must not be blank")
        return stripped

    @field_validator("aliases")
    @classmethod
    def aliases_not_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        stripped = tuple(alias.strip() for alias in value)
        if any(not alias for alias in stripped):
            raise ValueError("aliases must not be blank")
        return stripped

    @model_validator(mode="after")
    def no_duplicate_keys(self) -> "SkillEntry":
        keys = [normalize_term(self.canonical), *(normalize_term(a) for a in self.aliases)]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate canonical/alias after normalization")
        return self


class Dictionary(BaseModel):
    """The whole validated dictionary: version, provenance, entries."""

    model_config = ConfigDict(frozen=True)

    version: int = Field(ge=1)
    source: str = Field(min_length=1)
    entries: tuple[SkillEntry, ...] = Field(min_length=1)


def normalize_term(text: str) -> str:
    """Lowercase; hyphens/underscores to spaces; whitespace collapsed."""
    return " ".join(text.replace("-", " ").replace("_", " ").lower().split())


def build_index(dictionary: Dictionary) -> dict[str, SkillEntry]:
    """Map each normalized canonical and alias to its entry.

    Raises ValueError on the first collision: two entries claiming the
    same normalized term.
    """
    index: dict[str, SkillEntry] = {}
    for entry in dictionary.entries:
        for key in (entry.canonical, *entry.aliases):
            normalized = normalize_term(key)
            existing = index.get(normalized)
            if existing is not None:
                raise ValueError(
                    f"dictionary collision: {normalized!r} is claimed by "
                    f"{existing.canonical!r} and {entry.canonical!r}"
                )
            index[normalized] = entry
    return index
