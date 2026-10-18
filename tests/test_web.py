"""The website (design 12.1, fourth version): the search, the window of a project, the check of
a submission, the windows of the bottom of the page and the charts, on invented projects, with
Google, GitHub and the mirror node faked."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import pytest

from checkfakes import REGISTER, REPO, TOPIC, RegisterWrites, found_code, nodes
from fakes import project_page
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.settings import Settings
from searchfakes import embed_all, google, three_projects

pytestmark = [
    pytest.mark.integration,
    # Starlette 1.8 prefers another HTTP package for its test client; the warning says nothing
    # about the website.
    pytest.mark.filterwarnings("ignore:Using `httpx` with `starlette.testclient`"),
]
ON_PEBBLE = "A street vendor takes a coin."
VENDOR = "help a street vendor get paid with a coin"
PAYMENTS = "Payments and remittance"
HX = {"HX-Request": "true"}


def field(label: str, value: object, quotes: list[str], state: str = "kept") -> dict:
    return {"label": label, "value": value, "quotes": quotes, "removed": 0, "state": state,
            "why": ""}  # fmt: skip


@pytest.fixture
def site(empty_database: str, tmp_path: Path):  # noqa: ANN201
    from fastapi.testclient import TestClient

    from hackathon_memory.web.app import create_app

    database = three_projects(empty_database)
    client, fake, _ = google()
    embed_all(database, client)
    settings = Settings(_env_file=None, database_url=database, data_dir=str(tmp_path / "data"),
                        hedera_topic_id=REGISTER)  # fmt: skip
    # The saved copy of one page, with the day it was taken from its site.
    url = "https://ethglobal.com/showcase/pebble-pay-x1y2z"
    body = project_page(name="Pebble Pay", slug="pebble-pay")
    saved = FetchResult(url, url, 200, body, "text/html", "2026-10-10T19:00:00Z")
    RawStore(tmp_path / "data" / "raw" / "ethglobal.com").save(
        saved, body, received=body, collector="TestTool/0.1.0"
    )
    with psycopg.connect(database) as conn:
        ids = dict(conn.execute("SELECT name, id FROM projects").fetchall())
        fields = {
            "what_it_does": field("stated", "A vendor takes coins.", [ON_PEBBLE]),
            "how_it_works": field(
                "inferred", ["A buyer pays.", "The vendor is paid."], [ON_PEBBLE]
            ),  # fmt: skip
            "for_whom": field("stated", "Street vendors.", [ON_PEBBLE]),
            "hedera_services": field("not_found", "", [], "not_found"),
            "category": field("inferred", PAYMENTS, [ON_PEBBLE]),
            "problem": field("stated", "", [], "dropped"),
            "solution": field("not_found", "", [], "not_found"),
        }
        conn.execute(
            "INSERT INTO cards (project_id, model, instructions_version, thinking_level, "
            "input_sha256, fields, answer, quotes_given, quotes_found, fields_dropped, attempts) "
            "VALUES (%s, %s, %s, 'HIGH', %s, %s, '{}', 4, 4, 1, 1)",
            (ids["Pebble Pay"], settings.gemini_rewrite_model, INSTRUCTIONS_VERSION, "a" * 64,
             json.dumps(fields)),
        )  # fmt: skip
    asker, github_site = found_code(tmp_path)
    mirrors = nodes()
    writes = RegisterWrites(mirrors["testnet"])

    def make(**changes: object) -> TestClient:
        changed = settings.model_copy(update=changes)
        return TestClient(
            create_app(changed, google=client, llm=client, github_client=asker, mirrors=mirrors,
                       register_writer=writes)
        )  # fmt: skip

    served = make()
    served.github_site = github_site  # what the stand-in GitHub was asked
    served.writes = writes  # what was written to the stand-in register
    served.make = make  # the same site with other settings
    return served, fake, ids, database


def model_calls(fake, since: int = 0) -> int:  # noqa: ANN001
    """How many calls to a model that writes (not an embedding) the stand-in Google got."""
    return len([path for path, _ in fake.requests[since:] if "generateContent" in path])


def order_of(page_text: str) -> list[str]:
    """The ids of the results of a page, in their order."""
    return re.findall(r'<li class="result" id="result-(\d+)"', page_text)


def compare_answer(*parts: tuple[int, list[str]]) -> str:
    return json.dumps({"projects": [
        {"number": number, "same": f"Same {number}.", "differs": f"Differs {number}.",
         "fields_used": used}
        for number, used in parts
    ]})  # fmt: skip


# ----------------------------------------------------------------- the start page and the list


def test_the_start_page_lists_the_projects_and_calls_no_model(site) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    before = len(fake.requests)  # the embeddings of the three projects were made already
    page = client.get("/")
    assert page.status_code == 200
    assert 'id="idea" name="idea"' in page.text and "Order and compare with Gemini" in page.text
    assert "All 3 projects" in page.text and page.text.count('class="result"') == 3
    assert f'hx-get="/project/{ids["Pebble Pay"]}/panel"' in page.text
    assert "The card of a project opens here" not in page.text  # it opens when it is chosen
    assert '<dialog class="viewer" id="viewer"' in page.text
    assert "Building this?" not in page.text  # only under the results of an idea
    assert 'id="tip-proof" popover' in page.text and page.text.count('id="tip-proof"') == 1
    assert len(fake.requests) == before


def test_a_page_after_the_end_of_the_list_says_so(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/", params={"page": "2"})
    assert 'class="result"' not in page.text
    assert "There are no more projects in this list." in page.text


def test_the_list_shows_ten_projects_with_numbered_pages(site) -> None:  # noqa: ANN001
    client, _, _, database = site
    store = ProjectStore(database)
    for number in range(9):  # twelve projects in all
        slug = f"extra-{number}"
        html = project_page(name=f"Extra {number}", slug=slug, short_line="An extra project.")
        address = f"https://ethglobal.com/showcase/{slug}-x1y2z"
        store.save(read_project_page(html, address), "b" * 64)
    first = client.get("/")
    assert first.text.count('class="result"') == 10 and "1 to 10" in first.text
    assert 'aria-current="page"><span class="visually-hidden">Page </span>1</a>' in first.text
    assert 'hx-get="/?page=2"' in first.text and "Next &rsaquo;" in first.text
    second = client.get("/", params={"page": "2"})
    assert second.text.count('class="result"') == 2 and "11 to 12" in second.text


def test_the_numbers_of_the_pages_leave_out_the_middle() -> None:
    from hackathon_memory.web.app import page_numbers

    assert page_numbers(1, 1) == [1]
    assert page_numbers(1, 5) == [1, 2, 3, 4, 5]
    assert page_numbers(1, 83) == [1, 2, 3, None, 83]
    assert page_numbers(40, 83) == [1, None, 38, 39, 40, 41, 42, None, 83]
    assert page_numbers(83, 83) == [1, None, 81, 82, 83]


# ----------------------------------------------------------------- the search


def test_quick_results_ask_no_model_that_writes(site) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    before = len(fake.requests)
    page = client.get("/", params={"idea": VENDOR})
    assert page.status_code == 200
    assert model_calls(fake, before) == 0  # only the embedding of the idea
    assert "Quick results" in page.text and "Gemini has not read them" in page.text
    first = page.text.index('class="result"')
    assert f'hx-get="/project/{ids["Pebble Pay"]}/panel?idea=' in page.text[first : first + 900]
    # The model's sentence, and the words of the idea marked in it.
    assert "A <mark>vendor</mark> takes <mark>coins</mark>." in page.text
    assert 'id="compare-loader"' not in page.text  # no comparison without the button
    # One sentence invites the builder back to check the code before submitting it.
    assert 'Building this? Before you submit, <a href="#check-repo" data-focus-check>' in page.text


def test_the_words_of_the_idea_are_marked_and_a_page_never_runs_as_code(site) -> None:  # noqa: ANN001
    client, _, ids, database = site
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET short_line = %s WHERE id = %s",
                     ("<b>A ballot</b> paid with a coin", ids["Fern Vote"]))  # fmt: skip
    page = client.get("/", params={"idea": "a coin for a ballot"})
    assert "<b>A ballot</b>" not in page.text
    assert "&lt;b&gt;A <mark>ballot</mark>&lt;/b&gt;" in page.text
    assert "<mark>coin</mark>" in page.text


def test_common_words_of_the_idea_are_not_marked(site) -> None:  # noqa: ANN001
    """The marks show why a project is close: "app", "lets" or "take" stand in many ideas and
    are not marked; "vendor" and "coins" are."""
    client, _, _, _ = site
    page = client.get("/", params={"idea": "an app that lets a street vendor take coins"})
    assert "A <mark>vendor</mark> takes <mark>coins</mark>." in page.text
    only_common = client.get("/", params={"idea": "an app that lets people take it"})
    assert "<mark>" not in only_common.text  # no word left to mark


def test_the_ways_to_search(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    for mode in ("meaning", "words"):
        page = client.get("/", params={"idea": VENDOR, "mode": mode})
        assert f'id="mode-{mode}" checked' in page.text
    for old in ("both", "magic"):  # a way of an older page, or none: the default
        page = client.get("/", params={"idea": VENDOR, "mode": old})
        assert 'id="mode-meaning" checked' in page.text
    before = len(fake.requests)
    words = client.get("/", params={"idea": "parcel", "mode": "words"})
    assert len(fake.requests) == before  # by words only, the idea is not embedded
    assert "Where your words stand in its page:" in words.text
    assert "that use your words" in words.text


def test_the_button_orders_with_gemini_and_the_same_search_asks_nothing_again(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    by_meaning = order_of(client.get("/", params={"idea": VENDOR}).text)
    fake.answer_queue = [json.dumps({"closest": [2, 99]})]  # 99 is not in the list
    before = len(fake.requests)
    page = client.get("/", params={"idea": VENDOR, "ai": "1"})
    assert model_calls(fake, before) == 1
    assert order_of(page.text) == [by_meaning[1], by_meaning[0], *by_meaning[2:]]
    assert "Ordered by Gemini" in page.text and "Quick order</a>" in page.text
    assert 'aria-current="true">Gemini\'s order</a>' in page.text  # the order on the screen
    loader = re.search(r'id="compare-loader" hx-get="/compare\?idea=[^&]+&amp;ids=([\d,]+)"',
                       page.text)  # fmt: skip
    assert loader and loader.group(1).split(",") == order_of(page.text)
    sent = [body for path, body in fake.requests if "generateContent" in path][-1]
    assert "Pebble Pay" in json.dumps(sent)  # the model read the lines of the projects
    again = client.get("/", params={"idea": VENDOR, "ai": "1"})  # a reload, or "back"
    assert model_calls(fake, before) == 1 and order_of(again.text) == order_of(page.text)
    old = client.get("/", params={"idea": VENDOR, "mode": "ai"})  # the address of the old page
    assert order_of(old.text) == order_of(page.text) and model_calls(fake, before) == 1


def test_a_wrong_answer_of_gemini_keeps_the_order_of_meaning_and_says_so(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    by_meaning = order_of(client.get("/", params={"idea": VENDOR}).text)
    fake.answer_text = "{}"  # not a list of numbers
    page = client.get("/", params={"idea": VENDOR, "ai": "1"})
    assert order_of(page.text) == by_meaning
    assert "Gemini did not answer in time, so the projects are in the order of meaning" in page.text
    assert 'id="compare-loader"' not in page.text


def test_a_project_opens_in_the_window_with_its_own_address(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    pebble = ids["Pebble Pay"]
    page = client.get("/", params={"idea": VENDOR, "open": str(pebble)})
    assert 'id="viewer-title"' in page.text and f'data-project="{pebble}"' in page.text
    part = client.get(f"/project/{pebble}/panel", params={"idea": VENDOR})
    assert part.status_code == 200 and "<html" not in part.text
    assert 'id="viewer-title"' in part.text and "Compare with my idea" in part.text
    missing = client.get("/project/999999/panel")
    assert missing.status_code == 404 and "There is no project with this number" in missing.text


def test_the_card_of_a_project_names_the_projects_linked_to_it(site) -> None:  # noqa: ANN001
    """Two projects with the same code: the card of each names the other, says why, and opens
    it in the same window (design 8.4). A project with no link shows no box."""
    from hackathon_memory.db.repositories import RepositoryStore

    client, _, ids, database = site
    pebble, cedar, fern = ids["Pebble Pay"], ids["Cedar Post"], ids["Fern Vote"]
    assert "Linked projects" not in client.get(f"/project/{pebble}/panel").text
    RepositoryStore(database).link({pebble: REPO, cedar: REPO})
    part = client.get(f"/project/{pebble}/panel")
    box = part.text.split("Linked projects", 1)[1].split("</section>", 1)[0]
    assert f'hx-get="/project/{cedar}/panel"' in box and "The same repository." in box
    assert f"/project/{fern}" not in box
    page = client.get(f"/project/{cedar}")  # the page of its own names the link too
    assert "Linked projects" in page.text and f'hx-get="/project/{pebble}/panel"' in page.text


def test_the_card_keeps_the_three_sources_apart(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get(f"/project/{ids['Pebble Pay']}")
    assert page.status_code == 200
    text = page.text
    places = [text.index(words) for words in
              ("On the ledger<", "The code<", "From the project's page<",
               "Written by a model<")]  # fmt: skip
    assert places == sorted(places)  # the facts first, then the page, then the model
    assert "Pebble Pay, invented." in text  # the short line, word for word
    assert "Inferred: less sure" in text and ">Stated<" in text
    assert f"&ldquo;{ON_PEBBLE}&rdquo;" in text  # the quote that the field rests on
    assert "Not shown: none of the sentences that the model gave was found" in text
    assert "Neither the page nor the code names a Hedera ID" in text
    assert "as the page stood on 10 October 2026" in text  # the day it was saved from its site
    assert "compare-section" not in text  # no idea on its own page, so no comparison


def test_a_project_without_a_model_card_says_so(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get(f"/project/{ids['Cedar Post']}")
    assert "No card has been written by a model for this project yet" in page.text


def test_an_unknown_project_is_not_found(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/project/999999")
    assert page.status_code == 404 and "There is no project with this number" in page.text


def test_without_google_the_words_are_searched_and_the_page_says_so(site) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    fake.fail_with = (503, "unavailable")
    page = client.get("/", params={"idea": "a vendor and a coin"})
    assert page.status_code == 200
    assert "only its words were searched" in page.text
    assert f"/project/{ids['Pebble Pay']}/panel?idea=" in page.text


def test_without_the_database_the_page_says_how_to_start_it() -> None:
    from fastapi.testclient import TestClient

    from hackathon_memory.web.app import create_app

    # Nothing listens on port 1. On some computers such a connection is dropped and not refused;
    # the website gives up after a few seconds and says what to do.
    settings = Settings(_env_file=None, database_url="postgresql://nobody@127.0.0.1:1/none")
    client = TestClient(create_app(settings, google=object()))
    page = client.get("/", params={"idea": "anything"})
    assert page.status_code == 503 and "docker compose up -d --wait db" in page.text
    start = client.get("/")  # the start page still opens, without the filters, and says why
    assert start.status_code == 200 and "docker compose up -d --wait db" in start.text
    assert 'id="filter-event"' not in start.text


def test_the_text_of_a_page_is_shown_as_text_never_as_code(site) -> None:  # noqa: ANN001
    client, _, ids, database = site
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET short_line = %s WHERE id = %s",
                     ("<script>alert(1)</script>", ids["Fern Vote"]))  # fmt: skip
    page = client.get(f"/project/{ids['Fern Vote']}")
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text


def test_a_long_idea_is_cut_and_the_page_says_so(site) -> None:  # noqa: ANN001
    from hackathon_memory.web.app import LONGEST_IDEA

    client, _, _, _ = site
    page = client.get("/", params={"idea": "coin " * (LONGEST_IDEA // 4)})
    assert f"The idea was longer than {LONGEST_IDEA:,} characters, so it was cut." in page.text


# ----------------------------------------------------------------- the windows and the sources


def test_the_windows_of_the_bottom_of_the_page(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    how = client.get("/about/how", headers=HX)
    assert how.status_code == 200 and "<html" not in how.text
    assert "The search, step by step" in how.text and "The ways to search, measured" in how.text
    assert "What this tool cannot do" in how.text
    page = client.get("/about/how")  # without JavaScript, a whole page
    assert "<html" in page.text and "Back to the search" in page.text
    assert client.get("/method").status_code == 200
    questions = client.get("/about/questions", headers=HX)
    assert "Why does the AI not judge, score or rank the projects?" in questions.text
    assert "ETHGlobal was asked before any program read its showcase." in questions.text
    sources = client.get("/about/sources", headers=HX)
    assert sources.text.count('<li id="ref-') >= 15
    assert client.get("/about/nothing").status_code == 404


def test_each_term_links_its_numbered_source(site) -> None:  # noqa: ANN001
    from hackathon_memory.web.references import BY_KEY, NUMBER

    client, _, _, _ = site
    page = client.get("/")
    for key in ("hedera", "mirror", "account", "topic", "token", "contract", "embedding"):
        link = f'<a href="{BY_KEY[key].url}" target="_blank" rel="noopener">[{NUMBER[key]}]'
        assert link in page.text, key
    assert NUMBER["hedera"] == 1  # Hedera's own documentation comes first


# ----------------------------------------------------------------- the comparison (design 8.3)


def test_the_comparison_names_the_texts_it_used(site) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    pebble, cedar, fern = ids["Pebble Pay"], ids["Cedar Post"], ids["Fern Vote"]
    fake.answer_text = compare_answer((1, ["what_it_does", "made_up"]), (2, ["short_line"]),
                                      (9, ["name"]))  # fmt: skip
    part = client.get("/compare", params={"idea": "a coin for a vendor",
                                          "ids": f"{pebble},{cedar},{fern}"})  # fmt: skip
    assert part.status_code == 200
    assert f'id="compare-{pebble}" hx-swap-oob="true"' in part.text
    assert "Same 1." in part.text and "Differs 2." in part.text
    assert "Same 9." not in part.text  # a number that is not in the list
    assert "By Gemini, from what it does." in part.text  # "made_up" was dropped
    assert "By Gemini, from the short line." in part.text
    assert part.text.count("No comparison was written for this project.") == 1  # the third
    sent = [body for path, body in fake.requests if "generateContent" in path][-1]
    assert "A vendor takes coins." in json.dumps(sent)  # Pebble's card field went to the model


def test_a_comparison_is_kept_for_a_day_and_shown_in_the_window(site) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    pebble, cedar = ids["Pebble Pay"], ids["Cedar Post"]
    fake.answer_text = compare_answer((1, ["what_it_does"]), (2, ["short_line"]))
    before = len(fake.requests)
    client.get("/compare", params={"idea": VENDOR, "ids": f"{pebble},{cedar}"})
    assert model_calls(fake, before) == 1
    again = client.get("/compare", params={"idea": VENDOR, "ids": f"{pebble},{cedar}"})
    assert model_calls(fake, before) == 1 and "Same 1." in again.text
    window = client.get(f"/project/{pebble}/panel", params={"idea": VENDOR})
    assert "Same 1." in window.text and "Compare with my idea" not in window.text
    other = client.get(f"/project/{pebble}/panel", params={"idea": "another idea entirely"})
    assert "Compare with my idea" in other.text  # nothing kept for another idea
    assert model_calls(fake, before) == 1


def test_one_comparison_in_the_window_replaces_its_button(site) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    fern = ids["Fern Vote"]
    fake.answer_text = compare_answer((1, ["short_line"]))
    part = client.get("/compare", params={"idea": VENDOR, "ids": str(fern), "one": "1"})
    assert part.status_code == 200 and f'id="one-compare-{fern}"' in part.text
    assert "hx-swap-oob" not in part.text and "Same 1." in part.text


def test_a_comparison_that_fails_says_so_in_each_place(site) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    assert client.get("/compare", params={"idea": "x"}).status_code == 400
    fake.fail_with = (503, "unavailable")
    asked = f"{ids['Pebble Pay']},{ids['Cedar Post']}"
    part = client.get("/compare", params={"idea": "a coin", "ids": asked})
    assert part.status_code == 503
    assert part.text.count("could not be written just now") == 2


# ----------------------------------------------------------------- the filters (design 8.2)


def test_the_filters_offer_what_the_projects_have(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/")
    assert 'name="event"' in page.text and 'name="life"' in page.text
    assert "ETHGlobal Sample Event (3)" in page.text
    assert f"{PAYMENTS} (1)" in page.text  # the one card of the fixture
    assert "1 of 3 projects have one so far" in page.text


def test_a_filtered_search_shows_only_the_matching_projects(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get("/", params={"idea": VENDOR, "category": PAYMENTS})
    assert page.text.count('class="result"') == 1
    assert f"/project/{ids['Pebble Pay']}/panel?idea=" in page.text
    assert "category=Payments+and+remittance" in page.text  # the link keeps the filter
    assert "Clear the filters" in page.text
    card = client.get(f"/project/{ids['Pebble Pay']}", params={"idea": "a coin",
                                                               "category": PAYMENTS})  # fmt: skip
    assert 'href="/?idea=a+coin&amp;category=Payments+and+remittance#results"' in card.text


def test_a_filter_without_an_idea_narrows_the_list(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/", params={"category": PAYMENTS})
    assert "1 project matches the filters" in page.text and page.text.count('class="result"') == 1


def test_a_filter_keeps_the_closest_projects_that_have_its_value(site, monkeypatch) -> None:  # noqa: ANN001
    """The number next to a value is what the filter leaves (design 8.2): a filter narrows the
    closest projects of a search, it does not search again among all the projects."""
    from hackathon_memory.web import app as web_app

    client, _, _, _ = site
    monkeypatch.setattr(web_app, "SHOWN", 1)  # "the closest" is one project in this test
    vendor = client.get("/", params={"idea": VENDOR, "category": PAYMENTS})
    assert "1 to 1 of the 1 with these filters, among the 1 closest" in vendor.text
    assert vendor.text.count('class="result"') == 1 and "Pebble Pay" in vendor.text
    ballot = client.get("/", params={"idea": "a ballot for a small club", "category": PAYMENTS})
    assert "None of the 1 projects closest to your idea has these values" in ballot.text
    assert 'class="result"' not in ballot.text  # Pebble Pay has the value, but it is not close


def test_filters_that_leave_no_project_say_so_and_ask_nothing(site) -> None:  # noqa: ANN001
    client, fake, ids, database = site
    with psycopg.connect(database) as conn:
        other = conn.execute(
            "INSERT INTO events (site, slug, name, ends_on) "
            "VALUES ('ethglobal.com', 'other', 'Other Event', '2025-05-05') RETURNING id"
        ).fetchone()[0]
        conn.execute("UPDATE projects SET event_id = %s WHERE id = %s", (other, ids["Fern Vote"]))
    before = len(fake.requests)
    page = client.get("/", params={"idea": "a coin", "event": str(other), "category": PAYMENTS})
    assert "No project matches these filters" in page.text
    assert 'class="result"' not in page.text
    assert len(fake.requests) == before  # the idea was not even embedded


def test_a_filter_value_that_no_project_has_is_left_out_and_said(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/", params={"idea": "a coin", "proof": "proof_found"})
    assert "No project has the value given for the Hedera proof" in page.text
    assert page.text.count('class="result"') >= 1  # searched without that filter


# ----------------------------------------------------------------- the check of a submission (S3)


def checkable(database: str) -> str:
    """Pebble Pay keeps the code of the submission, and the event's end is typed in. Returns the
    number of the event, as the form sends it."""
    from hackathon_memory.db.repositories import RepositoryStore

    with psycopg.connect(database) as conn:
        conn.execute("UPDATE events SET ends_on = '2026-03-08'")
        (pebble,) = conn.execute("SELECT id FROM projects WHERE name = 'Pebble Pay'").fetchone()
        (event,) = conn.execute("SELECT id FROM events").fetchone()
    RepositoryStore(database).link({pebble: REPO})
    return str(event)


def test_a_submission_is_checked_by_programs_with_no_model_that_writes(site) -> None:  # noqa: ANN001
    client, fake, _, database = site
    event = checkable(database)
    before = len(fake.requests)
    asked = {"repo": "github.com/sample-org/pebble-pay/tree/main", "event": event}
    part = client.get("/check", params=asked, headers=HX)
    assert part.status_code == 200 and '<h2 id="viewer-title"' in part.text
    assert "github.com/sample-org/pebble-pay</h2>" in part.text
    assert "Proof: found" in part.text and "No model wrote anything here." in part.text
    assert f'href="https://hashscan.io/testnet/topic/{TOPIC}"' in part.text
    assert "Seen before" in part.text and "The same repository." in part.text
    assert "The closest past projects" in part.text and "Cedar Post" in part.text
    assert model_calls(fake, before) == 0  # the closest projects need an embedding only
    assert len(client.github_site.seen) == 3  # the facts, the README and the version, once
    assert 'Version checked: <span class="id">7260ea729063</span>' in part.text
    assert "the newest commit of the branch main" in part.text  # the branch, by its name
    day = r"\d{1,2} [A-Z][a-z]+ \d{4}"
    assert re.search(rf"Read from GitHub on {day}: its facts, its README \(README\.md\) and the "
                     r"version\.", part.text)  # fmt: skip
    page = client.get("/check", params=asked)  # without JavaScript: a page of its own
    assert page.status_code == 200 and '<h1 id="viewer-title"' in page.text
    assert len(client.github_site.seen) == 3  # GitHub was not asked again


def test_gemini_compares_a_checked_submission_with_its_closest_projects(site) -> None:  # noqa: ANN001
    """Only the named button calls Gemini; its answers fill the places of the check, which have
    their own ids, and the button gives way to a line that says who wrote them."""
    client, fake, _, database = site
    event = checkable(database)
    part = client.get("/check", params={"repo": REPO, "event": event}, headers=HX)
    before = len(fake.requests)
    asked = re.search(r'hx-get="(/compare\?repo=[^"]+&amp;place=check)"', part.text)
    places = re.findall(r'id="check-compare-(\d+)"', part.text)
    assert asked is not None and f"Compare these {len(places)} with Gemini</button>" in part.text
    assert len(asked.group(1)) < 200  # the address names the repository, not the README
    assert places and model_calls(fake, before) == 0  # nothing is asked before the button
    fake.answer_text = compare_answer(*[(n, ["what_it_does"]) for n in range(1, len(places) + 1)])
    done = client.get(asked.group(1).replace("&amp;", "&"), headers=HX)
    assert done.status_code == 200 and model_calls(fake, before) == 1
    assert all(f'id="check-compare-{pid}" hx-swap-oob="true"' in done.text for pid in places)
    assert "Same 1." in done.text and "Compared by Gemini with the README" in done.text
    again = client.get(asked.group(1).replace("&amp;", "&"), headers=HX)
    assert "Same 1." in again.text and model_calls(fake, before) == 1  # kept for one day
    never = {"repo": "github.com/nobody/never-checked", "ids": places[0], "place": "check"}
    unknown = client.get("/compare", params=never, headers=HX)
    assert unknown.status_code == 400 and model_calls(fake, before) == 1  # no README was saved


def test_a_check_without_a_repository_or_with_wrong_days_says_what_to_do(site) -> None:  # noqa: ANN001
    client, _, _, database = site
    event = checkable(database)
    wrong = client.get("/check", params={"repo": "my project", "event": event}, headers=HX)
    assert wrong.status_code == 400 and "This is not the link of a repository" in wrong.text
    backwards = {"repo": REPO, "event": "other", "starts": "2026-03-08", "ends": "2026-03-06"}
    late = client.get("/check", params=backwards, headers=HX)
    assert late.status_code == 400 and "Type the first and the last day" in late.text
    unknown = client.get("/check", params={"repo": REPO, "event": "99999"}, headers=HX)
    assert unknown.status_code == 400 and "There is no such hackathon" in unknown.text
    assert client.github_site.seen == []  # nothing was asked of GitHub
    typed = {"repo": REPO, "event": "other", "starts": "2026-03-06", "ends": "2026-03-08"}
    days = client.get("/check", params=typed, headers=HX)
    assert days.status_code == 200 and "6 March 2026 to 8 March 2026" in days.text


def test_a_transaction_named_on_a_page_is_shown_as_one_action(site) -> None:  # noqa: ANN001
    """A single transaction is its own kind of Hedera ID: the window says what the action was,
    when it happened, and links to it on HashScan (design 7.1)."""
    from hackathon_memory.check.ledger import LedgerFacts
    from hackathon_memory.db.ledger import LedgerStore

    client, _, ids, database = site
    tx = "0.0.7162784-1772884800-640883616"
    LedgerStore(database).save_facts(LedgerFacts(
        tx, "testnet", datetime(2026, 10, 18, tzinfo=UTC), found=True, kind="transaction",
        ledger_id=tx, created_at=datetime(2026, 3, 7, 12, tzinfo=UTC),
        first_activity_at=datetime(2026, 3, 7, 12, tzinfo=UTC),
        last_activity_at=datetime(2026, 3, 7, 12, tzinfo=UTC), empty=False,
        details={"name": "TOKENCREATION", "result": "SUCCESS"},
    ))  # fmt: skip
    with psycopg.connect(database) as conn:
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, %s, 'testnet', 'transaction', 'page', "
            "'invented', true) RETURNING id", (ids["Pebble Pay"], tx)).fetchone()  # fmt: skip
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                     "VALUES (%s, 'testnet', 'proof_found')", (hedera_id,))  # fmt: skip
    part = client.get(f"/project/{ids['Pebble Pay']}/panel")
    assert "A transaction: the creation of a token, on 7 March 2026." in part.text
    assert f'href="https://hashscan.io/testnet/transaction/{tx}"' in part.text


def test_the_hackathon_of_a_check_is_optional(site) -> None:  # noqa: ANN001
    """The tool is a memory, not a live view: with no hackathon, the facts are shown with their
    own dates and not judged, and the register asks for one (design 12.1, S3)."""
    client, _, _, database = site
    checkable(database)
    start = client.get("/")
    assert '<option value="">No hackathon: show the facts only</option>' in start.text
    assert "ETHGlobal Sample Event, 6 March 2026 to 8 March 2026" in start.text  # a dated one
    part = client.get("/check", params={"repo": REPO, "event": ""}, headers=HX)
    assert part.status_code == 200 and "no hackathon given" in part.text
    assert "Proof: found, dates not judged" in part.text
    head = part.text.split("</header>")[0]  # the marks of the check itself
    assert "Found; its dates are not judged" in part.text and "Life:" not in head
    assert "A registration names its hackathon." in part.text
    assert "Write it on Hedera" not in part.text
    form = {"repo": REPO, "event": "", "starts": "", "ends": "", "account": ""}
    refused = client.post("/register", data=form, headers=HX)
    assert refused.status_code == 400 and "A registration names its hackathon" in refused.text
    assert client.writes.written == []


@pytest.mark.browser
def test_a_project_of_a_check_opens_over_it_and_the_check_comes_back(site, chromium) -> None:  # noqa: ANN001
    client, fake, _, database = site
    event = checkable(database)
    fake.answer_text = compare_answer((1, ["what_it_does"]), (2, ["what_it_does"]))
    page = served(chromium, client, reduced_motion="reduce")
    page.goto("http://site.test/")
    page.fill("#check-repo", "github.com/sample-org/pebble-pay")
    page.select_option("#check-event", event)
    page.locator("#check button[type=submit]").click()
    page.wait_for_selector("#viewer[open] .check-result")
    page.locator("[data-check-compare]").click()  # Gemini, on its named button only
    page.wait_for_selector(".check-result .hm-compare-text")
    assert "Compared by Gemini with the README" in page.locator("#check-compare-ask").inner_text()
    page.locator(".check-result .hm-close-name a").first.click()
    page.wait_for_selector("#viewer[open] .project[data-project]")
    assert page.locator("[data-back-to-check]").is_visible()
    assert not page.locator("[data-viewer-step]").first.is_visible()  # no list to step through
    page.locator("[data-back-to-check]").click()
    page.wait_for_selector("#viewer[open] .check-result")
    assert page.locator("#register-form").count() == 1  # the check as it was
    page.context.close()


# ----------------------------------------------------------------- the register (S4)


def test_a_checked_submission_is_registered_once_and_read_back(site) -> None:  # noqa: ANN001
    import hashlib

    client, _, _, database = site
    event = checkable(database)
    asked = {"repo": "github.com/sample-org/pebble-pay", "event": event}
    check = client.get("/check", params=asked, headers=HX)
    assert "The register does not hold this code yet." in check.text
    assert "ethglobal.com/sample-event" in check.text and "Write it on Hedera" in check.text
    form = {**asked, "starts": "", "ends": "", "account": "0.0.4567890"}
    done = client.post("/register", data=form, headers=HX)
    assert done.status_code == 200 and "Registered on Hedera" in done.text
    assert "<dt>Number</dt><dd>1, on the topic" in done.text
    assert "https://hashscan.io/testnet/transaction/1791585601.000000001" in done.text
    (payload,) = client.writes.written
    assert json.loads(payload) == {
        "v": 2, "event": "ethglobal.com/sample-event",
        "commit": "7260ea7290637399c6ac181ed893a567144d96eb",
        "code": hashlib.sha256(REPO.encode()).hexdigest(),
        "account": hashlib.sha256(b"0.0.4567890").hexdigest(),
    }  # fmt: skip
    assert b"github" not in payload and b"pebble" not in payload  # no link in clear text
    again = client.post("/register", data=form, headers=HX)
    assert "Registered already" in again.text and len(client.writes.written) == 1
    later = client.get("/check", params=asked, headers=HX)
    assert "Registered before." in later.text and "number 1" in later.text
    assert "Write it on Hedera" not in later.text  # it is registered for this event already


def test_a_registration_needs_a_checked_repository_and_a_real_account(site) -> None:  # noqa: ANN001
    client, _, _, database = site
    event = checkable(database)
    form = {"repo": REPO, "event": event, "starts": "", "ends": "", "account": ""}
    first = client.post("/register", data=form, headers=HX)
    assert first.status_code == 400 and "Check the repository first" in first.text
    client.get("/check", params={"repo": REPO, "event": event}, headers=HX)
    wrong = client.post("/register", data={**form, "account": "my wallet"}, headers=HX)
    assert wrong.status_code == 400 and "A Hedera account looks like 0.0.12345" in wrong.text
    assert client.writes.written == []
    page = client.post("/register", data=form)  # without JavaScript: a page of its own
    assert page.status_code == 200 and "<h1" in page.text and len(client.writes.written) == 1


def test_a_closed_register_is_said_and_offers_no_button(site) -> None:  # noqa: ANN001
    client, _, _, database = site
    event = checkable(database)
    closed = client.make(hedera_topic_id="")
    check = closed.get("/check", params={"repo": REPO, "event": event}, headers=HX)
    assert "The public register is not open yet" in check.text
    assert "Write it on Hedera" not in check.text


# ----------------------------------------------------------------- the charts (design 12.1, S5)


def test_projects_linked_across_events_come_first_in_the_charts(site) -> None:  # noqa: ANN001
    from hackathon_memory.db.repositories import RepositoryStore

    client, _, ids, database = site
    page = client.get("/", params={"view": "charts"})
    assert page.text.index('id="chart-linked"') > page.text.index("<canvas data-chart=")
    with psycopg.connect(database) as conn:
        (later,) = conn.execute(
            "INSERT INTO events (site, slug, name) VALUES ('ethglobal.com', 'later', 'Later') "
            "RETURNING id"
        ).fetchone()
        conn.execute("UPDATE projects SET event_id = %s WHERE id = %s", (later, ids["Cedar Post"]))
    RepositoryStore(database).link({ids["Pebble Pay"]: REPO, ids["Cedar Post"]: REPO})
    page = client.get("/", params={"view": "charts"})
    assert "Linked across events: 1 group, 2 projects" in page.text
    assert page.text.index('id="chart-linked"') < page.text.index("<canvas data-chart=")


def test_the_charts_count_the_list_on_the_screen(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    before = len(fake.requests)
    page = client.get("/", params={"view": "charts"})
    assert page.status_code == 200 and 'aria-current="true">Charts</a>' in page.text
    assert "Counted now from the tables, for 3 projects." in page.text
    assert page.text.count("<canvas data-chart=") >= 3 and "Linked across events" in page.text
    assert 'href="https://ethglobal.com/events/sample-event"' in page.text  # the event's page
    assert 'class="result"' not in page.text and len(fake.requests) == before
    search = client.get("/", params={"idea": VENDOR, "view": "charts"})
    assert "for 3 projects: the closest to your idea" in search.text
    assert model_calls(fake, before) == 0  # charts call no model that writes


def test_a_share_is_shown_only_with_twenty_projects_behind_it() -> None:
    from hackathon_memory.search.counts import Tally
    from hackathon_memory.web.charts import build

    few = Tally(
        projects=3, proof=__import__("collections").Counter({"proof_found": 2, "no_id_given": 1})
    )
    chart = next(one for one in build(few, {}).charts if one.key == "proof")
    assert [(bar.words, bar.count, bar.share) for bar in chart.bars] == [
        ("Proof found", 2, None), ("No Hedera ID given", 1, None)]  # fmt: skip
    many = Tally(
        projects=40, proof=__import__("collections").Counter({"proof_found": 10, "no_id_given": 30})
    )
    chart = next(one for one in build(many, {}).charts if one.key == "proof")
    assert [bar.share for bar in chart.bars] == [25, 75]
    assert '"labels": ["Proof found", "No Hedera ID given"]' in chart.data()


# ------------------------------------------------- smaller parts


def test_the_page_of_an_event_is_the_page_its_projects_link_to() -> None:
    from hackathon_memory.web.data import event_page

    assert (
        event_page("ethglobal.com", "newyork2026", None)
        == "https://ethglobal.com/events/newyork2026"
    )
    winners = "https://hedera-hackathon.hashgraph.swiss/#winners"
    assert event_page("hedera-hackathon.hashgraph.swiss", "x", winners) == winners.split("#")[0]
    assert event_page("devpost.com", "hedera21", None) is None  # no page known: no link


def test_a_date_is_written_as_the_pages_write_it() -> None:
    from hackathon_memory.web.app import day, iso_day

    assert day(date(2025, 7, 6)) == "6 July 2025"
    assert day(datetime(2026, 10, 10, 19, 0, tzinfo=UTC)) == "10 October 2026"
    assert iso_day("2026-10-14") == "14 October 2026" and iso_day("not a day") == "not a day"


def test_the_reads_of_github_are_named_once_for_each_day() -> None:
    from types import SimpleNamespace

    from hackathon_memory.web.app import github_reads

    code = SimpleNamespace(fetched_at="2026-10-16T08:00:00Z")
    readme = SimpleNamespace(status="found", name="README.md", fetched_at="2026-10-16T08:00:01Z")
    version = SimpleNamespace(status="found", fetched_at="2026-10-18T05:00:00Z")
    assert github_reads(code, readme, version) == (
        "Read from GitHub: its facts and its README (README.md) on 16 October 2026, "
        "the version on 18 October 2026."
    )
    assert github_reads(code, SimpleNamespace(status="none"), None) == (
        "Read from GitHub on 16 October 2026: its facts."
    )  # a README that is missing is said apart


def test_every_page_has_a_tab_icon_and_a_way_to_the_results(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/", params={"idea": "a coin for a vendor"})
    assert '<link rel="icon" href="/static/icon.svg"' in page.text
    assert client.get("/static/icon.svg").status_code == 200
    assert 'action="/"' in page.text and 'id="results"' in page.text
    assert 'href="#results">Skip to the results</a>' in page.text


# ------------------------------------------------- the page's script, in a real browser


@pytest.fixture(scope="module")
def chromium():  # noqa: ANN201
    """Only a browser runs htmx and the page's script. Skipped where Playwright or its
    Chromium is not installed: python -m playwright install chromium."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch()
        except sync_api.Error as error:
            pytest.skip(f"no Chromium for Playwright here: {error.message.splitlines()[0]}")
        yield browser
        browser.close()


