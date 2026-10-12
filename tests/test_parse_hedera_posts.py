"""The winners of Hedera's own posts become winner entries. Every post here is invented, in the
shape of one of the five layouts of the real posts."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from hackathon_memory.collect.hedera_posts import POSTS, SITE
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import recorded_run
from hackathon_memory.parse import hedera_posts as reader
from hackathon_memory.parse.winner_entries import WinnerEntriesError
from hackathon_memory.pipeline.parse_pages import STEP, parse_winner_entries

BEMYAPP = "https://hedera20-platform.bemyapp.com/#/projects/{}"
DEVPOST = "https://devpost.com/software/{}"


def post(body: str) -> bytes:
    return f'<html><body><div class="blog-post-content">{body}</div></body></html>'.encode()


def found(event: str, body: str) -> list[tuple]:
    winners = reader.winners_of(event, post(body)).winners
    return [(w["name"], w["track"], w["place"]) for w in winners]


HEDERA20 = (
    f'<div><p>Intro with <a href="https://www.hedera.com/x">projects</a>.</p></div>'
    f"<div><h4>Invented Signing Challenge</h4>"
    f'<p>The winner is <a href="{BEMYAPP.format(1)}">Pebble Pay</a>, a wallet.</p>'
    f"<p>Pebble Pay lets a vendor take a coin.</p><p><strong>Prize – a lamp</strong></p></div>"
    f"<div><h4>Invented Systems Challenge</h4>"
    f'<p><strong>1st place</strong> <a href="{BEMYAPP.format(2)}">Cedar Post</a> moves parcels.</p>'
    f"<p><strong>1st place prize</strong></p>"
    f'<p><strong>2nd place</strong> <a href="{BEMYAPP.format(1)}">Pebble Pay</a> again.</p>'
    f"<p><strong>2nd place prize</strong></p></div>"
    f"<div><h4>Invented Service – First Place</h4>"
    f'<p><a href="{BEMYAPP.format(3)}">Fern Vote</a> counts ballots.</p>'
    f"<p>More about Fern Vote.</p><p><strong>Prize – $1</strong></p></div>"
)


def test_hedera20_a_winner_is_a_link_to_the_platform() -> None:
    assert found("Hedera20", HEDERA20) == [
        ("Pebble Pay", "Invented Signing Challenge", ""),
        ("Cedar Post", "Invented Systems Challenge", "1st place"),
        ("Pebble Pay", "Invented Systems Challenge", "2nd place"),
        ("Fern Vote", "Invented Service", "First Place"),
    ]
    winners = reader.winners_of("Hedera20", post(HEDERA20)).winners
    first = "The winner is Pebble Pay , a wallet. Pebble Pay lets a vendor take a coin."
    assert winners[0]["text"] == first
    assert winners[1]["text"] == "1st place Cedar Post moves parcels."  # the prize is not text
    assert winners[3]["text"] == "Fern Vote counts ballots. More about Fern Vote."


DEVPOST_POST = (
    '<p><strong>Congratulations to the Invented Winners</strong> <a href="https://x.devpost.com/">'
    "the site</a></p>"
    f'<h4>Overall Hackathon Winners</h4><p><a href="{DEVPOST.format("pebble")}">Pebble Pay</a>'
    " – a wallet.</p>"
    "<h4>Invented Challenge</h4><p>The challenge.</p><p><strong>Winners :</strong></p>"
    f'<p>Grand Prize – <a href="{DEVPOST.format("cedar")}">Cedar Post</a> – parcels</p>'
    "<p><strong>Runners Up –</strong></p>"
    f'<p><a href="{DEVPOST.format("fern")}">Fern Vote</a> counts ballots.</p>'
    f'<p>Others – <a href="{DEVPOST.format("a")}">A</a>, <a href="{DEVPOST.format("b")}">B</a></p>'
    f'<p><strong>Prizes –</strong></p><p>$5,000 for <a href="{DEVPOST.format("z")}">Z</a></p>'
)


def test_hedera21_and_22_a_winner_is_a_devpost_link_after_its_label() -> None:
    result = reader.winners_of("Hedera22", post(DEVPOST_POST))
    assert [(w["name"], w["track"], w["place"]) for w in result.winners] == [
        ("Pebble Pay", "Overall Hackathon Winners", "Winner"),
        ("Cedar Post", "Invented Challenge", "Grand Prize"),
        ("Fern Vote", "Invented Challenge", "Runner-up"),
    ]
    assert result.skipped == {"a line that lists several projects": 1}
    assert result.winners[0]["link"] == DEVPOST.format("pebble")


BEYOND = (
    "<h4>The Hackathon Journey</h4><p>Intro.</p><h4>Placed Prizes</h4>"
    "<h4>1. Pebble Pay (Award: $20,000 USD)</h4>"
    "<p>What did you build and why is it important?</p><p>A wallet for vendors.</p>"
    "<p>What did you like about the Hackathon experience?</p><p>Everything.</p>"
    "<h4>2. Cedar Post (Award: $15,000 USD)</h4><p>Project Summary</p><p>Parcels.</p>"
    "<h4>Best in Track</h4><p><strong>Sustainability</strong> : Fern Vote ($10,000 USD)</p>"
    "<p>Project Summary</p><p>Ballots.</p>"
    "<p><strong>Tokenizing the Future</strong> : Pebble Pay ($10,000 USD)</p><p></p>"
    "<h4>Conclusion: invented</h4><p>The end.</p>"
)


def test_beyond_blockchain_placed_prizes_and_best_in_track() -> None:
    assert found("Beyond Blockchain 2023", BEYOND) == [
        ("Pebble Pay", "Placed Prizes", "1st place, $20,000 USD"),
        ("Cedar Post", "Placed Prizes", "2nd place, $15,000 USD"),
        ("Fern Vote", "Sustainability", "Best in Track, $10,000 USD"),
        ("Pebble Pay", "Tokenizing the Future", "Best in Track, $10,000 USD"),
    ]
    winners = reader.winners_of("Beyond Blockchain 2023", post(BEYOND)).winners
    assert [w["text"] for w in winners[:3]] == ["A wallet for vendors.", "Parcels.", "Ballots."]


HELLO_FUTURE = (
    "<p><strong>Invented Hackathon</strong> ran in July.</p>"
    "<h4>Results and Winners</h4><h4>Overall Winners</h4>"
    "<h4>1st Place: Pebble Pay</h4><p><strong></strong>A wallet for vendors.</p>"
    "<ul><li><strong>Prize:</strong> $1</li></ul>"
    "<h4>️ Track Winners</h4><h4>AI</h4>"
    "<ol><li><strong>Cedar Post:</strong> parcels with an agent.</li>"
    "<li>\U0001f3c5<strong>Pebble Pay:</strong> again, with an agent.</li></ol>"
    "<p><strong>Tokenized Assets</strong></p><ol><li><strong>Fern Vote</strong> counts.</li></ol>"
    "<h4>‍♀️ Hashgraph Explorers (Beginner)</h4>"
    "<p>\U0001f31f<strong>Moss Map:</strong> maps moss for walkers.</p><p>Quill Ledger</p>"
    "<h4>What’s Next? Keep building</h4><p><strong>After:</strong> not a winner</p>"
)


def test_hello_future_overall_places_and_track_lists() -> None:
    result = reader.winners_of("Hello Future 2024", post(HELLO_FUTURE))
    assert [(w["name"], w["track"], w["place"]) for w in result.winners] == [
        ("Pebble Pay", "Overall", "1st place"),
        ("Cedar Post", "AI", ""),
        ("Pebble Pay", "AI", ""),
        ("Fern Vote", "Tokenized Assets", ""),
        ("Moss Map", "Hashgraph Explorers (Beginner)", ""),
    ]
    assert result.skipped == {"a line that is only a name": 1}
    assert result.winners[0]["text"] == "1st Place: Pebble Pay A wallet for vendors."


PLACED = (
    "<p><strong>AI &amp; Agents</strong>, <strong>DeFi</strong></p><h2>AI &amp; Agents</h2>"
    "<h3>1st Place: Pebble Pay – Invented Team</h3><p><strong>Prize</strong>: $10,000</p>"
    "<p><strong>Project Description:</strong></p>"
    '<p>A wallet, with <a href="https://pebble.example.test">its site</a>.</p>'
    '<p>See it on DoraHacks <a href="https://dorahacks.io/buidl/7">here</a></p>'
    "<h3>2nd Place – Cedar Post</h3><p><strong>Prize</strong></p><p>Parcels.</p>"
    '<p>Watch the demo <a href="https://www.youtube.com/x">here</a></p>'
    "<h2>DeFi</h2><h3>1st Place – Fern Vote (formerly Fern)</h3><p>Ballots.</p>"
    "<h4>Closing Celebration on a day</h4><h3>1st Place – After The End</h3>"
)


def test_origins_ascension_apex_place_headings_under_tracks() -> None:
    winners = reader.winners_of("Hello Future Apex", post(PLACED)).winners
    assert [(w["name"], w["track"], w["place"]) for w in winners] == [
        ("Pebble Pay", "AI & Agents", "1st place"),  # the team after the dash is left out
        ("Cedar Post", "AI & Agents", "2nd place"),
        ("Fern Vote (formerly Fern)", "DeFi", "1st place"),
    ]
    assert winners[0]["text"] == "A wallet, with its site ."
    assert winners[0]["link"] == "https://dorahacks.io/buidl/7"
    assert winners[1]["link"] is None  # a demo is not the page of the project


def test_a_project_that_won_twice_is_one_record_with_its_tracks_and_its_text() -> None:
    result = reader.winners_of("Beyond Blockchain 2023", post(BEYOND))
    records = reader.records_of("Beyond Blockchain 2023", POSTS["Beyond Blockchain 2023"],
                                result, set())  # fmt: skip
    pebble = next(r for r in records if r["name"] == "Pebble Pay")
    assert pebble["track"] == "Placed Prizes and Tokenizing the Future"
    assert pebble["place"] == "1st place, $20,000 USD; Best in Track, $10,000 USD"
    assert pebble["description_as_published"] == "A wallet for vendors."  # not the bare line
    assert len(records) == 3


def test_a_winner_named_after_a_person_is_left_out_by_its_fingerprint() -> None:
    result = reader.winners_of("Hello Future 2024", post(HELLO_FUTURE))
    people = {reader.fingerprint(" CEDAR post ")}
    records = reader.records_of("Hello Future 2024", POSTS["Hello Future 2024"], result, people)
    assert "Cedar Post" not in [r["name"] for r in records]
    assert result.skipped["a winner named after a person (listed by hand)"] == 1


def test_a_post_without_its_block_of_content_is_refused() -> None:
    with pytest.raises(WinnerEntriesError, match="no block of content"):
        reader.winners_of("Hedera20", b"<html><body><p>moved</p></body></html>")


def save(raw: Path, event: str, body: bytes) -> None:
    url = POSTS[event]
    fetch = FetchResult(url, url + "/", 200, body, "text/html", "2026-10-12T22:00:00Z")
    RawStore(raw / SITE).save(fetch, body, received=body, collector="TestTool/0.1.0")


def test_the_entries_of_the_saved_posts(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    save(raw, "Hedera20", post(HEDERA20))
    save(raw, "Hello Future Apex", post(PLACED))
    entries = reader.read_hedera_posts(raw / SITE, tmp_path / "by-hand" / SITE)
    names = sorted((e.page.event.name, e.page.name) for e in entries)
    assert names == [
        ("Hedera20", "Cedar Post"), ("Hedera20", "Fern Vote"), ("Hedera20", "Pebble Pay"),
        ("Hello Future Apex", "Cedar Post"), ("Hello Future Apex", "Fern Vote (formerly Fern)"),
        ("Hello Future Apex", "Pebble Pay"),
    ]  # fmt: skip
    pebble = next(e.page for e in entries if e.page.name == "Pebble Pay" and e.page.links)
    assert pebble.page.startswith(POSTS[pebble.event.name] + "#")


@pytest.mark.integration
def test_the_parse_step_keeps_them(empty_database: str, tmp_path: Path) -> None:
    migrate(empty_database)
    raw = tmp_path / "raw"
    save(raw, "Hedera22", post(DEVPOST_POST))
    with recorded_run(empty_database, STEP) as run:
        parse_winner_entries(tmp_path / "by-hand", ProjectStore(empty_database), run, saved=raw)
    assert run.counts["winner_entries_new"] == 3
    with psycopg.connect(empty_database) as conn:
        sites = conn.execute("SELECT DISTINCT site FROM projects").fetchall()
    assert sites == [(SITE,)]
