"""core/terms.py: dictionary-only JD term extraction (pure; SPEC §3 steps 2-5).

Meta checks: maximal munch (the longest dictionary phrase wins, so
"spring boot" never also counts "spring"), exact_case (Go vs go, R vs
r) plus the context that ordinary-word names need, each ambiguity rule
(punctuation, multi-word, a non-ambiguous neighbour on the line),
required vs preferred weights and the preferred override, occurrence
counting with the first-max-weight representative, deterministic
order, the 60 cap on a synthetic list, and kept-only scanning.
"""

from ats_scanner.core.dictionary import Dictionary, SkillCategory, SkillEntry, build_index
from ats_scanner.core.jd import clean_jd
from ats_scanner.core.terms import MAX_TERMS, JdTerm, extract_terms


def entry(
    canonical: str,
    *aliases: str,
    category: SkillCategory = SkillCategory.TOOL,
    exact_case: bool = False,
    ambiguous: bool = False,
) -> SkillEntry:
    return SkillEntry(
        canonical=canonical,
        aliases=aliases,
        category=category,
        exact_case=exact_case,
        ambiguous=ambiguous,
    )


TEST_INDEX = build_index(
    Dictionary(
        version=1,
        source="test",
        entries=(
            entry("Python", category=SkillCategory.LANGUAGE),
            entry("SQL", category=SkillCategory.LANGUAGE),
            entry("Go", category=SkillCategory.LANGUAGE, exact_case=True),
            entry("R", category=SkillCategory.LANGUAGE, exact_case=True),
            entry("Rust", category=SkillCategory.LANGUAGE),
            entry("Java", category=SkillCategory.LANGUAGE),
            entry("Kotlin", category=SkillCategory.LANGUAGE),
            entry("Docker", category=SkillCategory.DEVOPS),
            entry(
                "Spring",
                "spring boot",
                "spring framework",
                category=SkillCategory.FRAMEWORK,
                ambiguous=True,
            ),
            entry("Node.js", "node", "nodejs", category=SkillCategory.FRAMEWORK, ambiguous=True),
            entry("Express", "express.js", category=SkillCategory.FRAMEWORK, ambiguous=True),
            entry("Microsoft Excel", "excel", category=SkillCategory.TOOL, ambiguous=True),
            entry("Machine Learning", "ml", category=SkillCategory.PRACTICE),
            entry("Rails", "ruby on rails", category=SkillCategory.FRAMEWORK, ambiguous=True),
            entry(
                "REST",
                "rest api",
                "restful",
                category=SkillCategory.PRACTICE,
                ambiguous=True,
            ),
            entry("Kubernetes", "k8s", category=SkillCategory.DEVOPS),
        ),
    )
)


def terms_for(jd: str) -> tuple[JdTerm, ...]:
    return extract_terms(clean_jd(jd), TEST_INDEX)


def canonicals(terms: tuple[JdTerm, ...]) -> list[str]:
    return [term.canonical for term in terms]


def by_canonical(terms: tuple[JdTerm, ...], canonical: str) -> JdTerm:
    return next(term for term in terms if term.canonical == canonical)


def test_maximal_munch_longest_phrase_wins() -> None:
    jd = (
        "Requirements:\n"
        "- Experience with Spring Boot\n"
        "- Built with Ruby on Rails\n"
        "- Machine learning pipelines\n"
    )
    terms = terms_for(jd)
    spring = by_canonical(terms, "Spring")
    assert spring.occurrences == 1
    assert spring.surface == "Spring Boot"
    rails = by_canonical(terms, "Rails")
    assert rails.occurrences == 1
    assert rails.surface == "Ruby on Rails"
    ml = by_canonical(terms, "Machine Learning")
    assert ml.occurrences == 1
    assert ml.surface == "Machine learning"


def test_exact_case_matches_only_the_dictionary_capitalization() -> None:
    upper = terms_for("- Experience with Go, SQL and R\n")
    assert {"Go", "SQL", "R"} <= set(canonicals(upper))
    lower = terms_for("- Experience with go, sql and r\n")
    assert canonicals(lower) == ["SQL"]


def test_exact_case_names_need_context_like_ambiguous_ones() -> None:
    # C, Go, R are ordinary words: a bare sentence-initial "Go to market"
    # is not a hit, the same rule as for ambiguous entries.
    assert terms_for("Go to market with the founders.\n") == ()
    assert terms_for("R beats everything else here.\n") == ()


def test_exact_case_counts_with_a_precedence_cue() -> None:
    for line, expected in (
        ("Four years of Go.", "Go"),
        ("Experience with Go.", "Go"),
        ("Proficiency in R.", "R"),
        ("Skilled in R.", "R"),
    ):
        assert expected in canonicals(terms_for(f"{line}\n")), line


def test_exact_case_counts_inside_a_list() -> None:
    first = canonicals(terms_for("Experience with Go, SQL and R.\n"))
    assert {"Go", "SQL", "R"} <= set(first)
    assert "R" in canonicals(terms_for("Python, R and SQL.\n"))
    assert "Go" in canonicals(terms_for("Go and Rust.\n"))


def test_exact_case_does_not_count_when_hyphen_or_ampersand_joined() -> None:
    for line in (
        "R&D with Python.",
        "Present to C-level execs using Python.",
        "Go-to-market strategy with SQL.",
        "Plan C.",
    ):
        terms = terms_for(f"{line}\n")
        assert not ({"Go", "R", "C"} & set(canonicals(terms))), line


