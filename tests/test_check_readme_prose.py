"""The prose of a README for the ledger story of a check (check/submission.readme_prose): its words
line by line, without the marks of Markdown, code or addresses. The README here is invented."""

from __future__ import annotations

from hackathon_memory.check.history import CONSENSUS, TOKENS
from hackathon_memory.check.story import named_services
from hackathon_memory.check.submission import readme_prose

README = (
    "# Pebble\n"
    "**Built** with [Hedera tokens](https://docs.hedera.com/hts/) and `HCS`.\n"
    "| Feature | Hedera |\n"
    "|---|:---:|\n"
    "| Identity (HCS-14) | **Built** |\n"
    "- uses the Token Service\n"
    "```js\n"
    "new TokenCreateTransaction() // HTS\n"
    "```\n"
    "See https://hashscan.io/testnet/hts/0.0.1 for more.\n"
)


def test_the_prose_of_a_readme_keeps_its_words_and_drops_the_marks() -> None:
    assert readme_prose(README).splitlines() == [
        "Pebble",
        "Built with Hedera tokens and HCS.",
        "Feature · Hedera",
        "",  # the row of dashes under the head of the table
        "Identity (HCS-14) · Built",
        "uses the Token Service",
        "",  # the block of code
        "See for more.",
    ]


def test_a_quote_and_the_marks_of_emphasis_are_dropped_too() -> None:
    """The README's own words in the depth of use kept a quote's '>' and the stars around a phrase
    (review layer 1, 28 October 2026). A name such as token_id and a sum such as 5 * 3 stay."""
    text = "> Hedera *records* what happened.\n> > _Nested_ quote, with token_id and 5 * 3.\n"
    assert readme_prose(text).splitlines() == [
        "Hedera records what happened.",
        "Nested quote, with token_id and 5 * 3.",
    ]


def test_a_word_in_an_address_or_in_code_names_no_service() -> None:
    hidden = "Docs: https://docs.hedera.com/hts/ and\n```\nconst HCS = 1\n```\n"
    assert named_services(hidden) == {CONSENSUS, TOKENS}  # in the raw text, they would count
    assert named_services(readme_prose(hidden)) == set()
