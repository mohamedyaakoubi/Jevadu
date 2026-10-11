"""One page of the showcase list of ETHGlobal. Every page here is invented."""

from __future__ import annotations

import pytest

from fakes import EVENT, HEDERA_ID, LIST, OTHER_ID, list_page, listed
from hackathon_memory.collect.ethglobal_list import (
    ListedProject,
    ListShapeChanged,
    is_list_url,
    list_page_number,
    list_url,
    read_list_page,
)

RECORDS = [
    listed("pebble-pay", "x1y2z", HEDERA_ID),
    listed("cedar-lens", "k9l8m", OTHER_ID),
    listed("dune-notes", "p0o9i"),
    listed("quartz-notes", "q3w4e", OTHER_ID, HEDERA_ID, HEDERA_ID, event="ETHGlobal Other Event"),
]


# --------------------------------------------------------------------- the addresses of the list


def test_the_first_page_has_no_number_and_the_others_have_one() -> None:
    assert list_url(1) == LIST
    assert list_url(2) == LIST + "&page=2"
    assert list_url(40) == LIST + "&page=40"
    with pytest.raises(ValueError, match="1 to 999"):
        list_url(0)


@pytest.mark.parametrize(
    ("url", "number"),
    [
        (LIST, 1),
        (LIST + "&page=1", 1),
        (LIST + "&page=2", 2),
        (LIST + "&page=999", 999),
        ("https://ethglobal.com/showcase/?partners=hedera&page=7", 7),  # the site's own spelling
        ("https://ethglobal.com/showcase?page=3&partners=hedera", 3),
    ],
)
def test_a_page_of_the_hedera_list_is_known_by_its_address(url: str, number: int) -> None:
    assert list_page_number(url) == number
    assert is_list_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://ethglobal.com/showcase",  # the whole showcase, with no filter
        "https://ethglobal.com/showcase?page=2",
        "https://ethglobal.com/showcase?partners=other",  # another partner
        "https://ethglobal.com/showcase?partners=hedera,other",
        LIST + "&partners=other",  # the filter written twice
        LIST + "&page=2&page=3",
        LIST + "&events=sample",  # one more filter
        LIST + "&q=wallet",  # a search
        LIST + "&page=0",
        LIST + "&page=01",
        LIST + "&page=1000",
        LIST + "&page=two",
        LIST + "&page=",
        LIST + "#cards",
        "https://ethglobal.com/showcase/pebble-pay-x1y2z?partners=hedera",  # a project page
        "https://ethglobal.com/events?partners=hedera",
        "http://ethglobal.com/showcase?partners=hedera",
        "https://example.com/showcase?partners=hedera",
        "https://ethglobal.com.evil.test/showcase?partners=hedera",
        "https://user@ethglobal.com/showcase?partners=hedera",
        "https://ethglobal.com:8443/showcase?partners=hedera",
    ],
)
def test_no_other_address_is_a_page_of_the_list(url: str) -> None:
    assert list_page_number(url) is None
    assert not is_list_url(url)


# --------------------------------------------------------------------- reading a page


def test_a_page_gives_the_address_the_event_and_the_sponsors_of_each_project() -> None:
    page = read_list_page(list_page(2, RECORDS, has_next=True))
    assert page.number == 2
    assert page.has_next is True
    assert page.projects == (
        ListedProject("https://ethglobal.com/showcase/pebble-pay-x1y2z", EVENT, (HEDERA_ID,)),
        ListedProject("https://ethglobal.com/showcase/cedar-lens-k9l8m", EVENT, (OTHER_ID,)),
        ListedProject("https://ethglobal.com/showcase/dune-notes-p0o9i", EVENT, ()),
        ListedProject(
            "https://ethglobal.com/showcase/quartz-notes-q3w4e",
            "ETHGlobal Other Event",
            (OTHER_ID, HEDERA_ID),  # each sponsor once, in the order of the page
        ),
    )


def test_nothing_else_of_a_record_is_read_out() -> None:
    page = read_list_page(list_page(1, RECORDS, has_next=False))
    text = repr(page)
    for kept_out in ("invented short line", "Pebble Pay", "cdn.example.test", "12345"):
        assert kept_out not in text


