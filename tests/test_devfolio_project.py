"""One saved Devfolio project read into the facts of a card (parse/devfolio_project.py). Every
text, name and number is invented."""

from __future__ import annotations

import json

import pytest

from hackathon_memory.collect.devfolio import Event, Track
from hackathon_memory.parse.blocks import ITEM, PARAGRAPH, TITLE, Block
from hackathon_memory.parse.devfolio_project import (
    PARSER_VERSION,
    markdown_blocks,
    read_devfolio_project,
)
from hackathon_memory.parse.ethglobal_page import PageShapeChanged
from hackathon_memory.parse.project import CODE_LINK, HEDERA_PRIZE, OTHER_LINK, OTHER_PRIZE

API = "https://api.devfolio.co/api/projects/pebble-pay-a1"
EVENTS = {"sample-hack": Event("sample-hack", "sample-hack", "Sample Hack 2025",
                               "2025-02-23T17:00:00+00:00", "2025-03-01T17:30:00+00:00",
                               (Track("h1", "Hedera Builder", "Hedera"),
                                Track("z1", "Zero Track", "Zeroth")))}  # fmt: skip


def saved(**changes: object) -> bytes:
    project = {
        "slug": "pebble-pay-a1", "name": "Pebble Pay",
        "tagline": "Pay a street vendor with a coin.",
        "description": [
            {"title": "The problem it solves", "subtitle": "The event's question, not the team's.",
             "hint": "", "content": "A vendor takes a coin.\nIt settles at once.\n\n## How\n"
             "- One topic on testnet: 0.0.3456781\n- Ask @invented_handle"},
            {"title": "Team", "subtitle": "", "hint": "", "content": "Ana and Bo built it."},
            {"title": "Additional Features", "subtitle": "", "hint": "", "content": ""},
        ],
        "prize_tracks": [
            {"uuid": "h1", "name": "Hedera Builder", "description": "The event's words.",
             "project_tracks": {"uuid": "t1", "description": "We write each sale to a topic."}},
            {"uuid": "z1", "name": "Zero Track", "description": "", "project_tracks": {}},
        ],
        "hashtags": [{"name": "hedera"}, {"name": "React"}],
        "links": "https://github.com/sample-org/pebble-pay, https://pebble.example.test,"
                 "https://x.com/invented_person",
        "video_url": "https://video.example.test/pebble",
        # The first prize of the Hedera track, which Devfolio may file under "Organizer", and a
        # shared prize of another sponsor's track.
        "prizes": [{"uuid": "p1", "name": "First Prize: Hedera Builder"},
                   {"uuid": "p2", "name": "Zero Track - Prize(s)"}],
    }  # fmt: skip
    project.update(changes)
    event = {"name": "Sample Hack 2025", "slug": "sample-hack"}
    return json.dumps({"project": project, "hackathon": event}).encode()


def test_a_project_gives_its_facts_texts_and_prizes() -> None:
    page = read_devfolio_project(saved(), API, EVENTS)
    assert (page.site, page.page, page.site_key) == ("devfolio.co",
                                                     "https://devfolio.co/projects/pebble-pay-a1",
                                                     "pebble-pay-a1")  # fmt: skip
    assert (page.name, page.short_line) == ("Pebble Pay", "Pay a street vendor with a coin.")
    assert (page.event.slug, page.event.name, page.event.starts_at) == (
        "sample-hack", "Sample Hack 2025", "2025-02-23T17:00:00+00:00")  # fmt: skip
    # the team's texts only: the text about the team is cut, an empty one is left out
    assert [section.title for section in page.sections] == [
        "The problem it solves", "Tracks applied: Hedera Builder", "Technologies used"]  # fmt: skip
    first = page.sections[0].blocks
    assert first[:2] == (Block(PARAGRAPH, "A vendor takes a coin. It settles at once."),
                         Block(TITLE, "How", 2))  # fmt: skip
    assert first[2] == Block(ITEM, "One topic on testnet: 0.0.3456781", 1)
    assert "invented_handle" not in page.sections[0].text and page.people_words_hidden >= 2
    assert "The event's question" not in json.dumps([s.text for s in page.sections])
    assert page.sections[2].text == "hedera, React"
    assert [(link.kind, link.url, link.hidden_on) for link in page.links] == [
        (CODE_LINK, "https://github.com/sample-org/pebble-pay", None),
        (OTHER_LINK, "https://pebble.example.test", None),
        (OTHER_LINK, None, "x.com")]  # fmt: skip
    first_prize, shared = page.prizes
    assert (first_prize.sponsor, first_prize.track, first_prize.award) == (
        "Hedera", "Hedera Builder", "First Prize")  # fmt: skip
    assert (shared.sponsor, shared.pool, shared.line) == ("Zeroth", True, "Zero Track - Prize(s)")
    assert page.prize_state == HEDERA_PRIZE and page.has_video and page.parser == PARSER_VERSION
    assert [(found.entity_id, found.network) for found in page.hedera_ids] == [
        ("0.0.3456781", "testnet")]  # fmt: skip


def test_a_prize_of_no_hedera_track_is_another_sponsors() -> None:
    page = read_devfolio_project(saved(prizes=[{"uuid": "p9", "name": "Best Hedera Vibes"}]), API,
                                 EVENTS)  # fmt: skip
    (prize,) = page.prizes
    assert (prize.sponsor, prize.track) == ("", "Best Hedera Vibes")  # no track carries its name
    assert page.prize_state == OTHER_PRIZE
    assert read_devfolio_project(saved(prizes=[]), API, EVENTS).prize_state == "no_prize"


def test_an_unknown_shape_is_said_and_not_guessed() -> None:
    for body in (b"not json", b"[]", json.dumps({"project": {"slug": "x"}}).encode()):
        with pytest.raises(PageShapeChanged):
            read_devfolio_project(body, API, EVENTS)
    page = read_devfolio_project(saved(), API, {})  # an event that the find does not know
    assert page.event.starts_at is None and page.prizes[0].sponsor == ""


def test_markdown_becomes_blocks_with_its_words_as_written() -> None:
    text = "Intro line\nsame paragraph\n\n```\ncode()\n```\n1. first\n  - deeper"
    assert markdown_blocks(text) == (
        Block(PARAGRAPH, "Intro line same paragraph"), Block("code", "code()"),
        Block(ITEM, "first", 1), Block(ITEM, "deeper", 2))  # fmt: skip
