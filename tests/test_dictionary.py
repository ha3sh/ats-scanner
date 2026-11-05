"""core/dictionary.py + data/dictionary.json (SPEC §3 pipeline steps 2-3).

Model validation (unknown category, empty canonical, duplicate aliases
within an entry), normalize_term cases, build_index with loud collision
failures, and the real dictionary file: it loads, has 250-350 entries,
covers every category, canonicals are unique after normalization, no
alias equals another entry's canonical, the index builds without
collisions, and exact_case entries are exactly the short ambiguous
allow-list.
"""

import pytest
from pydantic import ValidationError

from ats_scanner.adapters.dictionary_loader import load_dictionary
from ats_scanner.config import DICTIONARY_VERSION
from ats_scanner.core.dictionary import (
    Dictionary,
    SkillCategory,
    SkillEntry,
    build_index,
    normalize_term,
)

# The short ambiguous names that alone may match with exact capitalization.
EXACT_CASE_ALLOW_LIST = {"Go", "R", "C"}

# Entries whose bare name or alias is also an ordinary word: the matcher
# must later require skill context before counting them.
AMBIGUOUS_ALLOW_LIST = {
    "Express",
    "Spring",
    "Rails",
    "Microsoft Excel",
    "Unity",
    "Assembly",
    "Vault",
    "Phoenix",
    "Swift",
    "Hugo",
    "Nest",
    "Apache Hive",
    "Apache Spark",
    "Node.js",
    "REST",
}

# Aliases removed because they false-match ordinary English words
# (regression list: they must never come back).
REMOVED_ALIASES = {"py", "pd", "tf", "sns", "pil", "sonar", "shell"}


@pytest.fixture(scope="module")
def dictionary() -> Dictionary:
    return load_dictionary()


def test_entry_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        SkillEntry.model_validate({"canonical": "Python", "category": "nope"})


def test_entry_rejects_empty_canonical() -> None:
    with pytest.raises(ValidationError):
        SkillEntry(canonical="   ", category=SkillCategory.LANGUAGE)


def test_entry_rejects_duplicate_aliases_within_an_entry() -> None:
    with pytest.raises(ValidationError):
        SkillEntry(
            canonical="PostgreSQL",
            aliases=("postgres", "Postgres"),
            category=SkillCategory.DATABASE,
        )


def test_entry_rejects_alias_equal_to_its_own_canonical() -> None:
    with pytest.raises(ValidationError):
        SkillEntry(canonical="Redis", aliases=("redis",), category=SkillCategory.DATABASE)


def test_normalize_term() -> None:
    assert normalize_term("  Node.JS  ") == "node.js"
    assert normalize_term("C++") == "c++"
    assert normalize_term("C#") == "c#"
    assert normalize_term("CI/CD") == "ci/cd"
    assert normalize_term("Machine   Learning") == "machine learning"
    assert normalize_term("ci-cd") == "ci cd"
    assert normalize_term("Node_JS") == "node js"
    assert normalize_term("TypeScript") == "typescript"


def make_dictionary() -> Dictionary:
    return Dictionary(
        version=1,
        source="test",
        entries=(
            SkillEntry(
                canonical="PostgreSQL", aliases=("postgres",), category=SkillCategory.DATABASE
            ),
            SkillEntry(canonical="Kubernetes", aliases=("k8s",), category=SkillCategory.DEVOPS),
        ),
    )


def test_build_index_maps_canonicals_and_aliases() -> None:
    index = build_index(make_dictionary())
    assert index["postgres"].canonical == "PostgreSQL"
    assert index["postgresql"].canonical == "PostgreSQL"
    assert index["k8s"].canonical == "Kubernetes"
    assert index["kubernetes"].canonical == "Kubernetes"


def test_build_index_fails_loudly_on_collision() -> None:
    dictionary = Dictionary(
        version=1,
        source="test",
        entries=(
            SkillEntry(canonical="PostgreSQL", aliases=("pg",), category=SkillCategory.DATABASE),
            SkillEntry(canonical="Python", aliases=("pg",), category=SkillCategory.LANGUAGE),
        ),
    )
    with pytest.raises(ValueError, match="collision"):
        build_index(dictionary)


def test_real_file_loads_and_matches_config_version(dictionary: Dictionary) -> None:
    # Single source pairing: bump config.DICTIONARY_VERSION and the file's
    # version field together.
    assert dictionary.version == DICTIONARY_VERSION


def test_real_file_has_250_to_350_entries(dictionary: Dictionary) -> None:
    assert 250 <= len(dictionary.entries) <= 350


def test_real_file_covers_every_category(dictionary: Dictionary) -> None:
    assert {entry.category for entry in dictionary.entries} == set(SkillCategory)


def test_real_file_canonicals_are_unique_after_normalization(dictionary: Dictionary) -> None:
    normalized = [normalize_term(entry.canonical) for entry in dictionary.entries]
    assert len(normalized) == len(set(normalized))


def test_real_file_no_alias_equals_another_canonical(dictionary: Dictionary) -> None:
    canonicals = {normalize_term(entry.canonical) for entry in dictionary.entries}
    for entry in dictionary.entries:
        for alias in entry.aliases:
            assert normalize_term(alias) not in canonicals, (entry.canonical, alias)


def test_real_file_index_builds_without_collisions(dictionary: Dictionary) -> None:
    index = build_index(dictionary)  # raises ValueError on any collision
    assert len(index) >= len(dictionary.entries)


def test_exact_case_entries_are_exactly_the_allow_list(dictionary: Dictionary) -> None:
    exact = {entry.canonical for entry in dictionary.entries if entry.exact_case}
    assert exact == EXACT_CASE_ALLOW_LIST


def test_ambiguous_entries_are_exactly_the_allow_list(dictionary: Dictionary) -> None:
    ambiguous = {entry.canonical for entry in dictionary.entries if entry.ambiguous}
    assert ambiguous == AMBIGUOUS_ALLOW_LIST


def test_removed_aliases_never_come_back(dictionary: Dictionary) -> None:
    for entry in dictionary.entries:
        for alias in entry.aliases:
            assert normalize_term(alias) not in REMOVED_ALIASES, (entry.canonical, alias)


def test_no_alias_is_shorter_than_two_characters(dictionary: Dictionary) -> None:
    for entry in dictionary.entries:
        for alias in entry.aliases:
            assert len(alias.strip()) >= 2, (entry.canonical, alias)


def test_requests_and_excel_are_renamed(dictionary: Dictionary) -> None:
    canonicals = {normalize_term(entry.canonical) for entry in dictionary.entries}
    assert "python requests" in canonicals
    assert "requests" not in canonicals
    assert "microsoft excel" in canonicals
    # No alias needed: the canonical itself normalizes to "python requests"
    # (an alias would duplicate its own canonical, which the model rejects).
    requests = next(e for e in dictionary.entries if e.canonical == "Python Requests")
    assert requests.aliases == ()
