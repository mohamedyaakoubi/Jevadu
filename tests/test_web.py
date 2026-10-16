"""The website: the search, the card beside it and the method page, on three invented projects,
with Google faked."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import pytest

from fakes import project_page
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
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
    settings = Settings(_env_file=None, database_url=database, data_dir=str(tmp_path / "data"))
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
    return TestClient(create_app(settings, google=client, llm=client)), fake, ids, database


# ----------------------------------------------------------------- the start page and the list


def test_the_start_page_lists_the_projects_and_calls_no_model(site) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    before = len(fake.requests)  # the embeddings of the three projects were made already
    page = client.get("/")
    assert page.status_code == 200
    assert '<textarea id="idea"' in page.text and "Search past projects" in page.text
    assert "All 3 projects" in page.text and page.text.count('class="result"') == 3
    assert f'hx-get="/project/{ids["Pebble Pay"]}/panel"' in page.text
    assert "The card of a project opens here" in page.text
    assert len(fake.requests) == before


def test_a_page_after_the_end_of_the_list_says_so(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/", params={"page": "2"})
    assert 'class="result"' not in page.text
    assert "There are no more projects in this list." in page.text


# ----------------------------------------------------------------- the search


def test_a_search_shows_the_closest_projects_with_their_marks(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get("/", params={"idea": VENDOR})
    assert page.status_code == 200
    first = page.text.index('class="result"')
    assert f'hx-get="/project/{ids["Pebble Pay"]}/panel?idea=' in page.text[first : first + 600]
    # The model's sentence, with its label, and the words of the idea marked in it.
    assert "A <mark>vendor</mark> takes <mark>coins</mark>." in page.text
    assert "written by a model, stated" in page.text
    assert "from the project's page" in page.text  # the others have no card yet
    assert "Hedera proof:" in page.text and "What the marks mean" in page.text
    assert "projects closest to your idea" in page.text and "found in" in page.text
    assert "A fast model put the closest first" in page.text  # the words follow the way
    words = client.get("/", params={"idea": VENDOR, "mode": "words"})
    assert "The first uses the rarest of your words the most." in words.text


def test_the_words_of_the_idea_are_marked_and_a_page_never_runs_as_code(site) -> None:  # noqa: ANN001
    client, _, ids, database = site
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET short_line = %s WHERE id = %s",
                     ("<b>A ballot</b> paid with a coin", ids["Fern Vote"]))  # fmt: skip
    page = client.get("/", params={"idea": "a coin for a ballot"})
    assert "<b>A ballot</b>" not in page.text
    assert "&lt;b&gt;A <mark>ballot</mark>&lt;/b&gt;" in page.text
    assert "<mark>coin</mark>" in page.text


def test_each_mode_of_search_can_be_chosen(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    for mode in ("ai", "both", "meaning", "words"):
        page = client.get("/", params={"idea": VENDOR, "mode": mode})
        assert f'value="{mode}" checked' in page.text
    before = len(fake.requests)
    words = client.get("/", params={"idea": "parcel", "mode": "words"})
    assert len(fake.requests) == before  # by words only, the idea is not embedded
    assert "Where your words stand in its page:" in words.text
    odd = client.get("/", params={"idea": VENDOR, "mode": "magic"})
    assert 'value="ai" checked' in odd.text  # an unknown mode is the default


def order_of(page_text: str) -> list[str]:
    """The ids of the results of a page, in their order."""
    import re

    return re.findall(r'<li class="result" id="result-(\d+)"', page_text)


def test_the_default_way_shows_the_order_of_the_model(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    by_meaning = order_of(client.get("/", params={"idea": VENDOR, "mode": "meaning"}).text)
    fake.answer_queue = [json.dumps({"closest": [2, 99]})]  # 99 is not in the list
    page = client.get("/", params={"idea": VENDOR})
    assert order_of(page.text) == [by_meaning[1], by_meaning[0], *by_meaning[2:]]
    assert "did not answer in time" not in page.text
    sent = [body for path, body in fake.requests if "generateContent" in path][-1]
    assert "Pebble Pay" in json.dumps(sent)  # the model read the lines of the projects


def test_a_wrong_answer_of_the_model_keeps_the_order_of_meaning_and_says_so(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    by_meaning = order_of(client.get("/", params={"idea": VENDOR, "mode": "meaning"}).text)
    fake.answer_text = "{}"  # not a list of numbers
    page = client.get("/", params={"idea": VENDOR})
    assert order_of(page.text) == by_meaning
    assert "did not answer in time, so they are in the order of meaning only" in page.text


def test_a_card_opens_beside_the_list_and_has_its_own_address(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    pebble = ids["Pebble Pay"]
    page = client.get("/", params={"idea": VENDOR, "open": str(pebble)})
    assert f'id="card-title-{pebble}"' in page.text
    assert f'id="result-{pebble}" aria-current="true"' in page.text
    part = client.get(f"/project/{pebble}/panel", params={"idea": VENDOR})
    assert part.status_code == 200 and "<html" not in part.text
    assert f'id="card-title-{pebble}"' in part.text and "Back to the results" in part.text
    missing = client.get("/project/999999/panel")
    assert missing.status_code == 404 and "There is no project with this number" in missing.text


def test_the_card_keeps_the_three_sources_apart(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get(f"/project/{ids['Pebble Pay']}")
    assert page.status_code == 200
    text = page.text
    places = [text.index(words) for words in
              ("From the code and the ledger", "From the project's page",
               "Written by a model")]  # fmt: skip
    assert places == sorted(places)  # the facts first, then the page, then the model
    assert "Pebble Pay, invented." in text  # the short line, word for word
    assert "Inferred: less sure" in text and ">Stated<" in text
    assert f"&ldquo;{ON_PEBBLE}&rdquo;" in text  # the quote that the field rests on
    assert "Not shown: none of the sentences that the model gave was found" in text
    assert "Neither the page nor the code names a Hedera ID" in text
    assert "as the page stood on 10 October 2026" in text  # the day it was saved from its site


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
    assert 'name="event"' not in start.text


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


def test_the_method_page_explains_the_search_and_its_tests(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/method")
    assert page.status_code == 200
    assert "The search, step by step" in page.text and "The ways to search" in page.text
    assert "What the marks mean" in page.text and "What this tool cannot do" in page.text


# ----------------------------------------------------------------- the comparison (design 8.3)


def compare_answer(*parts: tuple[int, list[str]]) -> str:
    return json.dumps({"projects": [
        {"number": number, "same": f"Same {number}.", "differs": f"Differs {number}.",
         "fields_used": used}
        for number, used in parts
    ]})  # fmt: skip


def test_the_search_page_waits_for_the_comparison_without_blocking(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    before = len(fake.requests)
    page = client.get("/", params={"idea": VENDOR, "mode": "both"})
    assert 'hx-get="/compare?idea=help%20a%20street%20vendor' in page.text
    assert page.text.count('class="compare waiting"') == 3
    assert "This usually takes less than 10 seconds." in page.text
    assert not [path for path, _ in fake.requests[before:] if "generateContent" in path]
    page = client.get("/", params={"idea": VENDOR})  # the default way: the model orders the list
    calls = [path for path, _ in fake.requests[before:] if "generateContent" in path]
    assert len(calls) == 1 and page.text.count('class="compare waiting"') == 3


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
    assert "Written by a model from what it does." in part.text  # "made_up" was dropped
    assert "Written by a model from the short line." in part.text
    assert part.text.count("No comparison was written for this project.") == 1  # the third
    sent = [body for path, body in fake.requests if "generateContent" in path][-1]
    assert "A vendor takes coins." in json.dumps(sent)  # Pebble's card field went to the model


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
    assert "Only 1 of the 3 projects have a category" in page.text


def test_a_filtered_search_shows_only_the_matching_projects(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get("/", params={"idea": VENDOR, "category": PAYMENTS})
    assert page.text.count('class="result"') == 1
    assert f"/project/{ids['Pebble Pay']}/panel?idea=" in page.text
    assert "category=Payments+and+remittance" in page.text  # the link keeps the filter
    assert "Only the projects that match the filters were searched." in page.text
    card = client.get(f"/project/{ids['Pebble Pay']}", params={"idea": "a coin",
                                                               "category": PAYMENTS})  # fmt: skip
    assert 'href="/?idea=a+coin&amp;category=Payments+and+remittance#results"' in card.text


def test_a_filter_without_an_idea_narrows_the_list(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/", params={"category": PAYMENTS})
    assert "1 project matches the filters" in page.text and page.text.count('class="result"') == 1


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


# ------------------------------------------------- the findings of review layer 1 (design 12.3)


def test_a_date_is_written_as_the_pages_write_it() -> None:
    from hackathon_memory.web.app import day, iso_day

    assert day(date(2025, 7, 6)) == "6 July 2025"
    assert day(datetime(2026, 10, 10, 19, 0, tzinfo=UTC)) == "10 October 2026"
    assert iso_day("2026-10-14") == "14 October 2026" and iso_day("not a day") == "not a day"


def test_an_idea_with_no_known_word_says_that_only_the_meaning_was_compared(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/", params={"idea": "zzqx wvvq qqzx", "mode": "both"})
    assert "No word of your idea was found in the projects searched" in page.text
    words = client.get("/", params={"idea": VENDOR, "mode": "both"})
    assert "No word of your idea was found" not in words.text


def test_every_page_has_a_tab_icon_and_a_way_to_the_results(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/", params={"idea": "a coin for a vendor"})
    assert '<link rel="icon" href="/static/icon.svg"' in page.text
    assert client.get("/static/icon.svg").status_code == 200
    assert 'action="/#results"' in page.text and 'id="results"' in page.text
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
        got = client.get(parts.path + (f"?{parts.query}" if parts.query else ""))
        route.fulfill(status=got.status_code, body=got.content,
                      headers={"content-type": got.headers["content-type"]})  # fmt: skip

    page.route(lambda url: url.startswith("http://site.test/"), answer)
    return page


@pytest.mark.browser
def test_each_comparison_takes_its_place(site, chromium) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    fake.answer_text = compare_answer((1, ["what_it_does"]), (2, ["short_line"]))
    page = served(chromium, client)
    page.goto(SEARCH)
    page.wait_for_function("!document.querySelector('.compare.waiting')")
    results = page.locator("li.result")
    assert "Same 1." in results.nth(0).inner_text() and "Differs 1." in results.nth(0).inner_text()
    assert "Same 2." in results.nth(1).inner_text()
    assert "No comparison was written for this project." in results.nth(2).inner_text()
    page.context.close()


@pytest.mark.browser
def test_a_failed_comparison_says_so_and_the_results_stay(site, chromium) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    page = served(chromium, client, lambda: setattr(fake, "fail_with", (503, "unavailable")))
    page.goto(SEARCH)
    page.wait_for_function("!document.querySelector('.compare.waiting')")
    texts = page.locator(".compare").all_inner_texts()
    assert len(texts) == 3 and all("could not be written just now" in text for text in texts)
    assert page.locator("li.result .result-link").count() == 3  # the results stay
    page.context.close()


@pytest.mark.browser
def test_a_card_opens_in_the_panel_without_leaving_the_page(site, chromium) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto(SEARCH)
    page.locator(".result-link", has_text="Cedar Post").click()
    page.wait_for_selector(f"#card-title-{ids['Cedar Post']}")
    assert f"open={ids['Cedar Post']}" in page.url
    assert page.locator(f"#result-{ids['Cedar Post']}").get_attribute("aria-current") == "true"
    assert page.evaluate("document.activeElement.id") == f"card-title-{ids['Cedar Post']}"
    assert page.locator("li.result").count() == 3  # the list is still there
    page.context.close()


@pytest.mark.browser
def test_on_a_phone_the_results_come_first_and_the_card_covers_the_list(site, chromium) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = served(chromium, client, viewport={"width": 390, "height": 844}, is_mobile=True)
    page.goto("http://site.test/")
    assert page.locator("#filters").get_attribute("open") is None  # folded on a phone
    page.locator("#idea").fill(VENDOR)
    page.get_by_role("button", name="Search past projects").click()
    page.wait_for_function(
        "document.activeElement && document.activeElement.id === 'results-title'"
    )
    assert "idea=" in page.url
    assert page.evaluate("window.scrollY") > 0  # the results, not the box, are on the screen
    page.locator(".result-link").first.click()
    page.wait_for_selector("#panel.open .card-title")
    assert page.evaluate("document.querySelector('#results').inert") is True
    page.get_by_role("button", name="Back to the results").click()
    page.wait_for_function("!document.querySelector('#panel.open')")
    assert "open=" not in page.url and page.locator("li.result").count() == 3
    page.context.close()


AXE = Path(__file__).parent / "assets" / "axe.min.js"
WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


def problems(page) -> list[str]:  # noqa: ANN001
    """What axe-core finds against WCAG 2.2 A and AA, and the rule of one main heading."""
    page.add_script_tag(path=str(AXE))
    found = page.evaluate(
        "async (tags) => (await axe.run(document, {runOnly: {type: 'tag', values: tags}}))"
        ".violations.map(v => v.id)",
        [*WCAG, "best-practice"],
    )
    return sorted(found)


@pytest.mark.browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 390])
def test_the_pages_have_no_problem_that_axe_finds(site, chromium, width, scheme) -> None:  # noqa: ANN001
    """axe-core finds about half of the problems of access, so a person still checks the rest
    (design 12.3); what it finds must never come back."""
    client, fake, _, _ = site
    fake.answer_text = compare_answer((1, ["what_it_does"]), (2, ["short_line"]), (3, ["name"]))
    page = served(chromium, client, viewport={"width": width, "height": 900},
                  color_scheme=scheme, is_mobile=width < 900)  # fmt: skip
    page.goto("http://site.test/")
    assert problems(page) == []
    page.goto(SEARCH + "&mode=meaning")
    page.wait_for_function("!document.querySelector('.compare.waiting')")
    assert problems(page) == []
    page.locator(".result-link").first.click()
    page.wait_for_selector("#panel .card-title")
    assert problems(page) == []
    page.goto("http://site.test/method")
    assert problems(page) == []
    page.context.close()
