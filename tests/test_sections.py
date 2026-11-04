"""core/sections.py: the seven sections and heading detection (pure).

A heading is a short line (at most 5 words, no sentence-ending period)
whose normalized text (lowercase, trimmed, punctuation and trailing colon
stripped) equals an alias. First occurrence wins; all seven sections are
always returned in fixed order.
"""

from ats_scanner.core.report import SectionName
from ats_scanner.core.sections import find_sections, is_heading, normalize_heading


def test_normalization_strips_case_colons_and_bullets() -> None:
    assert normalize_heading("  Skills: ") == "skills"
    assert normalize_heading("- WORK EXPERIENCE") == "work experience"
    assert normalize_heading("\u2022 Core Competencies") == "core competencies"


def test_alias_sets_match_positive_headings() -> None:
    cases = {
        "Summary": SectionName.SUMMARY,
        "Professional Summary": SectionName.SUMMARY,
        "Profile": SectionName.SUMMARY,
        "About me": SectionName.SUMMARY,
        "Experience": SectionName.EXPERIENCE,
        "Work Experience": SectionName.EXPERIENCE,
        "Professional experience": SectionName.EXPERIENCE,
        "Employment History": SectionName.EXPERIENCE,
        "Education": SectionName.EDUCATION,
        "Technical Skills": SectionName.SKILLS,
        "Core competencies": SectionName.SKILLS,
        "Skills:": SectionName.SKILLS,
        "Projects": SectionName.PROJECTS,
        "Selected projects": SectionName.PROJECTS,
        "Certifications": SectionName.CERTIFICATIONS,
        "Licenses and certifications": SectionName.CERTIFICATIONS,
    }
    for line, name in cases.items():
        assert is_heading(line), line
        sections = find_sections([line])
        finding = next(item for item in sections if item.name == name)
        assert finding.found, line
        assert finding.heading == line.strip(), line


def test_long_sentence_starting_with_experience_is_not_a_heading() -> None:
    sections = find_sections(
        ["Experience building scalable backend systems with Python and databases"]
    )
    finding = next(item for item in sections if item.name == SectionName.EXPERIENCE)
    assert not finding.found


def test_bullet_containing_education_is_not_a_heading() -> None:
    sections = find_sections(
        ["- Education included coursework in databases and distributed systems"]
    )
    finding = next(item for item in sections if item.name == SectionName.EDUCATION)
    assert not finding.found


def test_sentence_ending_period_is_not_a_heading() -> None:
    for line in ("Experience.", "Summary of my work."):
        sections = find_sections([line])
        finding = next(item for item in sections if item.name != SectionName.CONTACT)
        assert not finding.found, line


def test_all_seven_sections_always_present_in_fixed_order() -> None:
    sections = find_sections(["nothing relevant"])
    assert [item.name for item in sections] == [
        SectionName.CONTACT,
        SectionName.SUMMARY,
        SectionName.EXPERIENCE,
        SectionName.EDUCATION,
        SectionName.SKILLS,
        SectionName.PROJECTS,
        SectionName.CERTIFICATIONS,
    ]
    assert all(not item.found for item in sections)


def test_first_occurrence_wins_across_pages() -> None:
    sections = find_sections(["Skills\none", "Skills\ntwo"])
    finding = next(item for item in sections if item.name == SectionName.SKILLS)
    assert (finding.page, finding.line) == (1, 1)


def test_contact_section_found_when_email_present_heading_none() -> None:
    sections = find_sections(["alex@example.com"], contact_found=True)
    finding = next(item for item in sections if item.name == SectionName.CONTACT)
    assert finding.found
    assert finding.heading is None
    assert finding.page is None and finding.line is None


def test_contact_section_not_found_without_email_or_phone() -> None:
    sections = find_sections(["alex@example.com"], contact_found=False)
    finding = next(item for item in sections if item.name == SectionName.CONTACT)
    assert not finding.found
