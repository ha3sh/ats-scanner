"""core/contact.py: email, phone, LinkedIn detection (pure, line-based).

Phone rules: a loose international matcher requiring 9 to 15 digits in
total; date ranges, years, version strings and short numbers must not
match. Email: trailing punctuation stripped. LinkedIn: scheme and www
stripped from the value.
"""

from ats_scanner.core.contact import find_contact


def test_email_found_with_trailing_punctuation_stripped() -> None:
    info = find_contact(["Contact: alex@example.com, call anytime"])
    assert info.email.found
    assert info.email.value == "alex@example.com"
    assert (info.email.page, info.email.line) == (1, 1)


def test_phone_loose_international_formats() -> None:
    for text in (
        "(555) 555-0100",
        "+1 (555) 555-0100",
        "555 555 0100",
        "+44 20 7946 0958",
        "+1 415 555 0132",
    ):
        info = find_contact([text])
        assert info.phone.found, text
        assert info.phone.value is not None and info.phone.value.strip()


def test_phone_rejects_runs_of_year_like_numbers() -> None:
    for text in (
        "2018 - 2020 2021",
        "2019 2020 2021",
        "Led 3 teams 2019 - 2021 and 2022",
    ):
        info = find_contact([text])
        assert not info.phone.found, text


def test_phone_rejects_dates_years_versions_and_short_numbers() -> None:
    for text in (
        "2014 - 2018",
        "2014\u20132018",
        "March 2021 - Present",
        "3.12.4",
        "Python 3.12.4",
        "40%",
        "page 12",
        "v1.2",
        "1234567890123456",
    ):
        info = find_contact([text])
        assert not info.phone.found, text


def test_linkedin_variants_are_normalised() -> None:
    info = find_contact(["linkedin.com/in/alex-example"])
    assert info.linkedin.found
    assert info.linkedin.value == "linkedin.com/in/alex-example"
    info = find_contact(["https://www.linkedin.com/in/alex-example/"])
    assert info.linkedin.found
    assert info.linkedin.value == "linkedin.com/in/alex-example"


def test_no_contact_details() -> None:
    info = find_contact(["Nothing to see here."])
    assert not info.email.found and info.email.value is None
    assert not info.phone.found and info.phone.value is None
    assert not info.linkedin.found and info.linkedin.value is None
    assert info.email.page is None and info.email.line is None


def test_first_occurrence_wins_with_page_and_line() -> None:
    pages = [
        "no details on page one",
        "call (555) 555-0100\nor email alex@example.com",
    ]
    info = find_contact(pages)
    assert (info.phone.page, info.phone.line) == (2, 1)
    assert (info.email.page, info.email.line) == (2, 2)
