"""The text of a part of a page, block by block and word for word (design 6.1, design rule 4).

A page shows its text in blocks: a paragraph, an item of a list, a title, a piece of code. This
module keeps the words of the page and their order. It adds no word and it loses none. It also
joins nothing that the page keeps apart, and it splits nothing that the page writes as one: a
word in bold stays glued to the dash that follows it.

The tags come from real pages: 162 project pages of ethglobal.com, read on 11 October 2026,
hold p, li, ul, ol, strong, em, code, pre, a, br, blockquote, img and h1 to h4 inside a text.
Such a page is written by React, which puts a comment between two pieces of text. A comment is
not text: BeautifulSoup 4.15.0 leaves it out of get_text() (read in its source, Tag._all_strings).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from bs4 import NavigableString, Tag

PARAGRAPH = "paragraph"
ITEM = "item"
TITLE = "title"
CODE = "code"

_TITLES = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_LISTS = ("ul", "ol")
# Tags that hold blocks and are not one block of text themselves. A cell of a table is here too:
# its words become a paragraph of their own, so no sign is added between two cells.
_BOXES = frozenset(
    {
        "div", "section", "article", "main", "aside", "blockquote", "figure", "figcaption",
        "details", "summary", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "dl", "dt",
        "dd", "center",
    }
)  # fmt: skip
_NOT_TEXT = frozenset({"script", "style", "template", "noscript", "svg"})
# Tags that start on a new line. When one of them stands inside a line of text, its words must
# not run into the words before or after it.
_OWN_LINE = _BOXES | frozenset({"p", "pre", "li", "hr", *_LISTS, *_TITLES})


@dataclass(frozen=True)
class Block:
    """One block of text, as the page shows it."""

    kind: str  # paragraph, item, title or code
    text: str
    level: int = 0  # of a title: 1 to 6. Of an item: how deep its list is, from 1.


def squash(text: str) -> str:
    """The same words with one space between them."""
    return " ".join(text.split())


def plain_text(blocks: list[Block] | tuple[Block, ...]) -> str:
    """The blocks as one text, one block on each line. Code keeps its own lines."""
    return "\n".join(block.text for block in blocks)


def blocks_of(box: Tag) -> list[Block]:
    """The blocks of text inside `box`, in the order of the page."""
    found: list[Block] = []
    loose: list[str] = []  # text that stands in no block of its own

    def add(kind: str, text: str, level: int = 0) -> None:
        if text:
            found.append(Block(kind, text, level))

    def close_loose() -> None:
        text = squash("".join(loose))
        loose.clear()
        add(PARAGRAPH, text)

    def walk(node: Tag, depth: int) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                if type(child) is NavigableString:  # a comment is not text
                    loose.append(str(child))
                continue
            if not isinstance(child, Tag) or child.name in _NOT_TEXT:
                continue
            name = child.name
            if name == "br":
                loose.append("\n")
            elif name in _TITLES:
                close_loose()
                add(TITLE, squash(_words(child)), _TITLES[name])
            elif name == "p":
                close_loose()
                add(PARAGRAPH, squash(_words(child)))
            elif name == "pre":
                close_loose()
                add(CODE, _words(child).strip("\n"))
            elif name == "li":
                close_loose()
                item_depth = max(depth, 1)
                add(ITEM, squash(_words(child, stop_at_lists=True)), item_depth)
                for inner in child.find_all(_LISTS):
                    if _nearest(inner, ("li",), child) is None:  # a list of this item itself
                        walk(inner, item_depth + 1)
            elif name in _LISTS:
                close_loose()
                walk(child, depth + 1)
                close_loose()
            elif name in _BOXES:
                close_loose()
                walk(child, depth)
                close_loose()
            elif name == "hr":
                close_loose()
            else:  # strong, em, code, a and any other tag inside a line
                loose.append(_words(child))

    walk(box, 0)
    close_loose()
    return found


def _words(tag: Tag, *, stop_at_lists: bool = False) -> str:
    """The text inside `tag`, as it is written. A line break of the page becomes a new line.

    With `stop_at_lists`, the text of a list inside `tag` is left out: an item gives its own
    words, and the items of a list inside it are blocks of their own.
    """
    return "".join(_pieces(tag, stop_at_lists))


def _pieces(tag: Tag, stop_at_lists: bool) -> Iterator[str]:
    for child in tag.children:
        if isinstance(child, NavigableString):
            if type(child) is NavigableString:
                yield str(child)
        elif isinstance(child, Tag):
            if child.name in _NOT_TEXT or (stop_at_lists and child.name in _LISTS):
                continue
            if child.name == "br":
                yield "\n"
            elif child.name in _OWN_LINE:
                yield "\n"
                yield from _pieces(child, stop_at_lists)
                yield "\n"
            else:
                yield from _pieces(child, stop_at_lists)


def _nearest(tag: Tag, names: tuple[str, ...], below: Tag) -> Tag | None:
    """The nearest tag around `tag` with one of `names`, looking no higher than `below`."""
    for parent in tag.parents:
        if parent is below:
            return None
        if parent.name in names:
            return parent
    return None