SEARCH = "http://site.test/?idea=help+a+street+vendor+get+paid+with+a+coin"


def served(chromium, client, before_compare=lambda: None, **context):  # noqa: ANN001, ANN201
    """A page whose every request is answered by the website's test client: no server runs."""
    page = chromium.new_context(**context).new_page()

    def answer(route) -> None:  # noqa: ANN001
        parts = urlsplit(route.request.url)
        if parts.path == "/compare":
            before_compare()
        headers = {k: v for k, v in route.request.headers.items() if k.lower().startswith("hx-")}
        address = parts.path + (f"?{parts.query}" if parts.query else "")
        if route.request.method == "POST":  # the register's form
            headers["content-type"] = route.request.headers.get("content-type", "")
            got = client.post(address, content=route.request.post_data_buffer, headers=headers)
        else:
            got = client.get(address, headers=headers)
        route.fulfill(status=got.status_code, body=got.content,
                      headers={"content-type": got.headers["content-type"]})  # fmt: skip

    page.route(lambda url: url.startswith("http://site.test/"), answer)
    return page


@pytest.mark.browser
def test_each_comparison_takes_its_place(site, chromium) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    fake.answer_queue = [json.dumps({"closest": [1, 2, 3]})]
    fake.answer_text = compare_answer((1, ["what_it_does"]), (2, ["short_line"]))
    page = served(chromium, client)
    page.goto(SEARCH + "&ai=1")
    page.wait_for_function("!document.querySelector('.compare.waiting')")
    results = page.locator("li.result")
    assert "Same 1." in results.nth(0).inner_text() and "Differs 1." in results.nth(0).inner_text()
    assert "Same 2." in results.nth(1).inner_text()
    assert "No comparison was written for this project." in results.nth(2).inner_text()
    page.context.close()


