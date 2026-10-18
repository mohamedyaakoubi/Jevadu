"""The hackathons that a registration may name beyond the collection (hedera/listed.py)."""

from __future__ import annotations

from hackathon_memory.hedera import registry
from hackathon_memory.hedera.listed import LISTED, listed


def test_every_hackathon_of_the_list_has_a_key_that_a_record_accepts() -> None:
    assert LISTED and len({one.key for one in LISTED}) == len(LISTED)
    for one in LISTED:
        registry.record(one.key, "a" * 64, "b" * 40)  # refused if the key had another form
        assert listed(one.key) is one
        assert one.first is None or one.last is None or one.first <= one.last
    assert listed("days/2026-10-01/2026-10-20") is None
