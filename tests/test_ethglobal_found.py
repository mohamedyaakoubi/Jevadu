"""What the walk found: the file, and which sponsor id is Hedera. Everything here is invented."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fakes import HEDERA_ID, OTHER_ID
from hackathon_memory.collect.ethglobal_found import (
    FoundList,
    FoundProject,
    SponsorNotKnown,
    hedera_sponsor,
    load_found,
    save_found,
    winners_of,
)
from hackathon_memory.collect.ethglobal_list import ListedProject, ListPage
from hackathon_memory.collect.polite import CollectorRefused

EVENT = "ETHGlobal Sample Event"
OTHER_EVENT = "ETHGlobal Other Event"
THIRD_ID = "thr03"


def address(name: str) -> str:
    return f"https://ethglobal.com/showcase/{name}"


PEBBLE, CEDAR, QUARTZ, FIG, DUNE = (
    address(n) for n in ("pebble-1", "cedar-2", "quartz-3", "fig-4", "dune-5")
)


def found_with(*projects: tuple[str, tuple[str, ...]], event: str = EVENT) -> FoundList:
    return FoundList(
        started_at="2026-10-10T09:00:00Z",
        updated_at="2026-10-10T09:01:00Z",
        pages_read=1,
        complete=True,
        projects=[FoundProject(page, event, sponsors, 1) for page, sponsors in projects],
    )


FOUND = found_with(
    (PEBBLE, (HEDERA_ID,)),
    (CEDAR, (OTHER_ID,)),
    (DUNE, ()),  # no prize: most projects of the list are like this one
    (QUARTZ, (OTHER_ID, HEDERA_ID)),
    (FIG, (THIRD_ID, HEDERA_ID)),
)


# --------------------------------------------------------------------- what the walk knows


def test_the_walk_keeps_every_project_and_counts_them_by_event() -> None:
    found = FoundList(
        projects=[
            FoundProject(PEBBLE, EVENT, (HEDERA_ID,), 1),
            FoundProject(DUNE, EVENT, (), 1),
            FoundProject(QUARTZ, OTHER_EVENT, (OTHER_ID,), 2),
        ]
    )
    assert found.listed == 3
    assert found.listed_by_event == {EVENT: 2, OTHER_EVENT: 1}  # in the order of the list
    assert [project.page for project in found.with_prize] == [PEBBLE, QUARTZ]


# --------------------------------------------------------------------- which id is Hedera


def test_one_page_seen_by_hand_with_one_sponsor_names_hedera() -> None:
    assert hedera_sponsor(FOUND, [PEBBLE]) == HEDERA_ID


def test_hedera_is_the_one_id_that_all_the_pages_seen_by_hand_have() -> None:
    # Each of the two pages took prizes of two sponsors. Only one id is in both.
    assert hedera_sponsor(FOUND, [QUARTZ, FIG]) == HEDERA_ID
    assert hedera_sponsor(FOUND, [PEBBLE, QUARTZ, FIG]) == HEDERA_ID


def test_a_page_that_the_walk_does_not_know_with_a_prize_decides_nothing() -> None:
    assert hedera_sponsor(FOUND, [address("not-in-the-list-9"), PEBBLE]) == HEDERA_ID
    with pytest.raises(SponsorNotKnown, match="None of the pages seen by hand"):
        hedera_sponsor(FOUND, [address("not-in-the-list-9")])
    with pytest.raises(SponsorNotKnown, match="None of the pages seen by hand"):
        hedera_sponsor(FOUND, [DUNE])  # in the list, but the list names no prize for it
    with pytest.raises(SponsorNotKnown, match="None of the pages seen by hand"):
        hedera_sponsor(FOUND, [])


def test_one_page_with_two_sponsors_is_not_enough() -> None:
    with pytest.raises(SponsorNotKnown, match="share 2 sponsor ids"):
        hedera_sponsor(FOUND, [QUARTZ])


def test_pages_with_no_sponsor_in_common_are_refused() -> None:
    # A page was put on the hand-made list by mistake: it took another sponsor's prize.
    with pytest.raises(SponsorNotKnown, match="share 0 sponsor ids"):
        hedera_sponsor(FOUND, [PEBBLE, CEDAR])


def test_the_most_common_id_is_never_taken_for_hedera() -> None:
    crowd = found_with(
        (PEBBLE, (HEDERA_ID,)),
        (CEDAR, (OTHER_ID,)),
        (QUARTZ, (OTHER_ID,)),
        (FIG, (OTHER_ID,)),
    )
    assert hedera_sponsor(crowd, [PEBBLE]) == HEDERA_ID
    assert winners_of(crowd, HEDERA_ID) == [PEBBLE]


def test_the_winners_come_in_the_order_of_the_list() -> None:
    assert winners_of(FOUND, HEDERA_ID) == [PEBBLE, QUARTZ, FIG]
    assert winners_of(FOUND, OTHER_ID) == [CEDAR, QUARTZ]
    assert winners_of(FOUND, "nobody") == []


# --------------------------------------------------------------------- the file


def test_what_was_found_comes_back_from_the_file_as_it_was(tmp_path: Path) -> None:
    path = tmp_path / "found" / "hedera-list.json"
    save_found(path, FOUND)
    assert load_found(path) == FOUND
    assert not list(path.parent.glob("*.part"))  # written in one step


def test_no_file_means_that_no_walk_was_made(tmp_path: Path) -> None:
    assert load_found(tmp_path / "found" / "hedera-list.json") is None


def test_a_file_of_the_older_walk_is_refused_with_what_to_do(tmp_path: Path) -> None:
    # The first walk kept only the projects with a prize, and a count of the others.
    path = tmp_path / "hedera-list.json"
    older = {
        "format": 1,
        "site": "ethglobal.com",
        "pages_read": 21,
        "complete": True,
        "listed_by_event": {EVENT: 40},
        "with_prize": [{"page": PEBBLE, "event": EVENT, "sponsors": ["a"], "list_page": 1}],
    }
    path.write_text(json.dumps(older), encoding="utf-8")
    with pytest.raises(CollectorRefused, match="older walk") as refusal:
        load_found(path)
    assert "walk again" in str(refusal.value)


def change(record: dict, key: str, value: object) -> dict:
    return record | {key: value}


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("format", 99),
        ("site", "example.com"),
        ("pages_read", "many"),
        ("pages_read", -1),
        ("complete", "yes"),
        ("page_ends_not_shared", None),
        ("projects", {"pebble": 1}),
        ("projects", [{"page": "https://example.com/x", "event": EVENT, "sponsors": ["a"]}]),
        (
            "projects",
            [{"page": PEBBLE + "?page=2", "event": EVENT, "sponsors": ["a"], "list_page": 1}],
        ),
        ("projects", [{"page": PEBBLE, "event": EVENT, "sponsors": [7], "list_page": 1}]),
        ("projects", [{"page": PEBBLE, "event": EVENT, "sponsors": "a", "list_page": 1}]),
        ("projects", [{"page": PEBBLE, "event": "", "sponsors": [], "list_page": 1}]),
        ("projects", [{"page": PEBBLE, "event": EVENT, "sponsors": []}]),
        ("projects", ["pebble"]),
    ],
)
def test_a_file_that_is_not_as_expected_is_refused(tmp_path: Path, key: str, value: object) -> None:
    path = tmp_path / "hedera-list.json"
    save_found(path, FOUND)
    record = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(change(record, key, value)), encoding="utf-8")
    with pytest.raises(CollectorRefused, match="cannot be read"):
        load_found(path)


def test_a_file_that_is_not_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "hedera-list.json"
    path.write_text("{ half a file", encoding="utf-8")
    with pytest.raises(CollectorRefused, match="not taken for an empty one"):
        load_found(path)


def test_the_file_holds_addresses_events_and_ids_only(tmp_path: Path) -> None:
    path = tmp_path / "hedera-list.json"
    save_found(path, FOUND)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert set(record["projects"][0]) == {"page", "event", "sponsors", "list_page"}
    assert set(record) == {
        "format",
        "site",
        "list",
        "started_at",
        "updated_at",
        "pages_read",
        "complete",
        "page_ends_not_shared",
        "projects",
    }


# --------------------------------------------------------------------- pages in order


def a_page(number: int, *names: str, has_next: bool = True) -> ListPage:
    projects = tuple(ListedProject(address(name), EVENT, ()) for name in names)
    return ListPage(number=number, projects=projects, has_next=has_next)


def test_pages_are_taken_in_order_and_each_one_once() -> None:
    found = FoundList()
    found.add(a_page(1, "a-1", "b-2"), "t1")
    with pytest.raises(ValueError, match="in order"):
        found.add(a_page(1, "a-1", "b-2"), "t2")  # the same page again
    with pytest.raises(ValueError, match="in order"):
        found.add(a_page(3, "e-5"), "t2")  # a page was left out
    found.add(a_page(2, "b-2", "c-3", has_next=False), "t3")
    assert (found.pages_read, found.complete, found.listed, found.updated_at) == (2, True, 3, "t3")
    with pytest.raises(ValueError, match="in order"):
        found.add(a_page(3, "c-3", "d-4"), "t4")  # nothing comes after the last page


def test_the_row_that_two_pages_share_is_new_only_once() -> None:
    found = FoundList()
    assert len(found.add(a_page(1, "a-1", "b-2"), "t1")) == 2
    new = found.add(a_page(2, "b-2", "c-3"), "t2")
    assert [row.page for row in new] == [address("c-3")]
    assert found.page_ends_not_shared == 0
    assert [project.list_page for project in found.projects] == [1, 1, 2]


def test_a_page_that_starts_with_another_row_is_noted_and_no_project_comes_twice() -> None:
    found = FoundList()
    found.add(a_page(1, "a-1", "b-2"), "t1")
    # The list moved: page 2 starts with a new row, and names a project of page 1 again.
    new = found.add(a_page(2, "c-3", "a-1", "d-4", has_next=False), "t2")
    assert [row.page for row in new] == [address("c-3"), address("d-4")]
    assert found.page_ends_not_shared == 1
    assert found.listed == 4
