"""core/jd.py: JD cleaning into kept/removed blocks (pure; SPEC §3 step 1).

Conservative rules: only whole blocks are removed — a block under a
recognised boilerplate heading, or a standalone paragraph dominated by
equal-opportunity phrases (two or more distinct phrases). Requirement
blocks that merely mention "benefits" or "diversity" stay. Line numbers
are 1-based positions in the original text, so later evidence spans can
point into it. Fixtures in tests/fixtures/jds/ carry expected subsets in
the harness style.
"""

import json
from pathlib import Path

import pytest

from ats_scanner.core.jd import (
    BlockKind,
    KeptBlock,
    RemovalReason,
    RemovedBlock,
    clean_jd,
)
from harness import check_jd, run_jd

JD_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "jds"

FLAT_JD = (
    "Backend Developer - Bluebird Analytics\n"
    "\n"
    "We need a backend developer for our reporting pipeline.\n"
    "\n"
    "You will build APIs, tune queries, and keep deploys boring.\n"
    "\n"
    "Three years of Python and solid SQL are required.\n"
)

BOILERPLATE_JD = (
    "Senior Backend Engineer at Bluebird Analytics\n"
    "\n"
    "Bluebird Analytics is an equal opportunity employer. We celebrate diversity"
    " and inclusion on every team.\n"
    "\n"
    "Requirements:\n"
    "- Five years of Python\n"
    "- Production SQL experience\n"
    "\n"
    "Responsibilities:\n"
    "- Design APIs\n"
    "- Mentor juniors\n"
    "\n"
    "Benefits:\n"
    "- Unlimited PTO\n"
    "- Free snacks\n"
    "\n"
    "About Us:\n"
    "We are a small team in Portland.\n"
    "\n"
    "How to apply:\n"
    "Send a resume to jobs@bluebird.example.\n"
)

BENEFITS_SOFTWARE_JD = (
    "Payroll Engineer at Bluebird Analytics\n"
    "\n"
    "Requirements:\n"
    "- Five years of Python\n"
    "- Experience with benefits administration software\n"
    "- Comfortable with SQL\n"
    "\n"
    "Responsibilities:\n"
    "- Own the payroll pipeline\n"
    "\n"
    "Benefits:\n"
    "- Dental insurance\n"
    "\n"
    "How to apply:\n"
    "Email careers@bluebird.example.\n"
)


def test_flat_jd_keeps_everything() -> None:
    cleaned = clean_jd(FLAT_JD)
    assert cleaned.removed == ()
    assert [block.kind for block in cleaned.kept] == [BlockKind.OTHER] * 4
    assert [block.start_line for block in cleaned.kept] == [1, 3, 5, 7]


def test_benefits_software_requirement_is_kept() -> None:
    cleaned = clean_jd(BENEFITS_SOFTWARE_JD)
    requirements = next(block for block in cleaned.kept if block.kind is BlockKind.REQUIREMENTS)
    assert "benefits administration software" in requirements.text
    assert {block.reason for block in cleaned.removed} == {
        RemovalReason.BENEFITS,
        RemovalReason.HOW_TO_APPLY,
    }


def test_line_numbers_point_into_the_original_text() -> None:
    original_lines = BOILERPLATE_JD.splitlines()
    cleaned = clean_jd(BOILERPLATE_JD)
    blocks: list[KeptBlock | RemovedBlock] = [*cleaned.kept, *cleaned.removed]
    for block in blocks:
        assert block.text.splitlines()[0] == original_lines[block.start_line - 1], block.start_line
    assert [block.start_line for block in cleaned.kept] == [1, 5, 9]
    assert [block.start_line for block in cleaned.removed] == [3, 13, 17, 20]


def test_cleaning_is_deterministic() -> None:
    assert clean_jd(BOILERPLATE_JD) == clean_jd(BOILERPLATE_JD)


def test_heading_kinds() -> None:
    jd = "Must have:\n- Python\n\nNice to have:\n- Docker\n\nWhat you will do:\n- Build APIs\n"
    cleaned = clean_jd(jd)
    assert [block.kind for block in cleaned.kept] == [
        BlockKind.REQUIREMENTS,
        BlockKind.PREFERRED,
        BlockKind.RESPONSIBILITIES,
    ]
    assert cleaned.removed == ()
    assert [block.start_line for block in cleaned.kept] == [1, 4, 7]


def test_boilerplate_headings_remove_whole_sections() -> None:
    jd = (
        "Requirements:\n"
        "- Python\n"
        "\n"
        "Benefits:\n"
        "- Health insurance\n"
        "- Gym\n"
        "\n"
        "About Us:\n"
        "We are great.\n"
        "\n"
        "Equal Opportunity Employer:\n"
        "All are welcome.\n"
        "\n"
        "How to apply:\n"
        "Email us.\n"
    )
    cleaned = clean_jd(jd)
    assert [block.start_line for block in cleaned.kept] == [1]
    assert [block.reason for block in cleaned.removed] == [
        RemovalReason.BENEFITS,
        RemovalReason.ABOUT_COMPANY,
        RemovalReason.EQUAL_OPPORTUNITY,
        RemovalReason.HOW_TO_APPLY,
    ]
    assert [block.start_line for block in cleaned.removed] == [4, 8, 11, 14]


