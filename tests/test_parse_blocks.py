"""The text of a part of a page, block by block. Every page here is invented."""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from hackathon_memory.parse.blocks import (
    CODE,
    ITEM,
    PARAGRAPH,
    TITLE,
    Block,
    blocks_of,
    plain_text,
    squash,
)


def box(html: str) -> Tag:
    found = BeautifulSoup(f'<div id="box">{html}</div>', "lxml").find(id="box")
    assert isinstance(found, Tag)
    return found


def letters(text: str) -> str:
    """The text with no space at all: what must stay the same, letter by letter."""
    return "".join(text.split())


# --------------------------------------------------------------------- one block


def test_a_paragraph_is_one_block() -> None:
    assert blocks_of(box("<p>A coin for a street vendor.</p>")) == [
        Block(PARAGRAPH, "A coin for a street vendor.")
    ]


def test_a_word_in_bold_stays_glued_to_what_follows() -> None:
    page = box("<p>the <strong>Hedera</strong>-based <em>ledger</em>, and <code>a.b</code>.</p>")
    assert blocks_of(page) == [Block(PARAGRAPH, "the Hedera-based ledger, and a.b.")]


def test_a_comment_between_two_pieces_of_text_is_not_text() -> None:
    # A page written by React puts an empty comment between two pieces of text.
    line = box("<p>Hedera<!-- --> <!-- -->-<!-- --> <!-- -->Best use<!-- --> <!-- -->1st</p>")
    assert blocks_of(line) == [Block(PARAGRAPH, "Hedera - Best use 1st")]
    assert blocks_of(box("<p>to<!-- hidden words -->gether</p>")) == [Block(PARAGRAPH, "together")]


def test_a_line_break_keeps_two_words_apart() -> None:
    assert blocks_of(box("<p>one<br>two<br/>three</p>")) == [Block(PARAGRAPH, "one two three")]


def test_spaces_and_new_lines_of_the_markup_become_one_space() -> None:
    assert blocks_of(box("<p>  one\n     two\t three  </p>")) == [Block(PARAGRAPH, "one two three")]
    assert squash("  a \n b\t\tc ") == "a b c"


def test_an_empty_block_is_left_out() -> None:
    assert blocks_of(box("<p></p><p>   </p><ul><li></li></ul><h3></h3><p>kept</p>")) == [
        Block(PARAGRAPH, "kept")
    ]


# --------------------------------------------------------------------- lists, titles, code


def test_a_list_gives_one_block_for_each_item_with_its_depth() -> None:
    page = box(
        "<ul><li>first</li><li>second<ul><li>inside<ol><li>deep</li></ol></li></ul></li></ul>"
        "<ol><li>one</li></ol>"
    )
    assert blocks_of(page) == [
        Block(ITEM, "first", 1),
        Block(ITEM, "second", 1),
        Block(ITEM, "inside", 2),
        Block(ITEM, "deep", 3),
        Block(ITEM, "one", 1),
    ]


def test_an_item_with_paragraphs_inside_keeps_their_words_apart() -> None:
    page = box("<ul><li><p>one line</p><p>another line</p></li></ul>")
    assert blocks_of(page) == [Block(ITEM, "one line another line", 1)]


def test_a_list_wrapped_in_a_box_inside_an_item_is_not_lost() -> None:
    page = box("<ul><li>outer<div><ul><li>inner</li></ul></div></li></ul>")
    assert blocks_of(page) == [Block(ITEM, "outer", 1), Block(ITEM, "inner", 2)]


def test_a_title_keeps_its_level() -> None:
    page = box("<h2>Overview</h2><p>text</p><h3>Problem</h3><h4>A <em>small</em> part</h4>")
    assert blocks_of(page) == [
        Block(TITLE, "Overview", 2),
        Block(PARAGRAPH, "text"),
        Block(TITLE, "Problem", 3),
        Block(TITLE, "A small part", 4),
    ]


def test_code_keeps_its_lines() -> None:
    page = box("<pre><code>first = 1\n  second = 2\n</code></pre>")
    assert blocks_of(page) == [Block(CODE, "first = 1\n  second = 2")]


# --------------------------------------------------------------------- what is around the blocks


def test_text_outside_any_block_becomes_a_paragraph() -> None:
    page = box("loose <code>text</code> here<p>then a paragraph</p>and after<ul><li>item</li></ul>")
    assert blocks_of(page) == [
        Block(PARAGRAPH, "loose text here"),
        Block(PARAGRAPH, "then a paragraph"),
        Block(PARAGRAPH, "and after"),
        Block(ITEM, "item", 1),
    ]


def test_a_quote_and_a_box_give_their_own_blocks() -> None:
    page = box("<blockquote><p>said once</p><p>said twice</p></blockquote><div><p>boxed</p></div>")
    assert [block.text for block in blocks_of(page)] == ["said once", "said twice", "boxed"]


def test_each_cell_of_a_table_is_a_paragraph_and_no_sign_is_added() -> None:
    rows = "<tr><th>Name</th><th>Use</th></tr><tr><td>Topic</td><td>Log</td></tr>"
    page = box(f"<table>{rows}</table>")
    assert blocks_of(page) == [
        Block(PARAGRAPH, "Name"),
        Block(PARAGRAPH, "Use"),
        Block(PARAGRAPH, "Topic"),
        Block(PARAGRAPH, "Log"),
    ]


def test_a_script_a_style_and_a_picture_are_not_text() -> None:
    page = box(
        "<p>seen</p><script>var hidden = 1;</script><style>.x{color:red}</style>"
        '<p><img src="https://cdn.example.test/a.png" alt="words of a picture"></p>'
    )
    assert blocks_of(page) == [Block(PARAGRAPH, "seen")]


def test_a_rule_between_two_lines_keeps_them_apart() -> None:
    assert [b.text for b in blocks_of(box("before<hr>after"))] == ["before", "after"]


# --------------------------------------------------------------------- word for word

MESSY = """
<h2>What <em>it</em> is</h2>
<p>Pebble<strong>Pay</strong> lets a vendor take a coin.<br>It runs on the test
   network<!-- note -->, with the topic <code>0.0.3456789</code>.</p>
loose words
<ul>
  <li>one <a href="https://example.test/x">link</a>
    <ul><li>inside<!-- --> <!-- -->item</li></ul>
  </li>
  <li><p>two</p><p>three</p></li>
</ul>
<blockquote><p>a quote</p></blockquote>
<pre><code>line one
line two</code></pre>
<table><tr><td>cell</td><td>next</td></tr></table>
<h4>The end</h4>
"""


def test_no_letter_is_lost_and_none_is_added() -> None:
    page = box(MESSY)
    blocks = blocks_of(page)
    assert letters(plain_text(blocks)) == letters(page.get_text())


def test_the_order_of_the_page_is_kept() -> None:
    texts = [block.text for block in blocks_of(box(MESSY))]
    assert texts == [
        "What it is",
        "PebblePay lets a vendor take a coin. It runs on the test network, with the topic "
        "0.0.3456789.",
        "loose words",
        "one link",
        "inside item",
        "two three",
        "a quote",
        "line one\nline two",
        "cell",
        "next",
        "The end",
    ]


def test_the_plain_text_has_one_block_on_each_line() -> None:
    blocks = [Block(TITLE, "Title", 2), Block(PARAGRAPH, "words"), Block(CODE, "a\nb")]
    assert plain_text(blocks) == "Title\nwords\na\nb"
    assert plain_text([]) == ""
