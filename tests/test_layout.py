"""core/layout.py: column-order detection on synthetic word boxes (pure).

No pdfplumber here: the function receives frozen WordBox values and the page
width and must decide or abstain (None) — never guess.
"""

from ats_scanner.core.layout import WordBox, column_order

PAGE_WIDTH = 612
LINE_HEIGHT = 17


def word(text: str, x0: float, x1: float, top: float, height: float = 10) -> WordBox:
    return WordBox(text=text, x0=x0, x1=x1, top=top, bottom=top + height)


def header_words() -> list[WordBox]:
    """One full-width line above everything: spans ~40..560, so it crosses
    the gutter the columns would create."""
    return [
        word("Full", 40, 96, 30),
        word("width", 100, 156, 30),
        word("header", 160, 560, 30),
    ]


def two_column_words(rows: int = 8, right_x: float = 340) -> list[WordBox]:
    """Header line, then paired rows: left column ends by x=248, right starts
    at `right_x` (340 by default), so the empty band between the columns is
    ~15% of the page width."""
    words = header_words()
    for row in range(1, rows + 1):
        top = 60 + (row - 1) * LINE_HEIGHT
        words += [
            word(f"Left-{row}", 72, 128, top),
            word("alpha", 132, 188, top),
            word("beta", 192, 248, top),
            word(f"Right-{row}", right_x, right_x + 56, top),
            word("delta", right_x + 60, right_x + 116, top),
            word("epsilon", right_x + 120, right_x + 176, top),
        ]
    return words


def one_column_words(rows: int = 12) -> list[WordBox]:
    """Left-aligned single column; nothing right of x~270."""
    words = []
    for row in range(rows):
        top = 60 + row * LINE_HEIGHT
        for piece in range(3):
            x0 = 72 + piece * 50
            words.append(word(f"w{row}-{piece}", x0, x0 + 44, top))
    return words


def indices(text: str, markers: list[str]) -> list[int]:
    return [text.index(marker) for marker in markers]


def test_one_column_page_gets_no_column_text() -> None:
    assert column_order(one_column_words(), PAGE_WIDTH) is None


def test_two_clean_columns_read_left_block_then_right_block() -> None:
    text = column_order(two_column_words(), PAGE_WIDTH)
    assert text is not None
    order = indices(
        text,
        ["Left-1", "Left-4", "Left-8", "Right-1", "Right-4", "Right-8"],
    )
    assert order == sorted(order), text


def test_full_width_header_is_read_first() -> None:
    text = column_order(two_column_words(), PAGE_WIDTH)
    assert text is not None
    assert text.index("Full width header") < text.index("Left-1")
    assert text.index("Left-8") < text.index("Right-1")


def test_narrow_gutter_is_rejected() -> None:
    # Right column starts at x=260: the empty band is ~12 pt wide, under the
    # 3% (= 18.4 pt at 612) minimum, so the page must be read in row order.
    assert column_order(two_column_words(right_x=260), PAGE_WIDTH) is None


def test_too_few_words_is_rejected() -> None:
    words = two_column_words(rows=1)
    assert len(words) < 12
    assert column_order(words, PAGE_WIDTH) is None
