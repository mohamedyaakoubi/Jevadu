"""The list of hackathons in the check of a submission (web/hackathons.py)."""

from __future__ import annotations

from datetime import date

from hackathon_memory.hedera.listed import Listed
from hackathon_memory.web.hackathons import COMING, RUNNING, days_of, groups


def test_the_days_leave_out_the_year_that_the_group_says() -> None:
    assert days_of(date(2026, 9, 4), date(2026, 9, 16), 2026) == "4 to 16 September"
    assert days_of(date(2025, 7, 21), date(2025, 8, 8), 2025) == "21 July to 8 August"
    assert days_of(date(2026, 3, 6), date(2026, 3, 6), 2026) == "6 March"
    assert days_of(date(2023, 12, 28), date(2024, 1, 5), 2024) == (
        "28 December 2023 to 5 January 2024"
    )
    assert days_of(date(2026, 9, 4), date(2026, 9, 16)) == "4 to 16 September 2026"  # no group


def test_unknown_days_are_said_in_words() -> None:
    assert days_of(date(2026, 8, 10), None) == "from 10 August 2026"
    assert days_of(None, date(2026, 10, 20)) == "until 20 October 2026"
    assert days_of(None, None) == "days not announced yet"


def test_the_list_runs_from_the_hackathons_of_now_to_the_oldest_year() -> None:
    collected = [
        ("3", "ETHGlobal Cannes", date(2025, 7, 4), date(2025, 7, 6)),
        ("1", "ETHOnline 2026", date(2026, 9, 4), date(2026, 9, 16)),
        ("2", "ETHGlobal Cannes 2026", date(2026, 4, 3), date(2026, 4, 5)),
    ]
    by_hand = [
        Listed("listed/now", "Now Hack", first=date(2026, 8, 10)),
        Listed("listed/soon", "Soon Hack"),
        Listed("listed/over", "Over Hack", first=date(2025, 1, 6), last=date(2025, 1, 9)),
    ]
    found = groups(collected, by_hand, today=date(2026, 10, 18))
    assert [group.label for group in found] == [RUNNING, COMING, "2026", "2025"]
    texts = [[one.text for one in group.choices] for group in found]
    assert texts == [
        ["Now Hack (from 10 August 2026)"],
        ["Soon Hack (days not announced yet)"],
        ["ETHOnline 2026 (4 to 16 September)", "ETHGlobal Cannes 2026 (3 to 5 April)"],
        ["ETHGlobal Cannes (4 to 6 July)", "Over Hack (6 to 9 January)"],
    ]
    assert [one.value for one in found[2].choices] == ["1", "2"]  # what the form sends
    assert found[3].choices[1].value == "listed/over"


def test_a_hackathon_by_hand_waits_in_coming_until_its_first_day() -> None:
    by_hand = [Listed("listed/now", "Now Hack", first=date(2026, 8, 10))]
    assert groups([], by_hand, today=date(2026, 8, 9))[0].label == COMING
    assert groups([], by_hand, today=date(2026, 8, 10))[0].label == RUNNING
    assert groups([], [], today=date(2026, 8, 10)) == []  # no empty group