def test_requirement_mentioning_benefits_or_diversity_stays() -> None:
    jd = "Requirements:\n- Experience with benefits administration\n- Commitment to diversity\n"
    cleaned = clean_jd(jd)
    assert cleaned.removed == ()
    assert "benefits administration" in cleaned.kept[0].text
    assert "diversity" in cleaned.kept[0].text


def test_single_eeo_phrase_in_a_standalone_paragraph_stays() -> None:
    jd = "We value diversity.\n\nRequirements:\n- Python\n"
    cleaned = clean_jd(jd)
    assert cleaned.removed == ()
    assert [block.kind for block in cleaned.kept] == [BlockKind.OTHER, BlockKind.REQUIREMENTS]


def test_unrecognised_heading_ends_a_boilerplate_section() -> None:
    jd = "Requirements:\n- Python\n\nBenefits:\n- Unlimited PTO\n\nTech stack:\n- Rust\n- Go\n"
    cleaned = clean_jd(jd)
    assert [(block.start_line, block.kind) for block in cleaned.kept] == [
        (1, BlockKind.REQUIREMENTS),
        (7, BlockKind.OTHER),
    ]
    assert [(b.start_line, b.reason) for b in cleaned.removed] == [(4, RemovalReason.BENEFITS)]


def test_unrecognised_heading_after_about_us_and_after_how_to_apply() -> None:
    jd = (
        "About Us:\n"
        "We are great.\n"
        "\n"
        "Tech stack:\n"
        "- Rust\n"
        "\n"
        "How to apply:\n"
        "Email us.\n"
        "\n"
        "Interview process:\n"
        "Two calls.\n"
    )
    cleaned = clean_jd(jd)
    assert [(block.start_line, block.kind) for block in cleaned.kept] == [
        (4, BlockKind.OTHER),
        (10, BlockKind.OTHER),
    ]
    assert [(b.start_line, b.reason) for b in cleaned.removed] == [
        (1, RemovalReason.ABOUT_COMPANY),
        (7, RemovalReason.HOW_TO_APPLY),
    ]


def test_benefits_section_without_a_new_heading_is_still_removed_whole() -> None:
    jd = (
        "Benefits:\n"
        "- Health insurance\n"
        "\n"
        "We also offer a yearly learning budget and remote work.\n"
        "\n"
        "Requirements:\n"
        "- Python\n"
    )
    cleaned = clean_jd(jd)
    assert [(b.start_line, b.reason) for b in cleaned.removed] == [(1, RemovalReason.BENEFITS)]
    assert [(b.start_line, b.kind) for b in cleaned.kept] == [(6, BlockKind.REQUIREMENTS)]


def test_long_or_colonless_lines_do_not_end_a_section() -> None:
    jd = (
        "Benefits:\n"
        "- PTO\n"
        "\n"
        "Our generous benefits and perks package for everyone here:\n"
        "- Gym\n"
        "\n"
        "Benefits:\n"
        "- Snacks\n"
        "\n"
        "Tech stack we use\n"
        "- Rust\n"
    )
    cleaned = clean_jd(jd)
    assert cleaned.kept == ()
    assert [(b.start_line, b.reason) for b in cleaned.removed] == [
        (1, RemovalReason.BENEFITS),
        (7, RemovalReason.BENEFITS),
    ]


def test_unrecognized_heading_is_kept_as_other() -> None:
    jd = "About Bluebird Analytics:\nWe build dashboards.\n\nRequirements:\n- Python\n"
    cleaned = clean_jd(jd)
    assert [block.kind for block in cleaned.kept] == [BlockKind.OTHER, BlockKind.REQUIREMENTS]
    assert cleaned.removed == ()


def test_cleaned_text_joins_kept_blocks() -> None:
    cleaned = clean_jd(BOILERPLATE_JD)
    assert cleaned.cleaned_text == "\n\n".join(block.text for block in cleaned.kept)
    assert "Benefits:" not in cleaned.cleaned_text
    assert "Requirements:" in cleaned.cleaned_text


JD_NAMES = sorted(
    {
        *(path.name for path in JD_FIXTURES.glob("*.txt")),
        *(path.name.removesuffix(".expected.json") for path in JD_FIXTURES.glob("*.expected.json")),
    }
)


@pytest.mark.parametrize("name", JD_NAMES)
def test_every_jd_fixture_matches_its_expected_subset(name: str) -> None:
    fixture = JD_FIXTURES / name
    expected_path = JD_FIXTURES / f"{name}.expected.json"
    assert fixture.exists(), f"{expected_path.name} has no fixture file beside it"
    assert expected_path.exists(), f"{fixture.name} has no {fixture.name}.expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    messages = check_jd(expected, run_jd(fixture))
    assert not messages, "\n".join(messages)