@pytest.mark.browser
def test_a_failed_comparison_says_so_and_the_results_stay(site, chromium) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    fake.answer_queue = [json.dumps({"closest": [1, 2, 3]})]
    page = served(chromium, client, lambda: setattr(fake, "fail_with", (503, "unavailable")))
    page.goto(SEARCH + "&ai=1")
    page.wait_for_function("!document.querySelector('.compare.waiting')")
    texts = page.locator(".compare").all_inner_texts()
    assert len(texts) == 3 and all("could not be written just now" in text for text in texts)
    assert page.locator("li.result .result-link").count() == 3  # the results stay
    page.context.close()


@pytest.mark.browser
def test_quick_results_come_while_typing_and_ask_no_model(site, chromium) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto("http://site.test/")
    before = len(fake.requests)
    page.locator("#idea").fill(VENDOR)
    page.wait_for_function("new URL(location.href).searchParams.get('idea')")
    page.wait_for_selector("#results-title:has-text('Quick results')")
    assert page.locator("li.result").count() == 3 and model_calls(fake, before) == 0
    assert page.locator("#ai-button").is_enabled()
    page.context.close()


@pytest.mark.browser
def test_a_project_opens_in_a_window_over_the_list_and_back_closes_it(site, chromium) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto(SEARCH)
    page.locator(".result-link", has_text="Cedar Post").click()
    page.wait_for_selector(f"#viewer[open] .project[data-project='{ids['Cedar Post']}']")
    assert f"open={ids['Cedar Post']}" in page.url
    assert page.evaluate("document.activeElement.id") == "viewer-title"
    assert page.locator("li.result").count() == 3  # the list is still under the window
    page.go_back()
    page.wait_for_function("!document.getElementById('viewer').open")
    assert "open=" not in page.url and "idea=" in page.url
    page.locator(".result-link").first.click()
    page.wait_for_selector("#viewer[open] #viewer-title")
    page.locator("[data-viewer-step='1']").click()  # the next project of the list
    second = page.locator("li.result").nth(1).get_attribute("data-project")
    page.wait_for_selector(f"#viewer .project[data-project='{second}']")
    page.keyboard.press("Escape")
    page.wait_for_function("!document.getElementById('viewer').open")
    assert "open=" not in page.url
    page.context.close()