def test_the_last_page_has_no_next_page() -> None:
    assert read_list_page(list_page(3, RECORDS[:1], has_next=False)).has_next is False
    # A link back to the page before is not a next page.
    assert read_list_page(list_page(3, RECORDS[:1], has_next=False)).number == 3


def test_a_page_with_no_project_is_an_empty_page() -> None:
    page = read_list_page(list_page(9, [], has_next=False))
    assert page.projects == ()
    assert page.has_next is False


# --------------------------------------------------------------------- a page that changed shape


def test_a_page_without_its_data_is_refused() -> None:
    with pytest.raises(ListShapeChanged, match="0 times"):
        read_list_page(b"<html><body><a href='/showcase/a-b'>A</a></body></html>")


def test_a_page_whose_data_names_the_page_twice_is_refused() -> None:
    body = list_page(1, RECORDS, has_next=False)
    twice = body.replace(b"</body>", body[body.index(b"<script>self.__next_f.push([1,") :])
    with pytest.raises(ListShapeChanged, match="2 times"):
        read_list_page(twice)


@pytest.mark.parametrize(
    "data",
    [
        {"currentPage": "1", "projects": []},
        {"currentPage": 0, "projects": []},
        {"currentPage": True, "projects": []},
        {"currentPage": 1},
        {"currentPage": 1, "projects": {"pebble": 1}},
    ],
)
def test_data_without_a_page_number_or_a_list_is_refused(data: dict) -> None:
    with pytest.raises(ListShapeChanged, match="no page number or no list"):
        read_list_page(list_page(1, [], has_next=False, data=data))


def broken(**changes: object) -> dict:
    record = listed("pebble-pay", "x1y2z", HEDERA_ID)
    for key, value in changes.items():
        if value is None:
            del record[key]
        else:
            record[key] = value
    return record


@pytest.mark.parametrize(
    ("record", "problem"),
    [
        (broken(slug=None), "no name part, no id or no prizes part"),
        (broken(uuid=7), "no name part, no id or no prizes part"),
        (broken(prizes=None), "no name part, no id or no prizes part"),
        (broken(slug="pebble/../../hackers"), "do not give a project address"),
        (broken(uuid="x1y2z?page=2"), "do not give a project address"),
        (broken(event=None), "does not name its event"),
        (broken(event={"name": "  "}), "does not name its event"),
        (broken(prizes=[{"prize": {"sponsor": {"name": "Hedera"}}}]), "by an id"),
        (broken(prizes=[{"prize": {"sponsor": {"organization": {"uuid": ""}}}}]), "by an id"),
        (broken(prizes=[{"prize": None}]), "by an id"),
        (broken(prizes=["first place"]), "by an id"),
    ],
)
def test_a_record_that_is_not_as_expected_stops_the_reading(record: dict, problem: str) -> None:
    cards = [listed("pebble-pay", "x1y2z")]
    with pytest.raises(ListShapeChanged, match=problem):
        read_list_page(list_page(1, [record], has_next=False, cards=cards))


def test_a_refusal_never_repeats_text_of_the_page() -> None:
    record = broken(event=None, tagline="A secret plan of Orla Samplewright")
    cards = [listed("pebble-pay", "x1y2z")]
    with pytest.raises(ListShapeChanged) as refusal:
        read_list_page(list_page(1, [record], has_next=False, cards=cards))
    assert "Samplewright" not in str(refusal.value)
    assert "pebble" not in str(refusal.value)


def test_data_that_does_not_fit_the_cards_of_the_page_is_refused() -> None:
    # The data names four projects and the page shows cards for two of them.
    body = list_page(1, RECORDS, has_next=False, cards=RECORDS[:2])
    with pytest.raises(ListShapeChanged, match=r"2 project\(s\) of the data have no card"):
        read_list_page(body)


def test_more_links_in_the_page_than_records_are_fine() -> None:
    # A link to a project that is not in the data, for example in a menu, changes nothing.
    extra = [*RECORDS, listed("menu-pick", "m3n4u")]
    page = read_list_page(list_page(1, RECORDS, has_next=False, cards=extra))
    assert len(page.projects) == 4
