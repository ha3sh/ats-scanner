"""Section detection: the seven resume sections (pure; SPEC §4).

A heading is a short line (at most 5 words, no sentence-ending period)
whose normalized text — lowercase, trimmed, leading/trailing punctuation
and trailing colon stripped — equals one alias of a section. First
occurrence wins. "contact" is not heading-based: the pipeline marks it
found when an email or phone is detected (heading None).

The alias table below is the single source of truth for v1.
"""

from collections.abc import Sequence

from ats_scanner.core.report import SectionFinding, SectionName

MAX_HEADING_WORDS = 5

_STRIP = " \t\u2022*-\u2013\u2014.,;:!?"


SECTION_ALIASES: dict[SectionName, frozenset[str]] = {
    SectionName.SUMMARY: frozenset(
        {
            "summary",
            "professional summary",
            "career summary",
            "summary of qualifications",
            "profile",
            "about me",
            "objective",
        }
    ),
    SectionName.EXPERIENCE: frozenset(
        {
            "experience",
            "work experience",
            "professional experience",
            "relevant experience",
            "employment history",
            "work history",
        }
    ),
    SectionName.EDUCATION: frozenset(
        {
            "education",
            "education and training",
            "academic background",
            "academic history",
        }
    ),
    SectionName.SKILLS: frozenset(
        {
            "skills",
            "technical skills",
            "key skills",
            "core competencies",
            "competencies",
            "skills and tools",
        }
    ),
    SectionName.PROJECTS: frozenset(
        {
            "projects",
            "selected projects",
            "key projects",
            "personal projects",
            "project experience",
        }
    ),
    SectionName.CERTIFICATIONS: frozenset(
        {
            "certifications",
            "licenses and certifications",
            "certifications and licenses",
            "certificates",
            "licenses",
        }
    ),
}


def normalize_heading(line: str) -> str:
    """Lowercase, trimmed, edge punctuation and bullets stripped."""
    text = line.strip().strip(_STRIP).lower()
    return " ".join(text.split())


def is_heading(line: str) -> bool:
    """Short line, no sentence-ending period, at most five words."""
    text = line.strip()
    if not text or text.endswith("."):
        return False
    return 1 <= len(normalize_heading(text).split()) <= MAX_HEADING_WORDS


def find_sections(pages: Sequence[str], contact_found: bool = False) -> tuple[SectionFinding, ...]:
    """All seven sections in fixed order; first occurrence wins."""
    found: dict[SectionName, SectionFinding | None] = {name: None for name in SectionName}
    for page_number, text in enumerate(pages, start=1):
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not is_heading(line):
                continue
            normalized = normalize_heading(line)
            for name, aliases in SECTION_ALIASES.items():
                if found[name] is None and normalized in aliases:
                    found[name] = SectionFinding(
                        name=name,
                        found=True,
                        heading=line.strip(),
                        page=page_number,
                        line=line_number,
                    )
    sections: list[SectionFinding] = []
    for name in SectionName:
        finding = found[name]
        sections.append(finding if finding is not None else SectionFinding(name=name, found=False))
    # "contact" is not heading-based: the pipeline reports it found when an
    # email or phone was detected, with no heading text (SPEC §4).
    sections[0] = SectionFinding(name=SectionName.CONTACT, found=contact_found)
    return tuple(sections)
