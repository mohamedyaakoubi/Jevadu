"""What the parser reads on a project page of ETHGlobal. The pages are invented."""

from __future__ import annotations

import pytest

from fakes import sample
from hackathon_memory.parse.ethglobal_page import prize_sponsors, took_a_hedera_prize

# --------------------------------------------------------------------- the Hedera prize


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("project_winner.html", True),
        ("project_other_sponsor.html", False),  # won another sponsor's prize, talks about Hedera
        ("project_no_prize.html", False),
    ],
)
def test_a_page_is_a_hedera_winner_only_if_its_prize_block_says_so(
    name: str, expected: bool
) -> None:
    assert took_a_hedera_prize(sample(name)) is expected


def test_the_prize_line_is_read_whatever_the_case_or_the_dash() -> None:
    def block(line: str) -> bytes:
        return f"<h3>Winner of</h3><div><div><h4>{line}</h4></div></div>".encode()

    assert took_a_hedera_prize(block("HEDERA - Best use"))
    assert took_a_hedera_prize(block("Hedera – Best use"))
    assert not took_a_hedera_prize(block("Hederaphile - Best use"))
    assert not took_a_hedera_prize(b"<h3>Finalist</h3><div><h4>Hedera - Best use</h4></div>")


def test_the_sponsors_of_a_page_are_the_parts_before_the_dash() -> None:
    assert prize_sponsors(sample("project_winner.html")) == ["Hedera", "Other Sponsor"]
    assert prize_sponsors(sample("project_no_prize.html")) == []
    twice = "<h3>Winner of</h3><div><h4>Acme-Labs - First</h4><h4>Acme-Labs – Second</h4></div>"
    assert prize_sponsors(twice.encode()) == ["Acme-Labs"]