def test_plural_last_token_retries_with_the_singular() -> None:
    rest = by_canonical(terms_for("Requirements:\n- Experience with REST APIs\n"), "REST")
    assert rest.occurrences == 1
    assert rest.surface == "REST APIs"
    docker = by_canonical(terms_for("Docker containers everywhere.\n"), "Docker")
    assert docker.occurrences == 1
    assert canonicals(terms_for("Docker containers everywhere.\n")) == ["Docker"]
    kubernetes = by_canonical(terms_for("Kubernetes in production.\n"), "Kubernetes")
    assert kubernetes.occurrences == 1
    assert kubernetes.surface == "Kubernetes"


def test_ambiguous_single_words_need_punctuation_or_a_neighbour() -> None:
    assert "Microsoft Excel" not in canonicals(terms_for("Excel at teamwork every day.\n"))
    assert "Microsoft Excel" in canonicals(terms_for("Experience with Excel, SQL and Python\n"))
    assert "Node.js" not in canonicals(terms_for("The node in the graph is slow.\n"))
    assert "Node.js" in canonicals(terms_for("Experience with Node.js\n"))
    assert "Spring" not in canonicals(terms_for("We will ship this spring.\n"))
    assert "Spring" in canonicals(terms_for("Experience with Spring Boot\n"))
    assert "Express" not in canonicals(terms_for("Express your ideas in writing.\n"))
    assert "Express" in canonicals(terms_for("Experience with Express.js\n"))


def test_requirements_block_makes_terms_required() -> None:
    term = by_canonical(terms_for("Requirements:\n- Python\n"), "Python")
    assert term.weight == 2.0
    assert term.required is True


def test_required_cues_in_other_blocks() -> None:
    for line in (
        "Python is required here.",
        "You must know Python.",
        "A minimum of Python experience.",
        "Proficiency in Python expected.",
        "Strong Python skills.",
    ):
        term = by_canonical(terms_for(f"{line}\n"), "Python")
        assert term.weight == 2.0, line


def test_preferred_block_and_cues_force_other_weight() -> None:
    term = by_canonical(terms_for("Preferred:\n- Python is required in some teams\n"), "Python")
    assert term.weight == 1.0
    assert term.required is False
    for line in (
        "Nice to have: Python.",
        "Python is preferred.",
        "Python is a plus.",
        "Python for bonus points.",
    ):
        term = by_canonical(terms_for(f"{line}\n"), "Python")
        assert term.weight == 1.0, line


def test_preferred_cue_overrides_a_requirements_block() -> None:
    term = by_canonical(terms_for("Requirements:\n- Rust is a plus\n"), "Rust")
    assert term.weight == 1.0
    assert term.required is False


def test_not_required_is_a_known_limitation() -> None:
    # "X is not required" contains the cue "required"; negation is not
    # parsed. Documented in core/terms.py and SPEC §3 — this pins it.
    term = by_canonical(terms_for("SQL is not required for this role.\n"), "SQL")
    assert term.weight == 2.0
    assert term.required is True


def test_occurrences_and_context_come_from_the_first_max_weight_line() -> None:
    jd = "Nice to have:\n- Python\n\nRequirements:\n- Python and Python\n"
    term = by_canonical(terms_for(jd), "Python")
    assert term.occurrences == 3
    assert term.weight == 2.0
    assert term.required is True
    assert term.line == 5
    assert term.context == "- Python and Python"
    assert term.surface == "Python"


def test_terms_are_sorted_by_weight_then_occurrences_then_line_then_canonical() -> None:
    jd = (
        "Requirements:\n"
        "- SQL\n"
        "- Python and Python\n"
        "\n"
        "Nice to have:\n"
        "- Docker, Docker, Docker\n"
        "- Java and Kotlin\n"
    )
    terms = terms_for(jd)
    assert [(term.canonical, term.weight, term.occurrences) for term in terms] == [
        ("Python", 2.0, 2),
        ("SQL", 2.0, 1),
        ("Docker", 1.0, 3),
        ("Java", 1.0, 1),
        ("Kotlin", 1.0, 1),
    ]
    assert terms == terms_for(jd)


def test_terms_are_capped_at_60_deterministically() -> None:
    entries = tuple(
        SkillEntry(canonical=f"Skill{i:02d}", category=SkillCategory.TOOL) for i in range(70)
    )
    index = build_index(Dictionary(version=1, source="test", entries=entries))
    lines = "\n".join(f"- Skill{i:02d}" for i in range(70))
    terms = extract_terms(clean_jd(f"Requirements:\n{lines}\n"), index)
    assert len(terms) == MAX_TERMS == 60
    assert [term.canonical for term in terms] == [f"Skill{i:02d}" for i in range(60)]


def test_terms_come_from_kept_blocks_only() -> None:
    jd = "Benefits:\n- Python training budget\n\nRequirements:\n- SQL\n"
    assert canonicals(terms_for(jd)) == ["SQL"]


def test_lines_and_context_point_into_the_original_text() -> None:
    jd = "Senior Engineer at Bluebird Analytics\n\nRequirements:\n- Five years of Python\n"
    term = by_canonical(terms_for(jd), "Python")
    assert term.line == 4
    assert term.context == "- Five years of Python"
    assert jd.splitlines()[3] == term.context


def test_a_jd_without_dictionary_terms_yields_nothing() -> None:
    assert terms_for("We value curiosity and kindness.\n\n- Team lunches every Friday\n") == ()