@pytest.mark.browser
def test_on_a_phone_the_window_covers_the_screen(site, chromium) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 390, "height": 844}, is_mobile=True,
                  has_touch=True)  # fmt: skip
    page.goto(SEARCH)
    page.locator(".result-link").first.click()
    page.wait_for_selector("#viewer[open] #viewer-title")
    box = page.locator("#viewer").bounding_box()
    assert box and box["width"] >= 389 and box["height"] >= 800
    page.context.close()


@pytest.mark.browser
def test_an_info_mark_explains_its_term(site, chromium) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto("http://site.test/")
    page.locator(".hm-filter .info[data-tip='tip-proof']").hover()
    page.wait_for_selector("#tip-proof:popover-open")
    assert "Hedera IDs" in page.locator("#tip-proof").inner_text()
    page.keyboard.press("Escape")
    page.wait_for_selector("#tip-proof:not(:popover-open)", state="attached")
    phone = served(chromium, client, viewport={"width": 390, "height": 844}, is_mobile=True,
                   has_touch=True)  # fmt: skip
    phone.goto("http://site.test/")
    phone.locator(".hm-filter .info[data-tip='tip-life']").tap()
    phone.wait_for_selector("#tip-life:popover-open")
    box = phone.locator("#tip-life").bounding_box()
    assert box and box["y"] + box["height"] > 700  # a card at the bottom, where the thumb is
    page.context.close()
    phone.context.close()


