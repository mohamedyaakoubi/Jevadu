"""The hackathons that a registration may name beyond the collection (hedera/listed.py)."""

from __future__ import annotations

from datetime import date

from hackathon_memory.hedera import registry
from hackathon_memory.hedera.listed import LISTED, listed


def test_every_hackathon_of_the_list_has_a_key_that_a_record_accepts() -> None:
    assert LISTED and len({one.key for one in LISTED}) == len(LISTED)
    for one in LISTED:
        registry.record(one.key, "a" * 64, "b" * 40)  # refused if the key had another form
        assert listed(one.key) is one
        assert one.first is None or one.last is None or one.first <= one.last
    assert listed("days/2026-10-01/2026-10-20") is None


def test_the_fss_campus_edition_starts_on_the_day_its_registration_opened() -> None:
    """Its last day is announced when the submission opens, so it stays empty, and the dates of
    a check for it are not judged until then."""
    fss = listed("listed/fss-campus-edition-2026")
    assert fss is not None and fss.first == date(2026, 8, 10) and fss.last is None