@pytest.mark.browser
def test_the_last_search_comes_back_until_it_is_cleared(site, chromium) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto(SEARCH)
    page.goto("http://site.test/")
    page.wait_for_function("new URL(location.href).searchParams.get('idea')")
    assert page.locator("#idea").input_value() == VENDOR
    page.locator("[data-clear-search]").click()
    page.wait_for_function("!new URL(location.href).searchParams.get('idea')")
    page.goto("http://site.test/")
    assert "idea=" not in page.url
    page.context.close()


AXE = Path(__file__).parent / "assets" / "axe.min.js"
WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


def problems(page) -> list[str]:  # noqa: ANN001
    """What axe-core finds against WCAG 2.2 A and AA, and the rule of one main heading: each
    rule with the first element that breaks it."""
    page.add_script_tag(path=str(AXE))
    found = page.evaluate(
        "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}}))"
        ".violations.map(v => v.id + ': ' + v.nodes[0].target.join(' '))",
        [*WCAG, "best-practice"],
    )
    return sorted(found)


@pytest.mark.browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 390])
def test_axe_finds_no_problem(site, chromium, monkeypatch, width, scheme) -> None:  # noqa: ANN001
    """axe-core finds about half of the problems of access, so a person still checks the rest
    (design 12.3); what it finds must never come back."""
    del monkeypatch
    client, fake, _, database = site
    event = checkable(database)
    fake.answer_queue = [json.dumps({"closest": [1, 2, 3]})]
    fake.answer_text = compare_answer((1, ["what_it_does"]), (2, ["short_line"]), (3, ["name"]))
    page = served(chromium, client, viewport={"width": width, "height": 900},
                  color_scheme=scheme, is_mobile=width < 900, has_touch=width < 900,
                  reduced_motion="reduce")  # fmt: skip
    page.goto("http://site.test/")
    page.wait_for_timeout(1600)  # the first screen of the visit has gone
    assert problems(page) == []
    page.goto(SEARCH + "&ai=1")
    page.wait_for_function("!document.querySelector('.compare.waiting')")
    assert problems(page) == []
    page.locator(".result-link").first.click()
    page.wait_for_selector("#viewer[open] #viewer-title")
    assert problems(page) == []
    page.keyboard.press("Escape")
    page.wait_for_function("!document.getElementById('viewer').open")
    page.locator("[data-sheet='how']").click()
    page.wait_for_selector("#sheet[open] #sheet-title")
    assert problems(page) == []
    page.goto("http://site.test/?view=charts")
    assert problems(page) == []
    page.goto("http://site.test/")  # the check of a submission, in its window
    page.fill("#check-repo", "github.com/sample-org/pebble-pay")
    page.select_option("#check-event", event)
    page.locator("#check button[type=submit]").click()
    page.wait_for_selector("#viewer[open] .check-result #viewer-title")
    assert problems(page) == []
    page.locator("#register-form button[type=submit]").click()  # the register, with its receipt
    page.wait_for_selector("#register-box .hm-receipt")
    assert problems(page) == []
    page.context.close()
