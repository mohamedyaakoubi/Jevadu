"""The website (design 12.1, fourth version): the search, the window of a project, the check of
a submission, the windows of the bottom of the page and the charts, on invented projects, with
Google, GitHub and the mirror node faked."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import psycopg
import pytest

from checkfakes import REGISTER, REPO, TOPIC, RegisterWrites, found_code, nodes
from fakes import ARCHIVE_COMMIT, project_page
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.finops.budget import Budget
from hackathon_memory.finops.calls import MemoryStore
from hackathon_memory.finops.meter import Meter, MeteredClient, Tags
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.settings import Settings
from openfake import FakeOpenModels, open_client
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
WORDS_IN_BRACKETS = r'<span class="hm-keep">\((.*?)\)</span>'  # a bracket stays with its word


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

    stand_in = FakeOpenModels()  # the stand-in of the search model (search/stand_in.py)

    def make(app_options: dict | None = None, **changes: object) -> TestClient:
        changed = settings.model_copy(update=changes)
        options = dict(app_options or {})
        google_client = options.pop("google", client)  # another stand-in Google, if one is given
        return TestClient(
            create_app(changed, google=google_client, llm=client, github_client=asker,
                       mirrors=mirrors, register_writer=writes,
                       stand_in_client=open_client(stand_in), refresh_inline=True, **options)
        )  # fmt: skip

    served = make()
    served.stand_in = stand_in  # what the stand-in of the search model was asked
    served.github_site = github_site  # what the stand-in GitHub was asked
    served.writes = writes  # what was written to the stand-in register
    served.make = make  # the same site with other settings
    served.mirrors = mirrors  # the stand-in mirror nodes, to add an account that signs
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


def test_every_page_names_its_maker_with_his_profiles(site) -> None:  # noqa: ANN001
    """The footer of every page: the maker's name leads to his portfolio, then his profiles, each
    in a new tab (30 October 2026, from his portfolio's contact page and its page data)."""
    client, _, _, _ = site
    profiles = ("https://www.linkedin.com/in/yaakoubi-mohamed/", "https://github.com/mohamedyaakoubi",
                "https://x.com/Mohamed0Yakoubi", "https://medium.com/@amirrak8",
                "https://www.instagram.com/mohamed__yaakoubi/")  # fmt: skip
    for address in ("/", "/about/how", "/check?repo=github.com/sample-org/pebble-pay"):
        footer = client.get(address).text.split('<footer class="hm-footer">', 1)[1]
        assert ('<a href="https://www.mohamedyaakoubi.com" target="_blank" rel="noopener">'
                "Mohamed Yaakoubi</a>") in footer  # fmt: skip
        for profile in profiles:
            assert f'<a href="{profile}" target="_blank" rel="noopener">' in footer


def test_the_start_page_lists_the_projects_and_calls_no_model(site) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    before = len(fake.requests)  # the embeddings of the three projects were made already
    page = client.get("/")
    assert page.status_code == 200
    assert 'id="idea" name="idea"' in page.text and "Sort and compare with Gemini" in page.text
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
    assert "No more projects in this list." in page.text


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
    page = client.get("/", params={"idea": VENDOR, "mode": "meaning"})
    assert page.status_code == 200
    assert model_calls(fake, before) == 0  # only the embedding of the idea
    assert 'id="results-title">Results</h2>' in page.text and "closest by meaning" in page.text
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
    for old in ("both", "magic", ""):  # a way of an older page, or none: the default
        page = client.get("/", params={"idea": VENDOR, "mode": old})
        assert 'id="mode-words" checked' in page.text  # keyword (28 October 2026)
    page = client.get("/", params={"idea": VENDOR, "ai": "1"})  # an address of before
    assert 'id="mode-meaning" checked' in page.text  # Gemini orders the semantic results
    before = len(fake.requests)
    words = client.get("/", params={"idea": "parcel", "mode": "words"})
    assert len(fake.requests) == before  # by words only, the idea is not embedded
    assert "Matching text:" in words.text
    assert "closest by keyword" in words.text


def test_the_button_of_gemini_works_with_the_keyword_search_chosen(site) -> None:  # noqa: ANN001
    """The button orders the semantic results, whichever search the form is on. With Keyword
    chosen it sent mode=words, and the keyword results came back with no word about it (7
    November 2026)."""
    client, fake, _, _ = site
    fake.answer_queue = [json.dumps({"closest": [2, 1]})]
    before = len(fake.requests)
    page = client.get("/", params={"idea": VENDOR, "mode": "words", "ai": "1"})
    assert model_calls(fake, before) == 1
    assert "Sorted by Gemini" in page.text and 'data-mode="meaning"' in page.text
    assert 'id="mode-meaning" checked' in page.text


def test_the_button_orders_with_gemini_and_the_same_search_asks_nothing_again(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    by_meaning = order_of(client.get("/", params={"idea": VENDOR, "mode": "meaning"}).text)
    fake.answer_queue = [json.dumps({"closest": [2, 99]})]  # 99 is not in the list
    before = len(fake.requests)
    page = client.get("/", params={"idea": VENDOR, "ai": "1"})
    assert model_calls(fake, before) == 1
    assert order_of(page.text) == [by_meaning[1], by_meaning[0], *by_meaning[2:]]
    assert "Sorted by Gemini" in page.text and "Search order</a>" in page.text
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
    by_meaning = order_of(client.get("/", params={"idea": VENDOR, "mode": "meaning"}).text)
    fake.answer_text = "{}"  # not a list of numbers
    page = client.get("/", params={"idea": VENDOR, "ai": "1"})
    assert order_of(page.text) == by_meaning
    # "did not respond in time" was said for every failure before 24 October 2026
    assert "Gemini failed to give an order just now, so the results are in the search order" in (
        page.text)  # fmt: skip
    assert "after 4 more failures in a row, DeepSeek V4.1 Flash takes its place" in page.text
    assert 'id="compare-loader"' not in page.text


def test_after_five_failures_of_gemini_its_stand_in_orders_and_compares(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    by_meaning = order_of(client.get("/", params={"idea": VENDOR, "mode": "meaning"}).text)
    fake.fail_writing = (503, "unavailable")  # Gemini fails; the embeddings still answer
    client.stand_in.content = json.dumps({"closest": [2]})
    for left in ("4 more failures", "3 more failures", "2 more failures", "1 more failure"):
        page = client.get("/", params={"idea": VENDOR, "ai": "1"})
        assert order_of(page.text) == by_meaning and f"after {left} in a row" in page.text
    assert client.stand_in.sent == []
    page = client.get("/", params={"idea": VENDOR, "ai": "1"})  # the fifth failure in a row
    assert "Sorted by DeepSeek V4.1 Flash" in page.text
    assert "Gemini failed 5 times in a row, so DeepSeek V4.1 Flash put these results" in page.text
    assert "DeepSeek V4.1 Flash is reading the 30 closest projects" in page.text  # while it waits
    assert order_of(page.text) == [by_meaning[1], by_meaning[0], *by_meaning[2:]]
    asked = client.stand_in.body()
    assert asked["model"] == "deepseek-ai/deepseek-v4.1-flash-maas"
    assert asked["chat_template_kwargs"] == {"thinking": False}  # its measured level, "off"
    gemini = model_calls(fake)
    client.stand_in.content = compare_answer((1, ["short_line"]))
    first = order_of(page.text)[0]
    part = client.get("/compare", params={"idea": VENDOR, "ids": first, "mode": "meaning"})
    assert part.status_code == 200 and "By DeepSeek V4.1 Flash, from" in part.text
    assert model_calls(fake) == gemini  # while the stand-in has its turn, Gemini is not asked


def test_a_project_opens_in_the_window_with_its_own_address(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    pebble = ids["Pebble Pay"]
    page = client.get("/", params={"idea": VENDOR, "open": str(pebble)})
    assert 'id="viewer-title"' in page.text and f'data-project="{pebble}"' in page.text
    part = client.get(f"/project/{pebble}/panel", params={"idea": VENDOR})
    assert part.status_code == 200 and "<html" not in part.text
    assert 'id="viewer-title"' in part.text and "Compare with my idea" in part.text
    missing = client.get("/project/999999/panel")
    assert missing.status_code == 404 and "There is no project with this ID" in missing.text


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
    assert f'hx-get="/project/{cedar}/panel"' in box and "Same repository." in box
    assert f"/project/{fern}" not in box
    page = client.get(f"/project/{cedar}")  # the page of its own names the link too
    assert "Linked projects" in page.text and f'hx-get="/project/{pebble}/panel"' in page.text
    shared = client.get("/", params={"open": str(cedar)})  # opened from a link that was shared
    assert "Linked projects" in shared.text and f'hx-get="/project/{pebble}/panel"' in shared.text


def test_the_card_of_a_team_that_came_back_shows_its_timeline(site, tmp_path: Path) -> None:  # noqa: ANN001
    """The same repository at two events (design 8.7, 31 October 2026): the card shows both, the
    oldest first, says that the code is not compared until GitHub's answers are saved, then how
    it changed, and that the dates of commits are the team's own. The box of linked projects does
    not name them again."""
    from checkfakes import COMMIT, LATER_COMMIT, commits_answer, compare_answer
    from hackathon_memory.collect.answers import Answers
    from hackathon_memory.collect.github_commits import kept_of
    from hackathon_memory.collect.github_history import compare_address, kept_change, until_address
    from hackathon_memory.db.repositories import RepositoryStore

    client, _, ids, database = site
    pebble, cedar = ids["Pebble Pay"], ids["Cedar Post"]
    with psycopg.connect(database) as conn:
        (later,) = conn.execute(
            "INSERT INTO events (site, slug, name, ends_on) "
            "VALUES ('ethglobal.com', 'later', 'Later', '2026-06-14') RETURNING id"
        ).fetchone()
        conn.execute("UPDATE projects SET event_id = %s WHERE id = %s", (later, cedar))
        conn.execute("UPDATE events SET ends_on = '2026-03-08' WHERE slug = 'sample-event'")
    RepositoryStore(database).link({pebble: REPO, cedar: REPO})

    def timeline(text: str) -> str:
        return text.split("Timeline: one repository, 2 hackathons", 1)[1].split("</section>", 1)[0]

    part = client.get(f"/project/{pebble}/panel").text
    box = timeline(part)
    assert box.index("8 March 2026") < box.index("14 June 2026")  # the oldest event first
    assert "(this card)" in box and f'hx-get="/project/{cedar}/panel"' in box
    assert "The code between the two is not compared yet: the next reading asks GitHub." in box
    assert box.count("Its code at the end of the event: not read yet.") == 2
    assert "Same repository." not in box  # one repository: the title says it once
    assert "The dates of commits are the team's own" in box
    assert "Linked projects" not in part  # its only link is in the timeline already
    answers = Answers(tmp_path / "data" / "raw" / "api.github.com")  # where the step saves them
    for url, body, keep in (
        (until_address(REPO, date(2026, 3, 8)), commits_answer(), kept_of),
        (until_address(REPO, date(2026, 6, 14)), commits_answer(LATER_COMMIT), kept_of),
        (compare_address(REPO, COMMIT, LATER_COMMIT), compare_answer(), kept_change),
    ):
        fetch = FetchResult(url, url, 200, body, "application/json", "2026-10-31T08:00:00Z")
        kept, facts, taken_out = keep(fetch)
        answers.save(fetch, kept, received=body, collector="TestTool/0.1.0", team_cut=taken_out,
                     answer=facts, suffix=".json")  # fmt: skip
    box = timeline(client.get(f"/project/{cedar}").text)  # the page of its own shows it too
    assert "Between the two: 4 commits, 3 files changed, 60 lines added and 3 removed." in box
    assert f'href="{REPO}/compare/{COMMIT}...{LATER_COMMIT}"' in box
    assert f'href="{REPO}/commit/{COMMIT}"' in box and f">{COMMIT[:7]}<span" in box
    assert "not compared yet" not in box and "not read yet" not in box
    page = client.get("/", params={"open": str(cedar)}).text  # its (i) opens its one note
    assert 'popovertarget="tip-timeline"' in page and page.count('id="tip-timeline" popover') == 1


def test_projects_linked_by_a_hedera_id_show_a_timeline_whatever_they_won(site) -> None:  # noqa: ANN001
    """Two projects at two events, with two repositories and the same topic, and no prize
    (design 8.7): the timeline shows both, says how they are linked, and that their code is not
    compared."""
    from hackathon_memory.db.repositories import RepositoryStore

    client, _, ids, database = site
    pebble, cedar = ids["Pebble Pay"], ids["Cedar Post"]
    with psycopg.connect(database) as conn:
        (later,) = conn.execute(
            "INSERT INTO events (site, slug, name, ends_on) "
            "VALUES ('ethglobal.com', 'later', 'Later', '2026-06-14') RETURNING id"
        ).fetchone()
        conn.execute("UPDATE projects SET event_id = %s WHERE id = %s", (later, cedar))
        conn.execute("UPDATE events SET ends_on = '2026-03-08' WHERE slug = 'sample-event'")
        for pid in (pebble, cedar):
            (hid,) = conn.execute(
                "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
                "words_around, in_hashscan_link) VALUES (%s, '0.0.7000123', 'testnet', 'topic', "
                "'page', 'invented', false) RETURNING id", (pid,)).fetchone()  # fmt: skip
            conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                         "VALUES (%s, 'testnet', 'proof_found')", (hid,))  # fmt: skip
        (prizes,) = conn.execute("SELECT count(*) FROM prizes WHERE project_id = ANY(%s)",
                                 ([pebble, cedar],)).fetchone()  # fmt: skip
    assert prizes == 0  # neither won anything
    RepositoryStore(database).link({pebble: REPO, cedar: "https://github.com/sample-org/cedar"})
    part = client.get(f"/project/{cedar}/panel").text
    box = part.split("Timeline: 2 hackathons", 1)[1].split("</section>", 1)[0]
    assert "Same Hedera ID: 0.0.7000123 on testnet, confirmed by the ledger for both." in box
    assert "Different repositories, so the code is not compared." in box
    assert box.count("Its code at the end of the event: not read yet.") == 2
    assert "Linked projects" not in part  # its only link is in the timeline already


def test_projects_that_share_only_an_account_show_no_timeline(site) -> None:  # noqa: ANN001
    """Two projects at two events, with two repositories and the same testnet account (design
    8.4, 1 November 2026): an account is the builder's, so there is no timeline, and the linked
    projects say that the account is the same, not that the project is."""
    from datetime import UTC, datetime

    from hackathon_memory.check.ledger import LedgerFacts
    from hackathon_memory.db.ledger import LedgerStore
    from hackathon_memory.db.repositories import RepositoryStore

    client, _, ids, database = site
    pebble, cedar = ids["Pebble Pay"], ids["Cedar Post"]
    with psycopg.connect(database) as conn:
        (later,) = conn.execute(
            "INSERT INTO events (site, slug, name, ends_on) "
            "VALUES ('ethglobal.com', 'later', 'Later', '2026-06-14') RETURNING id"
        ).fetchone()
        conn.execute("UPDATE projects SET event_id = %s WHERE id = %s", (later, cedar))
        conn.execute("UPDATE events SET ends_on = '2026-03-08' WHERE slug = 'sample-event'")
        for pid in (pebble, cedar):
            (hid,) = conn.execute(
                "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
                "words_around, in_hashscan_link) VALUES (%s, '0.0.4729347', 'testnet', 'account', "
                "'page', 'invented', false) RETURNING id", (pid,)).fetchone()  # fmt: skip
            conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                         "VALUES (%s, 'testnet', 'proof_found')", (hid,))  # fmt: skip
    asked = datetime(2026, 10, 31, tzinfo=UTC)
    LedgerStore(database).save_facts(LedgerFacts("0.0.4729347", "testnet", asked, found=True,
                                                 kind="account"))  # fmt: skip
    RepositoryStore(database).link({pebble: REPO, cedar: "https://github.com/sample-org/cedar"})
    part = client.get(f"/project/{cedar}/panel").text
    assert "Timeline: 2 hackathons" not in part
    links = part.split("Linked projects", 1)[1].split("</section>", 1)[0]
    assert (
        "Same Hedera account: 0.0.4729347 on testnet, confirmed by the ledger for both. "
        "The same account, not necessarily the same project."
    ) in links


def test_a_filter_keeps_several_values_at_once(site) -> None:  # noqa: ANN001
    """Two events ticked in the event filter keep the projects of both, and one keeps its own
    (design 8.2, 1 November 2026); the boxes say which values are ticked, and the links of the
    page keep both values in one parameter."""
    client, _, ids, database = site
    pebble, cedar = ids["Pebble Pay"], ids["Cedar Post"]
    with psycopg.connect(database) as conn:
        (first,) = conn.execute("SELECT event_id FROM projects WHERE id = %s",
                                (pebble,)).fetchone()  # fmt: skip
        (later,) = conn.execute(
            "INSERT INTO events (site, slug, name, ends_on) "
            "VALUES ('ethglobal.com', 'later', 'Later', '2026-06-14') RETURNING id"
        ).fetchone()
        conn.execute("UPDATE projects SET event_id = %s WHERE id = %s", (later, cedar))
    one = client.get("/", params={"event": str(later)}).text
    assert "1 project matches the filters" in one
    assert f"/project/{cedar}/panel" in one and f"/project/{pebble}/panel" not in one
    both = client.get(f"/?event={first}&event={later}").text
    assert "3 projects match the filters" in both
    assert f"/project/{cedar}/panel" in both and f"/project/{pebble}/panel" in both
    for event in (first, later):
        assert f'name="event" value="{event}" checked' in both
    assert "event=" + "%7C".join(sorted([str(first), str(later)])) in both


def test_the_card_says_what_the_code_shows_about_hedera(site) -> None:  # noqa: ANN001
    """What the code says about Hedera (design 7.3): a line for each kind of thing found, each
    thing with its files, linked at the commit that was read; code that was not read says so."""
    from hackathon_memory.collect.github_code import CodeRead
    from hackathon_memory.collect.github_facts import RepositoryFacts
    from hackathon_memory.db.repositories import RepositoryStore
    from hackathon_memory.parse.hedera_code import MIRROR_NODE, CodeScan, Seen

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    store = RepositoryStore(database)
    store.link({pebble: REPO})
    store.save_facts(REPO, RepositoryFacts("found", datetime(2026, 3, 6, tzinfo=UTC), None,
                                           False, False, "TypeScript", REPO, "c" * 64,
                                           "2026-10-21T20:00:00Z"))  # fmt: skip
    unread = client.get(f"/project/{pebble}/panel").text
    assert "Hedera in the code" in unread and "has not been read for Hedera yet" in unread
    scan = CodeScan(files=40, commit=ARCHIVE_COMMIT,
                    packages={"@hashgraph/sdk": ["package.json"]},
                    features={"Consensus Service (topics)": Seen(12, [f"src/t{n}.ts"
                                                                     for n in range(10)])},
                    signs={MIRROR_NODE: Seen(1, ["src/mirror ledger.ts"])})  # fmt: skip
    store.save_code(REPO, CodeRead("read", scan, "2026-10-21T20:00:00Z"))
    part = client.get(f"/project/{pebble}/panel").text
    block = part.split("Hedera in the code", 1)[1].split("</section>", 1)[0]
    assert "Read 21 October 2026 at commit" in block and "40 files of the project" in block
    assert "Hedera packages" in block and "@hashgraph/sdk &middot; 1 file<" in block
    assert "Consensus Service (topics) &middot; 12 files" in block and "and 2 more" in block
    assert f'href="{REPO}/blob/{ARCHIVE_COMMIT}/src/mirror%20ledger.ts"' in block
    assert "Files that import a Hedera library" not in block  # nothing of that kind
    store.save_code(REPO, CodeRead("read", CodeScan(files=3, commit=ARCHIVE_COMMIT),
                                   "2026-10-21T20:00:00Z"))  # fmt: skip
    nothing = client.get(f"/project/{pebble}/panel").text
    assert "No Hedera package, import, service call, sign or mention in this code." in nothing


def own_id(database: str, project_id: int, entity: str, kind: str) -> None:
    """An invented ID that one project names, found by the ledger as the kind that its page
    says, with the status "proof found" on the test network."""
    from hackathon_memory.check.ledger import LedgerFacts
    from hackathon_memory.db.ledger import LedgerStore

    LedgerStore(database).save_facts(LedgerFacts(
        entity, "testnet", datetime(2026, 10, 22, tzinfo=UTC), found=True, kind=kind,
        ledger_id=entity, created_at=datetime(2026, 3, 6, 18, tzinfo=UTC),
    ))  # fmt: skip
    with psycopg.connect(database) as conn:
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, %s, 'testnet', %s, 'page', 'invented', "
            "true) RETURNING id", (project_id, entity, kind)).fetchone()  # fmt: skip
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                     "VALUES (%s, 'testnet', 'proof_found')", (hedera_id,))  # fmt: skip


def test_the_card_says_how_its_proof_and_its_activity_were_judged(site) -> None:  # noqa: ANN001
    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    plain = client.get(f"/project/{pebble}/panel").text
    # The box "How this was judged" went into "On the ledger" and the code (24 October 2026).
    assert "How this was judged" not in plain and "Neither the page nor the README names" in plain
    with psycopg.connect(database) as conn:  # the invented event: 6 to 8 March 2026
        conn.execute("UPDATE events SET starts_at = '2026-03-06T00:00:00Z', ends_on = '2026-03-08'")
    own_id(database, pebble, "0.0.4870201", "topic")  # made on 6 March 2026
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET proof_status = 'proof_found' WHERE id = %s", (pebble,))
    panel = client.get(f"/project/{pebble}/panel").text
    ledger = panel[panel.index(f'id="ledger-{pebble}"') :]
    ledger = ledger[: ledger.index("</section>")]
    assert "The window of ETHGlobal Sample Event: 4 February 2026 to 22 March 2026" in ledger
    assert "<b>Proof found: made inside the window</b>" in ledger  # the ID that decides it
    assert f'href="#ledger-{pebble}" data-scroll-to="ledger-{pebble}"' in panel
    assert f'href="#life-{pebble}" data-scroll-to="life-{pebble}"' in panel
    life = panel[panel.index(f'id="life-{pebble}"') :]
    assert "ETHGlobal Sample Event ended on 8 March 2026, so a sign of life is a push" in life
    # each sign says when it was read (design 7.4, 25 October 2026)
    read = "Last activity of its own IDs: none, read from the mirror node on 22 October 2026."
    assert read in life
    listed = client.get("/").text
    card = listed[listed.index(f'id="result-{pebble}"') :]
    card = card[: card.index("</li>")]
    assert f'data-scroll-to="ledger-{pebble}"' in card  # the mark opens the card there
    assert f'data-scroll-to="life-{pebble}"' in card
    assert f'hx-get="/project/{pebble}/panel"' in card


def test_an_id_of_the_code_shows_its_file_and_says_where_the_proof_comes_from(site) -> None:  # noqa: ANN001
    from hackathon_memory.db.code_ids import CodeIdStore, Given

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    own_id(database, pebble, "0.0.4870201", "account")
    with psycopg.connect(database) as conn:  # the page's ID becomes one that only the code names
        conn.execute("DELETE FROM hedera_ids WHERE project_id = %s", (pebble,))
        conn.execute("UPDATE projects SET proof_status = 'proof_found' WHERE id = %s", (pebble,))
    CodeIdStore(database).replace(pebble, [Given("0.0.4870201", "testnet", "config/ids.ts")])
    with psycopg.connect(database) as conn:
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) SELECT id, 'testnet', "
                     "'proof_found' FROM hedera_ids WHERE project_id = %s", (pebble,))  # fmt: skip
    panel = client.get(f"/project/{pebble}/panel").text
    assert "Proof: found in the code" in panel
    assert "in the code, config/ids.ts: no page or README names it" in panel
    listed = client.get("/").text
    card = listed[listed.index(f'id="result-{pebble}"') :]
    assert "Proof: found in the code" in card[: card.index("</li>")]


def linked(network: str, kind: str, entity: str, shown: str = "") -> str:
    """An ID as the site links it to its page on HashScan (3 November 2026), shown as `shown`."""
    return (f'<a class="id" href="https://hashscan.io/{network}/{kind}/{entity}" rel="noopener" '
            f'target="_blank">{shown or entity}<span class="visually-hidden"> on HashScan (opens '
            "in a new tab)</span></a>")  # fmt: skip


def stamp(moment: datetime, number: int) -> str:
    """A moment of consensus as the mirror node writes it: seconds.nanoseconds."""
    return f"{int(moment.timestamp())}.{number:09d}"


def test_the_card_tells_the_ledger_story_of_its_own_ids(site) -> None:  # noqa: ANN001
    """The ledger story (design 7.5): the services of the page, the code and the ledger side by
    side, the facts that stand out, the time before and after, and what was read and when. A
    project with no own ID of a fitting kind shows none of it."""
    from hackathon_memory.check.history import CONSENSUS, CONTRACTS, HBAR, History
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    title = "Hedera services: page, code and ledger"
    plain = client.get(f"/project/{pebble}/panel").text
    assert title not in plain and "hm-said" not in plain  # no story: the page's texts stay plain
    own_id(database, pebble, "0.0.4511", "topic")
    own_id(database, pebble, "0.0.4512", "account")
    with psycopg.connect(database) as conn:  # the event: 6 to 8 March 2026
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
        line = "Each sale is a message on HCS, paid in a Hedera token."
        conn.execute("UPDATE projects SET short_line = %s WHERE id = %s", (line, pebble))
    waiting = client.get(f"/project/{pebble}/panel").text
    assert "The history of its own Hedera IDs has not been read yet." in waiting
    sale, later = datetime(2026, 3, 7, 12, tzinfo=UTC), datetime(2026, 6, 1, 9, tzinfo=UTC)
    asked = datetime(2026, 10, 23, 2, tzinfo=UTC)
    store = HistoryStore(database)
    messages = {stamp(sale, 1): CONSENSUS, stamp(later, 2): CONSENSUS}
    store.save("0.0.4511", "testnet", "topic", History(messages, False), asked)
    calls = {stamp(sale, 10 + n): CONTRACTS for n in range(3)}
    store.save("0.0.4512", "testnet", "account",
               History({**calls, stamp(later, 20): HBAR}, False), asked)  # fmt: skip
    part = client.get(f"/project/{pebble}/panel").text
    block = part.split(title, 1)[1].split("</section>", 1)[0]
    assert "from 4 February 2026 to 7 April 2026, the event and 30 days on each side" in block
    rows = re.findall(r"<tr>\s*<th scope=\"row\">([^<]+)</th>(.*?)</tr>", block, re.DOTALL)
    assert [name for name, _ in rows] == ["Consensus Service (topics)", "Token Service",
                                          "Smart contracts"]  # fmt: skip
    assert "&ldquo;HCS&rdquo;" in rows[0][1] and ">1</button>" in rows[0][1]  # opens its note
    assert "&ldquo;Hedera token&rdquo;" in rows[1][1] and ">0</td>" in rows[1][1]
    assert "Its code was not read, so the table leaves it out." in block
    named = re.search(r"<li>The page names the Token Service " + WORDS_IN_BRACKETS + r", and its "
                      r"IDs show no Token Service transactions in that time\.</li>", block,
                      re.DOTALL)  # fmt: skip
    assert named and 'data-said-word="hedera token"' in named.group(1)
    assert 'data-said-word="hcs"' in rows[0][1]  # each word of the page is a button
    tagline = part.split("<h4>Tagline</h4>", 1)[1].split("</p>", 1)[0]
    assert '<mark class="hm-said" data-said="consensus" data-word="hcs">HCS</mark>' in tagline
    assert ("Its IDs show 3 smart contract transactions in that time, and the page does not name "
            "smart contracts.") in block  # fmt: skip
    assert re.search(r"<dt>Before \d+ \w+ \d{4}</dt><dd>none</dd>", block)  # by its date
    # after that time: the topic's message counts, and the account's transfer does not
    # its history kept no payer, so the line says that who paid is not known (29 October 2026)
    assert ("<dd>1 Consensus Service transaction, the last on 1 June 2026; who paid is not "
            "known</dd>") in block  # fmt: skip
    assert "Read from the mirror node on 23 October 2026: 2 of its own IDs." in block


def test_the_hbar_row_says_not_checked_and_its_mark_says_why(site) -> None:  # noqa: ANN001
    """The page is not checked for HBAR, since nearly every project moves HBAR to set itself up;
    its cell says so with a mark of its own (30 October 2026: "not compared" alone was unclear).
    Every mark of the page and of its window has its text on the page."""
    from hackathon_memory.check.history import HBAR, History
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    own_id(database, pebble, "0.0.4512", "account")
    with psycopg.connect(database) as conn:  # the event: 6 to 8 March 2026
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
    paid = datetime(2026, 3, 7, 12, tzinfo=UTC)
    HistoryStore(database).save("0.0.4512", "testnet", "account",
                                History({stamp(paid, n): HBAR for n in range(2)}, False),
                                datetime(2026, 10, 23, 2, tzinfo=UTC))  # fmt: skip
    page = client.get("/", params={"open": pebble}).text
    row = re.search(r'<th scope="row">Accounts and HBAR transfers</th>(.*?)</tr>', page, re.DOTALL)
    assert row and '<span class="text-secondary">not checked</span>' in row.group(1)
    assert 'popovertarget="tip-hbar"' in row.group(1) and ">2</button>" in row.group(1)
    # the old words of the HBAR cell are gone from its table (the timeline's note uses them)
    table = page[page.rindex("<table", 0, row.start()) : page.index("</table>", row.end())]
    assert "not compared" not in table
    tip = page.split('id="tip-hbar" popover>', 1)[1].split("</div>", 1)[0]
    assert "Nearly every project moves HBAR" in tip and "not checked" in tip
    marks = set(re.findall(r'popovertarget="tip-([a-z0-9-]+)"', page))
    assert "hbar" in marks and "story" in marks
    for key in marks:
        assert page.count(f'id="tip-{key}" popover') == 1, key


def test_the_card_shows_the_depth_of_use_and_the_days_of_its_own_ids(site) -> None:  # noqa: ANN001
    """Depth of use (design 7.5, 25 October 2026): what its IDs did, who took part, on how many
    days, the page's own words about Hedera, and a strip of days whose squares open HashScan."""
    from hackathon_memory.check.history import CONSENSUS, Act, History
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    own_id(database, pebble, "0.0.4511", "topic")
    with psycopg.connect(database) as conn:  # the event: 6 to 8 March 2026
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
        conn.execute("UPDATE projects SET short_line = %s WHERE id = %s",
                     ("Each sale is a message on HCS.", pebble))  # fmt: skip
    sale = datetime(2026, 3, 7, 12, tzinfo=UTC)
    messages = {stamp(sale, n): CONSENSUS for n in (1, 2, 3)}
    payers = ("0.0.7001", "0.0.8001", "0.0.8001")
    acts = {key: Act("CONSENSUSSUBMITMESSAGE", True, payer, (payer,))
            for key, payer in zip(sorted(messages), payers, strict=True)}  # fmt: skip
    HistoryStore(database).save("0.0.4511", "testnet", "topic", History(messages, False, acts),
                                datetime(2026, 10, 23, 2, tzinfo=UTC))  # fmt: skip
    part = client.get(f"/project/{pebble}/panel").text
    block = part.split(f'id="depth-{pebble}"', 1)[1].split("</section>", 1)[0]
    assert "3 messages to a topic." in block
    # who the other accounts can be, in plain words (29 October 2026)
    assert ("2 accounts that the page does not list: outside users, or other accounts of the "
            "team.") in block  # fmt: skip
    # the numbers say their dates, since the strip can draw more days (28 October 2026)
    assert "<dt>What its IDs did from 4 February 2026 to 7 April 2026</dt>" in block
    assert ("1 day with a transaction from 4 February 2026 to 7 April 2026: 1 during the event, 0 "
            "in the 30 days before it, 0 in the 30 days after it.") in block  # fmt: skip
    # one card (28 October 2026): the depth of use inside the card of the Hedera services, the
    # page's words marked once in its table, and the time before and after said once
    story = part.split('class="card project-section story-section"', 1)[1].split("</section>", 1)[0]
    assert f'id="depth-{pebble}"' in story and "depth-section" not in part
    assert "<q>" not in block and story.count("<dt>Before ") == 1
    first = sorted(messages)[0]
    assert f'href="https://hashscan.io/testnet/transaction/{first}"' in block
    assert 'data-note="7 March 2026: 3 Consensus Service transactions"' in block
    assert "<summary>The days as a table</summary>" in block
    # the days widen, with two small buttons, the narrower one off at first (28 October 2026)
    assert 'aria-label="Widen the days"' in block and 'data-zoom="in"' in block
    assert 'data-zoom="out" aria-label="Narrow the days" title="Narrow the days" disabled' in block
    assert "Ctrl and the mouse wheel, or the buttons + and −, widen the days." in block


def test_the_strip_cuts_out_a_long_time_without_a_transaction(site) -> None:  # noqa: ANN001
    """The strip draws the messages of its topic a year before the event too, and cuts out the
    time between them, a hatched band with its length (design 7.5, 28 October 2026). Before, it
    stopped 30 days before the event."""
    from hackathon_memory.check.history import CONSENSUS, Act, History
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    own_id(database, pebble, "0.0.4511", "topic")
    with psycopg.connect(database) as conn:  # the event: 6 to 8 March 2026
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
    early, during = stamp(datetime(2025, 3, 7, 12, tzinfo=UTC), 1), stamp(
        datetime(2026, 3, 7, 12, tzinfo=UTC), 2)  # fmt: skip
    messages = {early: CONSENSUS, during: CONSENSUS}
    # a stranger paid for the early message: an account that the page does not name
    acts = {early: Act("CONSENSUSSUBMITMESSAGE", True, "0.0.8001", ("0.0.8001",))}
    HistoryStore(database).save("0.0.4511", "testnet", "topic", History(messages, False, acts),
                                datetime(2026, 10, 23, 2, tzinfo=UTC))  # fmt: skip
    part = client.get(f"/project/{pebble}/panel").text
    block = part.split(f'id="depth-{pebble}"', 1)[1].split("</section>", 1)[0]
    assert 'data-note="7 March 2025: 1 Consensus Service transaction"' in block
    assert '<rect class="hm-strip-cut" ' in block and f'fill="url(#strip-{pebble}-cut)"' in block
    assert ("<title>No transaction for 11 months, from 8 March 2025 to 3 February 2026: left out "
            "of the strip.</title>") in block  # fmt: skip
    assert 'class="hm-strip-mark hm-strip-cut-mark"' in block and ">11 mo</text>" in block
    # who paid for the transactions before the time of the table (29 October 2026)
    assert ("1 Consensus Service transaction, the first on 7 March 2025; paid by 1 account that "
            "the page does not list") in block  # fmt: skip
    assert ("A hatched band is a time of more than 30 days with no transaction, left out of the "
            "strip; its length stands under it.") in block  # fmt: skip


def test_a_reading_that_the_limit_stopped_says_what_is_not_known(site) -> None:  # noqa: ANN001
    """A topic whose reading the limit of 2,000 transactions stopped a year before the event, as
    for a public contract that thousands call: the card says what was not read, and no longer
    "none" after the event or "no transaction" in the band (29 October 2026)."""
    from hackathon_memory.check.history import CONSENSUS, Act, History
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    own_id(database, pebble, "0.0.4511", "topic")
    with psycopg.connect(database) as conn:  # the event: 6 to 8 March 2026
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
    messages = {stamp(datetime(2025, 3, 7, 12, tzinfo=UTC), 1): CONSENSUS,
                stamp(datetime(2025, 3, 9, 12, tzinfo=UTC), 2): CONSENSUS}  # fmt: skip
    acts = {key: Act("CONSENSUSSUBMITMESSAGE", True, "0.0.8001", ("0.0.8001",)) for key in messages}
    HistoryStore(database).save("0.0.4511", "testnet", "topic", History(messages, True, acts),
                                datetime(2026, 10, 23, 2, tzinfo=UTC))  # fmt: skip
    part = client.get(f"/project/{pebble}/panel").text
    story = part.split('class="card project-section story-section"', 1)[1].split("</section>", 1)[0]
    said = "Jevadu read only the first 2,000 transactions of its topic 0.0.4511, up to 9 March 2025"
    assert (f'<p class="hm-story-cut">{said}. Its later transactions are missing from this card, '
            "so its numbers are at least these.</p>") in story  # fmt: skip
    # the lines after the note say it short, without the ID again
    stopped = "the reading of its topic stopped at its limit of 2,000 transactions, on 9 March 2025"
    assert ("<dd>at least 2 Consensus Service transactions, the first on 7 March 2025; paid by at "
            f"least 1 account that the page does not list; {stopped}</dd>") in story  # fmt: skip
    assert f"<dd>not known: {stopped}</dd>" in story and "<dd>none</dd>" not in story
    assert (f"<title>Not read: {said}. The time from 10 March 2025 to 3 February 2026 (11 months) "
            "is left out of the strip.</title>") in story  # fmt: skip
    assert ("A band after 9 March 2025 was not read: the reading of its topic stopped there, at "
            "its limit of 2,000 transactions.") in story  # fmt: skip


def test_the_card_says_who_made_its_own_ids(site) -> None:  # noqa: ANN001
    """Who made each own thing, from the step "makers" (design 7.5, 29 October 2026): OmniShield's
    README gave a contract made 20 months before its event by someone else."""
    from hackathon_memory.check.history import CONSENSUS, Act, History
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    own_id(database, pebble, "0.0.4511", "topic")  # made on 6 March 2026
    with psycopg.connect(database) as conn:  # the event: 6 to 8 March 2026
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
        conn.execute("UPDATE ledger_facts SET made_by = '0.0.8001', made_by_asked_at = %s "
                     "WHERE entity_id = '0.0.4511'",
                     (datetime(2026, 10, 29, tzinfo=UTC),))  # fmt: skip
    message = stamp(datetime(2026, 3, 7, 12, tzinfo=UTC), 1)
    acts = {message: Act("CONSENSUSSUBMITMESSAGE", True, "0.0.8001", ("0.0.8001",))}
    HistoryStore(database).save("0.0.4511", "testnet", "topic",
                                History({message: CONSENSUS}, False, acts),
                                datetime(2026, 10, 23, 2, tzinfo=UTC))  # fmt: skip
    part = client.get(f"/project/{pebble}/panel").text
    block = part.split(f'id="depth-{pebble}"', 1)[1].split("</section>", 1)[0]
    topic, maker = linked("testnet", "topic", "0.0.4511"), linked("testnet", "account", "0.0.8001")
    assert (f"<dt>Who made its IDs</dt>\n    <dd><span class=\"d-block\">Its topic {topic}, on 6 "
            f"March 2026: made by {maker}, an account that the project does not "
            "list.</span></dd>") in block  # fmt: skip


def test_a_public_service_that_the_page_names_is_said_and_not_owned(site) -> None:  # noqa: ANN001
    """The price oracle of Pyth, given by a page as one of its contracts: the card says what it
    is, with its owner's list, and draws none of its transactions (migration 0022)."""
    from hackathon_memory.check.ledger import LedgerFacts
    from hackathon_memory.db.ledger import LedgerStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    pyth = "0xa2aa501b19aff244d90cc15a4cf739d2725b5729"
    LedgerStore(database).save_facts(LedgerFacts(
        pyth, "testnet", datetime(2026, 10, 29, tzinfo=UTC), found=True, kind="contract",
        ledger_id="0.0.3042133", created_at=datetime(2024, 2, 9, tzinfo=UTC),
    ))  # fmt: skip
    with psycopg.connect(database) as conn:
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, %s, 'testnet', 'contract', 'page', "
            "'invented', true) RETURNING id", (pebble, pyth)).fetchone()  # fmt: skip
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                     "VALUES (%s, 'testnet', 'proof_found')", (hedera_id,))  # fmt: skip
    part = client.get(f"/project/{pebble}/panel").text
    named = linked("testnet", "contract", "0.0.3042133", shown=pyth)  # its page on HashScan
    assert (f"It also names {named}, the price oracle of Pyth: a public "
            "service that many projects use, so its transactions are not counted as the "
            "project's here.") in part  # fmt: skip
    assert 'href="https://github.com/pyth-network/pyth-crosschain/' in part


def test_the_card_says_how_its_own_ids_are_set_up(site) -> None:  # noqa: ANN001
    """The kind, the custom fees and the keys of its own token, from the check of the IDs, with
    the day of that check (design 7.5, 28 October 2026)."""
    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    own_id(database, pebble, "0.0.4515", "token")
    setup = {"type": "NON_FUNGIBLE_UNIQUE", "supply_type": "INFINITE", "keys": ["admin", "supply"],
             "fees": {"royalty": [[1, 20]]}}  # fmt: skip
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE ledger_facts SET details = %s WHERE entity_id = '0.0.4515'",
                     (json.dumps(setup),))  # fmt: skip
    part = client.get(f"/project/{pebble}/panel").text
    block = part.split(f'id="depth-{pebble}"', 1)[1].split("</section>", 1)[0]
    assert '<p class="hm-depth-title">How they are set up, read on 22 October 2026</p>' in block
    token = linked("testnet", "token", "0.0.4515")
    assert (f"Its token {token}: an NFT collection with no supply limit; a royalty of 5% on each "
            "sale; keys for admin and supply.") in block  # fmt: skip


def test_the_card_counts_the_calls_of_its_contracts_for_the_service_they_reached(site) -> None:  # noqa: ANN001
    """The calls of its own contract that reached the Token Service count in its row, and the
    other system contracts and the limit are said under the table (design 7.5, 28 October
    2026)."""
    from hackathon_memory.check.history import CONTRACTS, Act, History
    from hackathon_memory.check.story import time_of
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble, escrow = ids["Pebble Pay"], "0.0.4516"
    own_id(database, pebble, escrow, "contract")
    with psycopg.connect(database) as conn:  # the event: 6 to 8 March 2026
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
        (starts_at,) = conn.execute("SELECT starts_at FROM events").fetchone()
        span = time_of(starts_at, date(2026, 3, 8))
        conn.execute("INSERT INTO contract_calls (entity_id, network, starts_at, ends_at, read, "
                     "cut, reached, asked_at) VALUES (%s, 'testnet', %s, %s, 100, true, %s, %s)",
                     (escrow, *span, json.dumps({"0.0.359": 34, "0.0.361": 2}),
                      datetime(2026, 10, 28, tzinfo=UTC)))  # fmt: skip
    call = stamp(datetime(2026, 3, 7, 12, tzinfo=UTC), 1)
    HistoryStore(database).save(escrow, "testnet", "contract",
                                History({call: CONTRACTS}, False,
                                        {call: Act("CONTRACTCALL", True, "0.0.7001", ())}),
                                datetime(2026, 10, 23, 2, tzinfo=UTC))  # fmt: skip
    part = client.get(f"/project/{pebble}/panel").text
    story = part.split('class="card project-section story-section"', 1)[1].split("</table>", 2)
    table, after = story[0], story[1]
    assert '<span class="hm-from-contracts">+ 34 from its contracts</span>' in table
    assert ("Its contracts also reached random numbers in 2 calls in that time. Of a contract "
            "with more calls in that time, the first 100 were read.") in after  # fmt: skip


def test_a_number_of_the_table_opens_what_it_holds(site) -> None:  # noqa: ANN001
    """The Consensus Service counts the transaction that made the topic beside its messages, so
    its number is one more than the messages to a topic; the number opens a note that says what
    it holds, and the parts add up to it (3 November 2026)."""
    from hackathon_memory.check.history import CONSENSUS, Act, History
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble, team = ids["Pebble Pay"], "0.0.4512"
    a_card_with_days(database, pebble)  # an own topic with two messages on 7 March 2026
    own_id(database, pebble, team, "account")
    made = stamp(datetime(2026, 3, 6, 12, tzinfo=UTC), 3)
    HistoryStore(database).save(team, "testnet", "account",
                                History({made: CONSENSUS}, False,
                                        {made: Act("CONSENSUSCREATETOPIC", True, team, (team,))}),
                                datetime(2026, 10, 23, 2, tzinfo=UTC))  # fmt: skip
    part = client.get(f"/project/{pebble}/panel").text
    table = part.split('class="card project-section story-section"', 1)[1].split("</table>", 1)[0]
    note = f"held-{pebble}-consensus"
    assert (f'<button type="button" class="hm-count" popovertarget="{note}" data-tip="{note}" '
            f'aria-describedby="{note}">3</button>') in table  # fmt: skip
    assert (f'<div class="tip hm-held" id="{note}" popover role="tooltip" data-stay>2 messages '
            "to a topic and 1 topic made.</div>") in table  # fmt: skip
    depth = part.split(f'id="depth-{pebble}"', 1)[1].split("</section>", 1)[0]
    assert "2 messages to a topic, 1 topic made" in depth


def test_a_team_that_put_an_own_id_on_the_main_network_has_the_tag_mainnet(site) -> None:  # noqa: ANN001
    """An own ID that the page names on the main network, known there as that kind and made in
    the time of the event or later; not an ID named with no network, nor one made years before
    (design 7.5, 28 October 2026)."""
    from hackathon_memory.check.ledger import LedgerFacts
    from hackathon_memory.db.ledger import LedgerStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]

    def named(network: str | None, made: datetime) -> str:
        LedgerStore(database).save_facts(LedgerFacts(
            "0.0.4517", "mainnet", datetime(2026, 10, 28, tzinfo=UTC), found=True, kind="topic",
            ledger_id="0.0.4517", created_at=made))  # fmt: skip
        with psycopg.connect(database) as conn:
            conn.execute("DELETE FROM hedera_ids WHERE entity_id = '0.0.4517'")
            (hedera_id,) = conn.execute(
                "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
                "words_around, in_hashscan_link) VALUES (%s, '0.0.4517', %s, 'topic', 'page', "
                "'invented', false) RETURNING id", (pebble, network)).fetchone()  # fmt: skip
            conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                         "VALUES (%s, 'mainnet', 'proof_found')", (hedera_id,))  # fmt: skip
        return client.get(f"/project/{pebble}/panel").text

    during = datetime(2026, 3, 7, tzinfo=UTC)  # the event: from 6 March 2026
    # on the card, the tag opens the project's path on the main network (design 7.6)
    card = named("mainnet", during)
    assert f'class="hm-tag-open" href="/project/{pebble}/mainnet"' in card
    assert '<span class="badge bg-green-lt">Mainnet<span aria-hidden="true">' in card
    found = client.get("/", params={"idea": "help a street vendor get paid with a coin"}).text
    assert '<span class="badge bg-green-lt">Mainnet</span>' in found  # and on the result
    assert "Mainnet" not in named(None, during)  # named with no network
    assert "Mainnet" not in named("mainnet", datetime(2021, 9, 20, tzinfo=UTC))  # long before


def test_the_mainnet_filter_keeps_the_teams_on_the_main_network(site) -> None:  # noqa: ANN001
    """The tag "Mainnet" as a filter, yes or no (31 October 2026): each choice counts its projects
    and keeps only those."""
    from hackathon_memory.check.ledger import LedgerFacts
    from hackathon_memory.db.ledger import LedgerStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    LedgerStore(database).save_facts(LedgerFacts(
        "0.0.4517", "mainnet", datetime(2026, 10, 28, tzinfo=UTC), found=True, kind="topic",
        ledger_id="0.0.4517", created_at=datetime(2026, 3, 7, tzinfo=UTC)))  # fmt: skip
    with psycopg.connect(database) as conn:
        conn.execute("DELETE FROM hedera_ids WHERE entity_id = '0.0.4517'")
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, '0.0.4517', 'mainnet', 'topic', 'page', "
            "'invented', false) RETURNING id", (pebble,)).fetchone()  # fmt: skip
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                     "VALUES (%s, 'mainnet', 'proof_found')", (hedera_id,))  # fmt: skip
    page = client.get("/").text
    assert 'name="mainnet"' in page and ">Yes (1)</span>" in page and ">No (2)</span>" in page
    kept = client.get("/", params={"mainnet": "yes"}).text
    assert "1 project matches the filters" in kept and f"/project/{pebble}/panel" in kept
    # the other filters count what this one keeps; its own numbers stay whole (1 November 2026)
    assert "ETHGlobal Sample Event (1)" in kept
    assert ">Yes (1)</span>" in kept and ">No (2)</span>" in kept
    assert "Each number says how many projects that value shows with your other filters." in kept
    left = client.get("/", params={"mainnet": "no"}).text
    assert "2 projects match the filters" in left and f"/project/{pebble}/panel" not in left


MAINNET_ASKED = datetime(2026, 11, 1, tzinfo=UTC)


def put_on_mainnet(database: str, project_id: int) -> tuple[str, str]:
    """The topic 0.0.4517 of a project, named on the main network and made on 7 March 2026, with
    two messages in its history (7 March and 7 April 2026), the cost of the first one read.
    Returns the two moments."""
    from hackathon_memory.check.history import CONSENSUS, History
    from hackathon_memory.check.ledger import LedgerFacts
    from hackathon_memory.check.mainnet import Detail, Rate
    from hackathon_memory.db.history import HistoryStore
    from hackathon_memory.db.ledger import LedgerStore
    from hackathon_memory.db.mainnet import MainnetStore

    LedgerStore(database).save_facts(LedgerFacts(
        "0.0.4517", "mainnet", MAINNET_ASKED, found=True, kind="topic", ledger_id="0.0.4517",
        created_at=datetime(2026, 3, 7, tzinfo=UTC)))  # fmt: skip
    with psycopg.connect(database) as conn:
        conn.execute("DELETE FROM hedera_ids WHERE entity_id = '0.0.4517'")
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, '0.0.4517', 'mainnet', 'topic', 'page', "
            "'invented', false) RETURNING id", (project_id,)).fetchone()  # fmt: skip
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                     "VALUES (%s, 'mainnet', 'proof_found')", (hedera_id,))  # fmt: skip
    one = f"{int(datetime(2026, 3, 7, 10, tzinfo=UTC).timestamp())}.000000001"
    two = f"{int(datetime(2026, 4, 7, 10, tzinfo=UTC).timestamp())}.000000002"
    history = History({one: CONSENSUS, two: CONSENSUS}, False)
    HistoryStore(database).save("0.0.4517", "mainnet", "topic", history, MAINNET_ASKED)
    MainnetStore(database).save(
        Detail(one, "CONSENSUSSUBMITMESSAGE", True, 59_829_520, 0, ("0.0.7001",), 0),
        Rate(637_060, 30_000), MAINNET_ASKED,
    )  # fmt: skip
    return one, two


def test_the_view_mainnet_counts_what_the_own_ids_did_on_the_main_network(site) -> None:  # noqa: ANN001
    """The fourth view (design 12.1, S10, 1 November 2026): how many projects of the list put an
    own ID on the main network, its transactions, their fees in HBAR and in dollars at the rate of
    the network, and a table of the projects; a transaction whose cost is not read yet is said."""
    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    put_on_mainnet(database, pebble)
    assert ">Mainnet</a>" in client.get("/").text  # the switch beside the other views
    page = client.get("/", params={"view": "mainnet"}).text
    assert "1 of 3 projects put its own ID on Hedera's main network" in page
    assert ("Their own IDs made 2 transactions there, on 2 days, from 7 March 2026 to 7 April "
            "2026.") in page  # fmt: skip
    # 0.598 HBAR at 637,060 cents for 30,000 HBAR: 12.7 cents
    assert "The network charged 0.60 HBAR in fees for them: $0.13 at the exchange rate" in page
    assert "The cost of 1 transaction is not read yet." in page
    assert "No HBAR changed hands in them besides the fees." in page
    assert "1 account paid for them." in page
    assert "The last day of its event is not known." in page
    assert f'data-open-viewer="{pebble}"' in page
    assert 'href="https://hashscan.io/mainnet/topic/0.0.4517"' in page
    assert 'aria-current="true">Mainnet</a>' in page
    # a filter that leaves no project on the main network
    other = client.get("/", params={"view": "mainnet", "mainnet": "no"}).text
    assert "0 of 2 projects put their own ID on Hedera's main network" in other
    assert "No project of this list put an own ID on the main network." in other


def test_the_path_on_the_main_network_opens_from_the_view_and_from_the_card(site) -> None:  # noqa: ANN001
    """The window of a project's path on the main network (design 7.6, 1 November 2026): opened
    from a row of the view Mainnet and from the tag "Mainnet" of a card, in the window over the
    page; a page of its own without htmx; none for a project that put nothing there."""
    from hackathon_memory.check.mainnet_what import Thing
    from hackathon_memory.db.mainnet import MainnetStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    one, _ = put_on_mainnet(database, pebble)
    store = MainnetStore(database)
    store.explain(one, "paid", ("eip155:8453",), MAINNET_ASKED)
    store.save_thing(Thing("0.0.4517", "topic", datetime(2026, 3, 7, tzinfo=UTC), "0.0.7001",
                           name="shop receipts", fields=("kind", "network"), messages=2),
                     MAINNET_ASKED)  # fmt: skip
    store.save_thing(Thing("0.0.4600", "token", datetime(2026, 3, 8, tzinfo=UTC), "0.0.7001",
                           name="Side Token (SIDE)", held_by_others=0), MAINNET_ASKED)  # fmt: skip
    store.mark_followed("0.0.7001", "read", MAINNET_ASKED)
    address = f"/project/{pebble}/mainnet"
    assert f'data-sheet="{address}"' in client.get("/", params={"view": "mainnet"}).text
    assert f'class="hm-tag-open" href="{address}" data-sheet="{address}"' in (
        client.get(f"/project/{pebble}/panel").text)  # fmt: skip
    window = client.get(address, headers={"HX-Request": "true"})
    assert window.status_code == 200
    text = window.text
    assert 'id="sheet-title"' in text and "Pebble Pay on Hedera's main network" in text
    maker = linked("mainnet", "account", "0.0.7001")
    assert "Made the topic" in text and f"&ldquo;shop receipts&rdquo;, by {maker}." in text
    assert 'class="hm-path-word">paid</span>' in text  # the kind that the message gives itself
    assert "Base</span>" not in text and "Base <span" in text and "(eip155:8453)" in text
    assert "No transaction of its own IDs on the main network" in text
    assert "to the reading of 1 November 2026" in text
    assert "Side Token (SIDE)" in text and "no other account holds it now" in text
    assert "<html" not in text  # a part of the page, for the window
    page = client.get(address)
    assert page.status_code == 200 and "Back to the search" in page.text  # a page of its own
    nothing = client.get(f"/project/{ids['Fern Vote']}/mainnet", headers={"HX-Request": "true"})
    assert nothing.status_code == 404
    assert "put no own ID on Hedera" in nothing.text
    assert 'id="tip-mainnet-path"' in client.get("/").text  # its (i) explains it


def test_a_moved_token_is_named_by_its_id_and_a_public_one_by_its_owner(site) -> None:  # noqa: ANN001
    """A token that a transaction moved is named by its symbol and its ID, linked to HashScan as
    every ID of the window, since a symbol is only a name that a maker chose; a token that its
    owner runs for everyone, SAUCE here, is said with its owner's page (migration 0030, 3
    November 2026). The account and the transfer are invented; SAUCE's ID is SaucerSwap's."""
    from hackathon_memory.check.history import TOKENS, History
    from hackathon_memory.check.ledger import LedgerFacts
    from hackathon_memory.check.mainnet import Detail, Rate
    from hackathon_memory.db.history import HistoryStore
    from hackathon_memory.db.ledger import LedgerStore
    from hackathon_memory.db.mainnet import MainnetStore

    client, _, ids, database = site
    pebble, account = ids["Pebble Pay"], "0.0.4518"
    LedgerStore(database).save_facts(LedgerFacts(
        account, "mainnet", MAINNET_ASKED, found=True, kind="account", ledger_id=account,
        created_at=datetime(2026, 3, 7, tzinfo=UTC)))  # fmt: skip
    with psycopg.connect(database) as conn:
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, %s, 'mainnet', 'account', 'page', "
            "'invented', false) RETURNING id", (pebble, account)).fetchone()  # fmt: skip
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                      "VALUES (%s, 'mainnet', 'proof_found')", (hedera_id,))  # fmt: skip
    moment = f"{int(datetime(2026, 3, 7, 11, tzinfo=UTC).timestamp())}.000000003"
    HistoryStore(database).save(account, "mainnet", "account", History({moment: TOKENS}, False),
                                MAINNET_ASKED)  # fmt: skip
    store = MainnetStore(database)
    store.save(Detail(moment, "CRYPTOTRANSFER", True, 100_000, 0, (account,), 1),
               Rate(637_060, 30_000), MAINNET_ASKED)  # fmt: skip
    store.explain(moment, "moved SAUCE (0.0.731861)", (), MAINNET_ASKED)
    text = client.get(f"/project/{pebble}/mainnet", headers={"HX-Request": "true"}).text
    assert f"1 transaction that moved SAUCE ({linked('mainnet', 'token', '0.0.731861')})." in text
    said = (
        "0.0.731861 is SAUCE, the token of SaucerSwap: a public service that many projects "
        'use. Source: <a href="https://docs.saucerswap.finance/tokenomics/overview"'
    )
    assert said in text
    assert "read on 3 November 2026." in text


def test_an_id_in_a_sentence_links_to_its_page_on_hashscan() -> None:
    """The IDs of a sentence of the card or of the window link to HashScan: an own ID with its
    network and kind, another with the network of the ID before it and the kind that the word
    before it names, else the kind given; an ID of no known network stays as it is, and the
    rest of the sentence is escaped (3 November 2026)."""
    from hackathon_memory.web.data import id_links, ids_in

    own = {"0.0.4511": ("testnet", "topic")}
    said = str(id_links("Its topic 0.0.4511, on 6 March: made by 0.0.8001 <b>.", own))
    assert said == (f"Its topic {linked('testnet', 'topic', '0.0.4511')}, on 6 March: made by "
                    f"{linked('testnet', 'account', '0.0.8001')} &lt;b&gt;.")  # fmt: skip
    assert str(id_links("No account holds its token 0.0.9 now.", network="mainnet")) == (
        f"No account holds its token {linked('mainnet', 'token', '0.0.9')} now.")  # fmt: skip
    assert str(id_links("moved SAUCE (0.0.731861)", network="mainnet", kind="token")) == (
        f"moved SAUCE ({linked('mainnet', 'token', '0.0.731861')})")  # fmt: skip
    assert str(id_links("made by 0.0.9", {})) == "made by 0.0.9"  # no network: no link
    found = ids_in("0.0.5 and 10.0.3, version 0.0.12a, then (0.0.731861).")
    assert found == ["0.0.5", "0.0.731861"]


def test_the_sites_own_files_are_never_run_old(site) -> None:  # noqa: ANN001
    """The script and the styles are linked with a fingerprint of their content, and a browser
    checks its copy each time (design 12.2, 28 October 2026)."""
    client, _, _, _ = site
    page = client.get("/").text
    script = re.search(r'src="(/static/site\.js\?v=[0-9a-f]{12})"', page)
    style = re.search(r'href="(/static/style\.css\?v=[0-9a-f]{12})"', page)
    assert script and style
    answer = client.get(script.group(1))
    assert answer.status_code == 200 and answer.headers["cache-control"] == "no-cache"
    again = client.get(script.group(1), headers={"If-None-Match": answer.headers["etag"]})
    assert again.status_code == 304 and again.headers["cache-control"] == "no-cache"


def test_each_tag_of_a_card_has_its_own_note(site) -> None:  # noqa: ANN001
    """An (i) explains only its tag: a winners' list entry gets the note of that tag, not the
    notes of the prizes or of the main network (design 12.2, 28 October 2026)."""
    client, _, ids, database = site
    fern = ids["Fern Vote"]
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET entry_kind = 'winner_entry', "
                     "prize_state = 'hedera_prize' WHERE id = %s", (fern,))  # fmt: skip
    head = client.get(f"/project/{fern}/panel").text.split("</header>", 1)[0]
    assert 'data-tip="tip-hedera-prize"' in head and 'data-tip="tip-winners-list"' in head
    assert 'data-tip="tip-mainnet"' not in head and 'data-tip="tip-event"' not in head
    page = client.get("/").text
    for key in ("event", "event-chart", "hedera-prize", "other-prize", "winners-list", "mainnet"):
        assert f'id="tip-{key}"' in page, key
    event = page.split('id="tip-event"', 1)[1].split("</div>", 1)[0]
    assert "prize" not in event and "Mainnet" not in event  # the note of the events only


def test_the_note_of_reading_again_says_what_the_website_does(site) -> None:  # noqa: ANN001
    """With the rounds off, the note does not say that the website reads again while it runs
    (design 12.2, 28 October 2026)."""
    client, _, _, _ = site
    note = client.get("/").text.split('id="tip-fresh"', 1)[1].split("</div>", 1)[0]
    assert "while the website runs" not in note and "when the collection is read again" in note
    assert "what the calls of its contracts reached" in note


def a_card_with_days(database: str, pebble: int) -> None:
    """Pebble Pay with an own topic and two messages on 7 March 2026, in its event of 6 to 8
    March: a card with a strip of days."""
    from hackathon_memory.check.history import CONSENSUS, Act, History
    from hackathon_memory.db.history import HistoryStore

    own_id(database, pebble, "0.0.4511", "topic")
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
    messages = {stamp(datetime(2026, 3, 7, 12, tzinfo=UTC), n): CONSENSUS for n in (1, 2)}
    acts = {key: Act("CONSENSUSSUBMITMESSAGE", True, "0.0.7001", ("0.0.7001",))
            for key in messages}  # fmt: skip
    HistoryStore(database).save("0.0.4511", "testnet", "topic", History(messages, False, acts),
                                datetime(2026, 10, 23, 2, tzinfo=UTC))  # fmt: skip


def test_the_card_counts_the_transactions_of_the_kinds_it_does_not_name(site) -> None:  # noqa: ANN001
    """A card names six kinds of transaction; the rest are counted together, by their number of
    transactions and of kinds (25 October 2026)."""
    from hackathon_memory.check.history import HBAR, Act, History
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble, team = ids["Pebble Pay"], "0.0.4512"
    own_id(database, pebble, team, "account")
    with psycopg.connect(database) as conn:  # the event: 6 to 8 March 2026
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
    named = ["CRYPTOTRANSFER", "TOKENMINT", "TOKENBURN", "TOKENASSOCIATE", "CRYPTOCREATEACCOUNT",
             "SCHEDULECREATE"]  # fmt: skip
    for others, said in ((["TOKENCREATION", "CRYPTOAPPROVEALLOWANCE"], "2 more of 2 other kinds"),
                         (["TOKENCREATION"], "1 more of another kind")):  # fmt: skip
        names = [*named, *named, *others]  # two of each named kind, one of each other
        moments = [stamp(datetime(2026, 3, 7, 12, tzinfo=UTC), n) for n in range(len(names))]
        acts = {at: Act(name, True, team, (team,)) for at, name in zip(moments, names, strict=True)}
        HistoryStore(database).save(team, "testnet", "account",
                                    History(dict.fromkeys(moments, HBAR), False, acts),
                                    datetime(2026, 10, 23, 2, tzinfo=UTC))  # fmt: skip
        part = client.get(f"/project/{pebble}/panel").text
        block = part.split(f'id="depth-{pebble}"', 1)[1].split("</section>", 1)[0]
        assert "2 transfers, " in block and f", and {said}." in block
        # its own IDs are accounts only: the time around the table is said once
        assert block.count("not counted, since its own IDs are accounts only") == 1


def test_the_card_says_who_holds_its_tokens_in_words(site) -> None:  # noqa: ANN001
    """The accounts that hold its tokens now and that it does not name: "no account" in words,
    not a 0 (28 October 2026)."""
    from hackathon_memory.check.history import TOKENS, Act, History
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble, coin, team = ids["Pebble Pay"], "0.0.4513", "0.0.4514"
    own_id(database, pebble, coin, "token")
    own_id(database, pebble, team, "account")
    with psycopg.connect(database) as conn:  # the event: 6 to 8 March 2026
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
    minted = stamp(datetime(2026, 3, 7, 12, tzinfo=UTC), 1)
    for holders, said in (((team,), "No account outside the page's list holds its tokens now."),
                          ((team, "0.0.9001"), "1 account outside the page's list holds its "
                                               "tokens now.")):  # fmt: skip
        HistoryStore(database).save(coin, "testnet", "token",
                                    History({minted: TOKENS}, False,
                                            {minted: Act("TOKENMINT", True, team, (team,))},
                                            holders),
                                    datetime(2026, 10, 23, 2, tzinfo=UTC))  # fmt: skip
        part = client.get(f"/project/{pebble}/panel").text
        block = part.split(f'id="depth-{pebble}"', 1)[1].split("</section>", 1)[0]
        assert said in block and "held now by 0" not in block


def test_the_places_of_the_page_are_marked_and_the_rest_stays_text() -> None:
    from hackathon_memory.web.data import said

    assert str(said('<b>HCS</b> & "hts"')) == (
        '&lt;b&gt;<mark class="hm-said" data-said="consensus" data-word="hcs">HCS</mark>&lt;/b&gt; '
        '&amp; &#34;<mark class="hm-said" data-said="tokens" data-word="hts">hts</mark>&#34;'
    )
    assert str(said("No service here.")) == "No service here."


def test_the_live_demo_has_a_button_at_the_head_of_the_card(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    part = client.get(f"/project/{ids['Pebble Pay']}/panel")
    head = part.text.split('class="project-cols"', 1)[0]
    assert 'href="https://demo.example.test/pebble-pay"' in head and "Live demo" in head


def test_the_card_keeps_the_three_sources_apart(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get(f"/project/{ids['Pebble Pay']}")
    assert page.status_code == 200
    text = page.text
    places = [text.index(words) for words in
              ("On the ledger<", "The code<", "From the project page<",
               "AI summary<")]  # fmt: skip
    assert places == sorted(places)  # the facts first, then the page, then the model
    assert "Pebble Pay, invented." in text  # the short line, word for word
    assert ">Inferred<" in text and ">Stated<" in text
    assert f"&ldquo;{ON_PEBBLE}&rdquo;" in text  # the quote that the field rests on
    assert "Hidden: none of its quotes were found" in text
    assert "Neither the page nor the README names a Hedera ID" in text
    assert "as of 10 October 2026" in text  # the day it was saved from its site
    assert "compare-section" not in text  # no idea on its own page, so no comparison
    # The title is a level 1 heading here, so a level 2 stands above the sections of level 3.
    hidden = '<h2 class="visually-hidden">The details of the project</h2>'
    assert hidden in text
    assert hidden not in client.get(f"/project/{ids['Pebble Pay']}/panel").text  # the title: h2


def test_a_project_without_a_model_card_says_so(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get(f"/project/{ids['Cedar Post']}")
    assert "No AI summary for this project yet" in page.text


def test_an_unknown_project_is_not_found(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/project/999999")
    assert page.status_code == 404 and "There is no project with this ID" in page.text


def test_without_google_the_words_are_searched_and_the_page_says_so(site) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    fake.fail_with = (503, "unavailable")
    page = client.get("/", params={"idea": "a vendor and a coin", "mode": "meaning"})
    assert page.status_code == 200
    assert "so these are keyword results" in page.text
    assert f"/project/{ids['Pebble Pay']}/panel?idea=" in page.text


def test_an_expired_google_sign_in_gives_the_keyword_results(site) -> None:  # noqa: ANN001
    """A sign-in to Google that expired or was revoked fails before a request leaves: the page
    falls back to the keyword results and says so (29 October 2026: it answered with an error)."""
    import google.auth.credentials
    import google.auth.exceptions
    from google import genai

    class Expired(google.auth.credentials.Credentials):
        def refresh(self, request: object) -> None:
            raise google.auth.exceptions.RefreshError("invalid_grant: the token expired")

    expired = genai.Client(enterprise=True, project="test-project", location="global",
                           credentials=Expired())  # fmt: skip
    client, _, ids, _ = site
    page = client.make({"google": expired}).get(
        "/", params={"idea": "a coin for the street vendors of the night", "mode": "meaning"}
    )
    assert page.status_code == 200
    assert "so these are keyword results" in page.text
    assert f"/project/{ids['Pebble Pay']}/panel?idea=" in page.text


def test_an_unexpected_error_is_answered_in_plain_words(site, monkeypatch) -> None:  # noqa: ANN001
    """The error itself goes to the log of the server, never to the page."""
    from fastapi.testclient import TestClient

    from hackathon_memory.web import data

    client, _, _, _ = site

    def broken(conninfo: str) -> list:
        raise RuntimeError("a secret detail of the server")

    monkeypatch.setattr(data, "dated_events", broken)
    calm = TestClient(client.app, raise_server_exceptions=False)
    page = calm.get("/", params={"idea": VENDOR})
    assert page.status_code == 500 and "Something went wrong on the server" in page.text
    assert "<h1" in page.text and "secret detail" not in page.text
    part = calm.get("/", params={"idea": VENDOR}, headers=HX)
    assert part.status_code == 500 and 'id="viewer-title"' in part.text and "<html" not in part.text


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
    cut = f"Your idea was longer than {LONGEST_IDEA:,} characters, so it was shortened."
    assert cut in page.text


# ----------------------------------------------------------------- the windows and the sources


def test_the_windows_of_the_bottom_of_the_page(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    how = client.get("/about/how", headers=HX)
    assert how.status_code == 200 and "<html" not in how.text
    assert "The search, step by step" in how.text and "Search modes compared" in how.text
    assert "Limits</h3>" in how.text and "Test 3: the Hedera IDs." in how.text
    page = client.get("/about/how")  # without JavaScript, a whole page
    assert "<html" in page.text and "Back to the search" in page.text
    assert client.get("/method").status_code == 200
    questions = client.get("/about/questions", headers=HX)
    assert "Why doesn't the AI judge, score or rank the projects?" in questions.text
    assert "ETHGlobal was asked before any program read its showcase." in questions.text
    sources = client.get("/about/sources", headers=HX)
    assert sources.text.count('<li id="ref-') >= 15
    assert client.get("/about/nothing").status_code == 404


def test_each_term_links_its_numbered_source(site) -> None:  # noqa: ANN001
    from hackathon_memory.web.references import BY_KEY, NUMBER

    client, _, _, _ = site
    page = client.get("/")
    terms = ("hedera", "mirror", "account", "topic", "token", "contract", "embedding")
    for key in (*terms, "ward", "silhouette"):  # the last two: the groups of the graph
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
    assert part.text.count("No comparison for this project.") == 1  # the third
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


def test_a_comparison_kept_for_the_idea_shows_on_its_card_in_the_list(site) -> None:  # noqa: ANN001
    """A comparison asked in a project's window shows on its card when the list comes again
    (30 October 2026: the card kept no trace of it)."""
    client, fake, ids, _ = site
    pebble = ids["Pebble Pay"]
    fake.answer_text = compare_answer((1, ["what_it_does"]))
    client.get("/compare", params={"idea": VENDOR, "ids": str(pebble), "one": "1"})
    before = len(fake.requests)
    page = client.get("/", params={"idea": VENDOR, "mode": "meaning"})  # no order of Gemini
    card = page.text.split(f'id="result-{pebble}"', 1)[1].split("</li>", 1)[0]
    assert "Same 1." in card and "By Gemini, from what it does." in card
    assert model_calls(fake, before) == 0  # kept, never asked again
    other = client.get("/", params={"idea": "a market of old books", "mode": "meaning"})
    assert "Same 1." not in other.text  # kept for its own idea only


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
    assert part.text.count("could not be generated just now") == 2


# ----------------------------------------------------------------- the filters (design 8.2)


def test_the_filters_offer_what_the_projects_have(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/")
    assert 'name="event"' in page.text and 'name="life"' in page.text
    assert "ETHGlobal Sample Event (3)" in page.text
    assert 'name="organiser"' in page.text and ">ETHGlobal (3)</span>" in page.text
    assert f"{PAYMENTS} (1)" in page.text  # the one card of the fixture
    assert "1 of 3 projects have one" in page.text


def test_a_filtered_search_shows_only_the_matching_projects(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get("/", params={"idea": VENDOR, "category": PAYMENTS})
    assert page.text.count('class="result"') == 1
    assert f"/project/{ids['Pebble Pay']}/panel?idea=" in page.text
    assert "category=Payments+and+remittance" in page.text  # the link keeps the filter
    assert "Clear filters" in page.text
    card = client.get(f"/project/{ids['Pebble Pay']}", params={"idea": "a coin",
                                                               "category": PAYMENTS})  # fmt: skip
    assert 'href="/?idea=a+coin&amp;category=Payments+and+remittance#results"' in card.text


def test_a_filter_without_an_idea_narrows_the_list(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/", params={"category": PAYMENTS})
    assert "1 project matches the filters" in page.text and page.text.count('class="result"') == 1


def test_the_prize_filter_keeps_the_winners_and_those_known_only_from_a_list(site) -> None:  # noqa: ANN001
    client, _, ids, database = site
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET prize_state = 'hedera_prize' WHERE id = ANY(%s)",
                     ([ids["Cedar Post"], ids["Fern Vote"]],))  # fmt: skip
        conn.execute("UPDATE projects SET entry_kind = 'winner_entry' WHERE id = %s",
                     (ids["Fern Vote"],))  # fmt: skip
    page = client.get("/").text
    assert 'value="hedera_prize"><span>Won a Hedera prize (2)</span>' in page
    assert 'value="winners_list"><span>Winners&#39; list only (1)</span>' in page
    assert 'value="other_prize"' not in page  # no project won another sponsor's prize here
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET prize_state = 'other_prize' WHERE id = %s",
                     (ids["Pebble Pay"],))  # fmt: skip
    fresh = client.make()  # a running site reads the facts of its filters once a minute at most
    other = fresh.get("/").text
    assert 'value="other_prize"><span>Won another sponsor&#39;s prize (1)</span>' in other
    assert order_of(fresh.get("/", params={"winner": "other_prize"}).text) == [
        str(ids["Pebble Pay"])
    ]
    won = client.get("/", params={"winner": "hedera_prize"}).text
    assert set(order_of(won)) == {str(ids["Cedar Post"]), str(ids["Fern Vote"])}
    listed = client.get("/", params={"winner": "winners_list"}).text
    assert order_of(listed) == [str(ids["Fern Vote"])]
    assert "winner=winners_list" in listed  # the address keeps the choice


def test_a_filter_keeps_the_closest_projects_that_have_its_value(site, monkeypatch) -> None:  # noqa: ANN001
    """The number next to a value is what the filter leaves (design 8.2): a filter narrows the
    closest projects of a search, it does not search again among all the projects."""
    from hackathon_memory.web import app as web_app

    client, _, _, _ = site
    monkeypatch.setattr(web_app, "SHOWN", 1)  # "the closest" is one project in this test
    vendor = client.get("/", params={"idea": VENDOR, "category": PAYMENTS})
    assert "1 to 1 of the 1 matching your filters, among the 1 closest" in vendor.text
    assert vendor.text.count('class="result"') == 1 and "Pebble Pay" in vendor.text
    ballot = client.get("/", params={"idea": "a ballot for a small club", "category": PAYMENTS})
    assert "None of the 1 closest projects match these filters" in ballot.text
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


def with_line(client, check_text: str) -> str:  # noqa: ANN001
    """The team adds the line that the box of the register asks for to its README on GitHub."""
    from checkfakes import README, readme_answer
    from fakes import Reply
    from hackathon_memory.collect.github import readme_address

    line = re.search(r"jevadu: [A-Z2-7]{8}", check_text).group(0)
    readme = readme_answer(f"{README}\n\n{line}\n")
    client.github_site.pages[readme_address(REPO)] = Reply(200, readme)
    return line


def answer_of(client, steps):  # noqa: ANN001, ANN201
    """The answer of a check that runs while its window shows its steps: waits for it, then asks
    for it as the page does."""
    job = re.search(r"/check/progress\?job=([\w-]+)", steps.text).group(1)
    client.app.state.check_jobs.get(job).done.result(30)
    return client.get("/check/progress", params={"job": job}, headers=HX)


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
    assert "Proof: found" in part.text
    assert f'href="https://hashscan.io/testnet/topic/{TOPIC}"' in part.text
    assert "Seen before" in part.text and "Same repository." in part.text
    assert "Most similar past projects" in part.text and "Cedar Post" in part.text
    assert model_calls(fake, before) == 0  # the closest projects need an embedding only
    # The facts, the README, the version and the code (two requests for its archive), once.
    assert len(client.github_site.seen) == 5
    code = part.text.split("Hedera in the code", 1)[1].split("</section>", 1)[0]
    assert "Consensus Service (topics) &middot; 1 file" in code
    assert f'href="{REPO}/blob/{ARCHIVE_COMMIT}/src/topic.ts"' in code
    assert 'Commit checked: <span class="id">7260ea729063</span>' in part.text
    assert "the latest on main" in part.text  # the branch, by its name
    day = r"\d{1,2} [A-Z][a-z]+ \d{4}"
    assert re.search(rf"Fetched from GitHub on {day}: the repository details, the README "
                     r"\(README\.md\) and the latest commit\.", part.text)  # fmt: skip
    page = client.get("/check", params=asked)  # without JavaScript: a page of its own
    assert page.status_code == 200 and '<h1 id="viewer-title"' in page.text
    # A check is kept for good (7 November 2026): though the stand-in's answers are dated 11
    # October 2026, this check asks GitHub again only for the archive, which the stand-in made from
    # another commit than its newest one; "Read again now" would ask for everything.
    assert len(client.github_site.seen) == 7
    hidden = '<h2 class="visually-hidden">What the check found</h2>'
    assert hidden in page.text and hidden not in part.text


def test_a_spent_budget_is_named_and_never_taken_for_google_away(site) -> None:  # noqa: ANN001
    """Until 29 October 2026 a spent budget made the search by meaning say that Google's
    embedding service did not respond."""
    client, fake, _, database = site
    meter = Meter(MemoryStore(), "test", budget=Budget("test", total_usd=0.0), location="global")
    spent = MeteredClient(fake.client(), meter, Tags(purpose="embed_query"))
    poor = client.make(app_options={"google": spent})
    page = poor.get("/", params={"idea": "a coin box that counts what a vendor sold",
                                 "mode": "meaning"})  # fmt: skip
    assert "The budget for AI calls is spent, so these are keyword results." in page.text
    assert "did not respond" not in page.text
    asked = {"repo": REPO, "event": checkable(database)}
    part = poor.get("/check", params=asked, headers=HX)
    assert "cannot be shown: the budget for AI calls is spent." in part.text
    assert "did not respond" not in part.text


def test_a_rehearsal_says_so_at_the_top_of_every_page(site) -> None:  # noqa: ANN001
    """Started with --rehearsal, the website writes to the topic for rehearsals, and a band says
    so, so that a rehearsal is never taken for the register (design 9.3, 25 October 2026)."""
    client, _, ids, _ = site
    assert "hm-rehearsal" not in client.get("/").text
    rehearsal = client.make({"rehearsal": True})
    for page in ("/", f"/project/{ids['Pebble Pay']}"):
        band = rehearsal.get(page).text.split('class="hm-rehearsal"', 1)[1].split("</p>")[0]
        assert "Rehearsal mode" in band  # the box of the register names the topic


def test_a_rehearsal_names_the_practice_topic_above_the_button_and_on_the_receipt(site) -> None:  # noqa: ANN001
    """The band scrolls away with the page, so the box of the register and its receipt say again
    where the record goes (design 9.3, review layer 1 of 28 October 2026)."""
    client, _, _, database = site
    event = checkable(database)
    asked = {"repo": "github.com/sample-org/pebble-pay", "event": event}
    real = client.get("/check", params=asked, headers=HX).text
    assert "The button writes one record to the public register on Hedera testnet" in real
    rehearsal = client.make({"rehearsal": True})
    check = rehearsal.get("/check", params=asked, headers=HX).text
    box = check.split('id="register-box"', 1)[1].split("</section>", 1)[0]
    assert (f'the button writes one record to the practice topic <span class="id">{REGISTER}'
            "</span> on Hedera testnet, not to the register") in box  # fmt: skip
    assert "The button writes one record to the public register" not in box
    with_line(client, check)
    form = {**asked, "starts": "", "ends": "", "account": ""}
    done = rehearsal.post("/register", data=form, headers=HX)
    assert done.status_code == 200 and "Registered on the practice topic" in done.text


def test_a_card_is_read_again_at_the_press_of_its_button(site) -> None:  # noqa: ANN001
    """ "Read again now" asks GitHub and the mirror node again about one project, and the card
    shows itself again, in its window or as its page (design 7.3, S2, 25 October 2026)."""
    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    checkable(database)  # Pebble Pay keeps the code of REPO
    own_id(database, pebble, "0.0.4870201", "topic")
    panel = client.get(f"/project/{pebble}/panel").text
    block = panel[panel.index(f'id="read-{pebble}"') :].split("</aside>")[0]
    assert "The mirror node read on 22 October 2026." in block and "read again by" not in block
    assert f'hx-post="/project/{pebble}/read-again' in block and "Read again now" in block
    before = len(client.github_site.seen)
    answer = client.post(f"/project/{pebble}/read-again", headers=HX)
    assert answer.status_code == 200 and answer.headers["HX-Retarget"] == "#viewer-body"
    assert len(client.github_site.seen) > before  # GitHub was asked about its repository
    shown = answer.text[answer.text.index(f'id="read-{pebble}"') :].split("</aside>")[0]
    assert "GitHub read on 11 October 2026" in shown  # the card, read again
    # what the reading found stays in the block, for every visitor (28 October 2026)
    assert "read again by a visitor:" in shown and "<li>A README was found.</li>" in shown
    later = client.get(f"/project/{pebble}/panel").text
    assert "read again by a visitor:" in later and "<li>A README was found.</li>" in later
    assert client.get(f"/project/{pebble}/read-again", headers=HX).headers["HX-Retarget"]
    as_page = client.post(f"/project/{pebble}/read-again?page=1", headers=HX)
    assert as_page.headers["HX-Refresh"] == "true"  # the card's own page loads again


def test_the_block_of_the_readings_shows_its_steps_and_a_failure_in_words(site) -> None:  # noqa: ANN001
    """While a project is read again, its block shows the steps, those done marked and the one
    that runs turning; a failure says what went wrong and offers to try again (design 7.3, S2)."""
    from hackathon_memory.web.refresher import FAILED, RUNNING, State

    client, _, ids, _ = site
    pebble = ids["Pebble Pay"]
    reader = client.app.state.refresher
    moment = datetime(2026, 10, 28, 7, tzinfo=UTC)
    reader.state = lambda _pid: State(RUNNING, moment, None, "ledger")
    running = client.get(f"/project/{pebble}/read-again", headers=HX).text
    assert 'hx-trigger="every 1s"' in running and ">Reading again</p>" in running
    assert running.count('class="is-done"') == 2 and running.count('class="is-now"') == 1
    assert 'Its Hedera IDs on the ledger<span class="visually-hidden">: running</span>' in running
    reader.state = lambda _pid: State(FAILED, moment, "MirrorError")
    failed = client.get(f"/project/{pebble}/read-again", headers=HX).text
    assert "The mirror node did not answer. The card keeps what it read before." in failed
    assert "every 1s" not in failed and "Try again" in failed


def test_errors_say_what_happened_and_what_to_do(site) -> None:  # noqa: ANN001
    """An address or a project that does not exist, a refusal of the register, and a repository
    that GitHub does not show each say so in words a person can act on (28 October 2026)."""
    client, _, _, database = site
    page = client.get("/nothing-here")
    assert page.status_code == 404 and "This page does not exist." in page.text
    assert '"detail"' not in page.text  # not the framework's JSON
    assert client.get("/nothing-here", headers=HX).status_code == 404
    opened = client.get("/", params={"open": "999999"}).text
    body = opened.split('id="viewer-body">', 1)[1].split("</dialog>", 1)[0]
    assert "There is no project with this ID." in body and 'class="project"' in body
    gone = client.get("/check", params={"repo": "github.com/sample-org/no-such-thing"}, headers=HX)
    assert gone.status_code == 404 and "GitHub has no public repository at this link" in gone.text
    assert "Proof:" not in gone.text  # no page of empty facts around it
    event = checkable(database)
    asked = {"repo": "github.com/sample-org/pebble-pay", "event": event}
    with_line(client, client.get("/check", params=asked, headers=HX).text)
    client.writes.refused = "INSUFFICIENT_PAYER_BALANCE"
    refused = client.post("/register", data={**asked, "starts": "", "ends": "", "account": ""},
                          headers=HX)  # fmt: skip
    shown = html.unescape(refused.text)  # as a person reads it
    assert refused.status_code == 503 and "INSUFFICIENT_PAYER_BALANCE" not in shown
    assert ("Nothing was registered: the site's Hedera account has run out of HBAR. Try again "
            "in a minute.") in shown  # fmt: skip


def test_the_activity_of_a_check_names_its_hackathon_and_one_not_over(site) -> None:  # noqa: ANN001
    """The line of the activity says which hackathon it is counted from, as the card does, and a
    hackathon that is not over says so with its last day (design 7.4, 25 October 2026: it said
    "the event ended less than 90 days ago")."""
    client, _, _, database = site
    event = checkable(database)

    def life_line(asked: dict[str, str]) -> str:
        part = client.get("/check", params={"repo": REPO, **asked}, headers=HX)
        return part.text[part.text.index('id="check-life"') :].split("</p>")[0]

    past = life_line({"event": event})
    assert "ETHGlobal Sample Event ended on 8 March 2026, so a sign of life" in past
    assert "after 7 April 2026." in past and "Last push: 8 March 2026, read from GitHub on " in past
    future = life_line({"event": "other", "starts": "2099-01-01", "ends": "2099-01-05"})
    assert "The hackathon of the days typed in ends on 5 January 2099, so" in future
    assert "So: the event is not over yet." in future and "ended" not in future


def test_a_check_tells_the_ledger_story_of_its_readme_and_keeps_the_histories(site) -> None:  # noqa: ANN001
    """The ledger story in a check (design 7.5, "In a check"): the README in the place of the
    page, its lines that name a service under the table, and the history of each own ID read
    once and taken from the table by a second check."""
    from checkfakes import README, readme_answer
    from fakes import Reply
    from hackathon_memory.collect.github import readme_address

    client, _, _, database = site
    event = checkable(database)
    text = f"{README}\nEvery sale is a message on HCS.\nPayouts use HTS, and HCS again.\n"
    client.github_site.pages[readme_address(REPO)] = Reply(200, readme_answer(text))
    asked = {"repo": REPO, "event": event}
    part = client.get("/check", params=asked, headers=HX).text
    block = part.split("Hedera services: README, code and ledger", 1)[1].split("</section>", 1)[0]
    assert '<th scope="col">README</th>' in block and 'data-said-in="in the README"' in part
    assert "from 4 February 2026 to 7 April 2026, the event and 30 days on each side" in block
    said = (
        r"<li>The README names the Token Service " + WORDS_IN_BRACKETS + r", and its IDs show no "
    )
    named = re.search(said + r"Token Service transactions in that time\.</li>", block, re.DOTALL)
    assert named and 'data-said-word="hts"' in named.group(1)
    assert "Where the README names them (2 lines)" in block
    assert '<mark class="hm-said" data-said="tokens" data-word="hts">HTS</mark>' in block
    assert "of its own IDs." in block  # what its own IDs are is in the (i)
    depth = part.split('id="depth-check"', 1)[1].split("</section>", 1)[0]  # design 7.5
    assert "1 message to a topic." in depth
    assert "<q>" not in depth  # the README's words are marked in its lines, not quoted again
    with psycopg.connect(database) as conn:
        first = conn.execute("SELECT asked_at FROM ledger_histories WHERE entity_id = %s",
                             (TOPIC,)).fetchall()  # fmt: skip
    assert len(first) == 1  # read once, and kept
    client.get("/check", params=asked, headers=HX)
    with psycopg.connect(database) as conn:
        again = conn.execute("SELECT asked_at FROM ledger_histories WHERE entity_id = %s",
                             (TOPIC,)).fetchall()  # fmt: skip
    assert again == first  # the second check took it from the table
    none = client.get("/check", params={"repo": REPO}, headers=HX).text  # no hackathon
    assert "Ledger: every transaction of its own IDs. No hackathon was chosen." in none


def test_read_again_now_of_a_check_shows_what_the_ledger_did_since(site) -> None:  # noqa: ANN001
    """His scene of 5 November 2026: register, read again, and the new action is on the days of
    the IDs. A plain second check still takes the ledger's answers from the table."""
    from checkfakes import TOPIC

    client, _, _, database = site
    event = checkable(database)
    asked = {"repo": REPO, "event": event}
    part = client.get("/check", params=asked, headers=HX).text
    assert "data-check-again" in part and "Read again now" in part
    button = re.search(r'hx-get="(/check\?[^"]*again=1[^"]*)"', part)
    assert button is not None and "progress=1" in button.group(1)
    assert 'data-tip="tip-check-again"' in part
    depth = part.split('id="depth-check"', 1)[1].split("</section>", 1)[0]
    assert "1 message to a topic." in depth
    with psycopg.connect(database) as conn:
        first = conn.execute("SELECT asked_at FROM ledger_histories WHERE entity_id = %s",
                             (TOPIC,)).fetchall()  # fmt: skip
    assert len(first) == 1
    client.mirrors["testnet"].lists[("messages", TOPIC)].append(  # a new message, after the check
        {"sequence_number": 8, "consensus_timestamp": "1772884801.000000001"}
    )
    plain = client.get("/check", params=asked, headers=HX).text
    assert "2 messages to a topic." not in plain
    again = client.get("/check", params={**asked, "again": "1"}, headers=HX).text
    with psycopg.connect(database) as conn:
        later = conn.execute("SELECT asked_at FROM ledger_histories WHERE entity_id = %s",
                             (TOPIC,)).fetchall()  # fmt: skip
    assert later != first  # read again now, not taken from the table
    shown = again.split('id="depth-check"', 1)[1].split("</section>", 1)[0]
    assert "2 messages to a topic." in shown


def a_press_ago(database: str, hours: float) -> None:
    """The last presses of "Read again now" were made `hours` earlier than they were."""
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE read_again_uses SET used_at = used_at - make_interval(secs => %s)",
                     (hours * 3600,))  # fmt: skip


def presses_of(database: str) -> list[tuple]:
    with psycopg.connect(database) as conn:
        return conn.execute("SELECT what, used_at FROM read_again_uses").fetchall()


def test_a_check_is_read_again_once_in_3_hours(site) -> None:  # noqa: ANN001
    """His word of 6 November 2026: one press every 3 hours for a repository. A press too soon
    asks nothing and the check is a plain one; the button is greyed out and says from when."""
    from checkfakes import TOPIC

    client, _, _, database = site
    event = checkable(database)
    asked = {"repo": REPO, "event": event}
    client.get("/check", params=asked, headers=HX)  # a plain check uses no press
    assert "data-check-again>Read again now" in client.get("/check", params=asked, headers=HX).text
    first = client.get("/check", params={**asked, "again": "1"}, headers=HX).text
    assert re.search(r"<button[^>]*disabled>Read again now</button>", first)
    assert "again=1" not in first and "You can read it again from " in first
    stamp = presses_of(database)
    assert [what for what, _ in stamp] == [REPO]
    client.mirrors["testnet"].lists[("messages", TOPIC)].append(  # a new message, after the press
        {"sequence_number": 8, "consensus_timestamp": "1772884801.000000001"}
    )
    soon = client.get("/check", params={**asked, "again": "1"}, headers=HX)
    assert soon.status_code == 200 and "You can read it again from " in soon.text
    assert "2 messages to a topic." not in soon.text  # nothing was asked
    assert presses_of(database) == stamp  # a press too soon does not put the next one further off
    a_press_ago(database, 2.9)
    assert "You can read it again from " in client.get("/check", params=asked, headers=HX).text
    a_press_ago(database, 0.2)  # now 3.1 hours ago
    plain = client.get("/check", params=asked, headers=HX).text
    assert "You can read it again from " not in plain and "data-check-again>Read again now" in plain
    again = client.get("/check", params={**asked, "again": "1"}, headers=HX).text
    shown = again.split('id="depth-check"', 1)[1].split("</section>", 1)[0]
    assert "2 messages to a topic." in shown and "You can read it again from " in again


def test_a_reading_of_a_check_that_failed_does_not_count(site, monkeypatch) -> None:  # noqa: ANN001
    """The mirror node did not answer: the team can press again at once."""
    from checkfakes import TOPIC
    from hackathon_memory.hedera.mirror import MirrorError

    client, _, _, database = site
    event = checkable(database)
    asked = {"repo": REPO, "event": event, "again": "1"}

    def away(*_args: object, **_more: object) -> None:
        raise MirrorError("down")

    mirror = client.mirrors["testnet"]
    monkeypatch.setattr(mirror, "topic", away)
    failed = client.get("/check", params=asked, headers=HX).text
    assert "The mirror node of Hedera did not answer" in failed
    assert "You can read it again from " not in failed and "again=1" in failed
    assert presses_of(database) == []
    monkeypatch.undo()
    assert TOPIC in mirror.things["topic"]
    assert "You can read it again from " in client.get("/check", params=asked, headers=HX).text


def test_a_card_is_read_again_once_in_3_hours(site) -> None:  # noqa: ANN001
    """The button of a card has the same limit (6 November 2026). A press too soon asks nothing
    and brings the card back, whose button says from when; a failed reading does not count."""
    from hackathon_memory.web.refresher import FAILED, State

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    checkable(database)  # Pebble Pay keeps the code of REPO
    own_id(database, pebble, "0.0.4870201", "topic")
    press = f"/project/{pebble}/read-again"
    assert f'hx-post="{press}' in client.get(f"/project/{pebble}/panel").text
    first = client.post(press, headers=HX)
    assert first.status_code == 200 and f'hx-post="{press}' not in first.text
    assert re.search(r"<button[^>]*disabled>Read again now</button>", first.text)
    assert "You can read it again from " in first.text
    asked = len(client.github_site.seen)
    soon = client.post(press, headers=HX)
    assert soon.headers["HX-Retarget"] == "#viewer-body"
    assert "You can read it again from " in soon.text
    assert len(client.github_site.seen) == asked  # nothing was asked
    assert "You can read it again from " in client.get(f"/project/{pebble}").text  # on its page too
    a_press_ago(database, 3.1)
    assert f'hx-post="{press}' in client.get(f"/project/{pebble}/panel").text
    reader = client.app.state.refresher
    real = reader.ask
    reader.ask = lambda _pid: State(FAILED, datetime.now(UTC), "MirrorError")
    assert "The mirror node did not answer" in client.post(press, headers=HX).text
    assert presses_of(database) == []  # given back: "Try again" can be pressed at once
    reader.ask = real
    assert client.post(press, headers=HX).status_code == 200
    assert len(client.github_site.seen) > asked


def test_a_check_asked_by_the_script_shows_its_steps_until_the_answer(site) -> None:  # noqa: ANN001
    """The page's script asks with progress=1: the check runs in a thread of its own, the window
    shows its steps, and the next ask gives the answer in place of the whole window (design 12.1,
    S3). Without the script, the page waits for the answer as before."""
    client, _, _, database = site
    event = checkable(database)
    asked = {"repo": REPO, "event": event, "progress": "1"}
    first = client.get("/check", params=asked, headers=HX)
    assert first.status_code == 200 and 'id="check-steps"' in first.text
    assert '<h2 id="viewer-title"' in first.text and 'id="check-said"' in first.text
    assert first.text.count('class="hm-step ') == 5
    answer = answer_of(client, first)
    assert answer.headers["HX-Retarget"] == "#viewer-body"
    assert (
        "Proof: found" in answer.text and "Hedera services: README, code and ledger" in answer.text
    )
    job = re.search(r"/check/progress\?job=([\w-]+)", first.text).group(1)
    lost = client.get("/check/progress", params={"job": job}, headers=HX)  # taken already
    assert lost.status_code == 404 and "This check is no longer kept" in lost.text
    page = client.get("/check", params=asked)  # without the script: a page of its own
    assert page.status_code == 200 and "Proof: found" in page.text


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
    assert "Same 1." in done.text and "Compared by Gemini with this README" in done.text
    again = client.get(asked.group(1).replace("&amp;", "&"), headers=HX)
    assert "Same 1." in again.text and model_calls(fake, before) == 1  # kept for one day
    never = {"repo": "github.com/nobody/never-checked", "ids": places[0], "place": "check"}
    unknown = client.get("/compare", params=never, headers=HX)
    assert unknown.status_code == 400 and model_calls(fake, before) == 1  # GitHub has no README
    assert f'id="check-compare-{places[0]}" hx-swap-oob="true"' in unknown.text  # nothing waits
    assert "could not be read from GitHub" in unknown.text
    assert "Compare these 1 with Gemini</button>" in unknown.text  # the button comes back


def test_a_check_shows_its_comparison_kept_for_good(site) -> None:  # noqa: ANN001
    """A comparison with Gemini asked for a check is kept for good and shows at once on the next
    check of the same README, with no new call and no button; a typed idea keeps one day (7
    November 2026)."""
    client, fake, _, database = site
    event = checkable(database)
    part = client.get("/check", params={"repo": REPO, "event": event}, headers=HX)
    asked = re.search(r'hx-get="(/compare\?repo=[^"]+&amp;place=check)"', part.text).group(1)
    places = re.findall(r'id="check-compare-(\d+)"', part.text)
    fake.answer_text = compare_answer(*[(n, ["what_it_does"]) for n in range(1, len(places) + 1)])
    assert client.get(asked.replace("&amp;", "&"), headers=HX).status_code == 200
    before = len(fake.requests)
    again = client.get("/check", params={"repo": REPO, "event": event}, headers=HX)
    assert model_calls(fake, before) == 0
    assert "Same 1." in again.text and "Kept until the check is read again." in again.text
    assert "data-check-compare" not in again.text  # every place is filled: no button
    with psycopg.connect(database) as conn:
        kept = conn.execute("SELECT count(*) FROM idea_comparisons WHERE kept").fetchone()[0]
        embedded = conn.execute("SELECT count(*) FROM idea_embeddings WHERE kept").fetchone()[0]
    assert kept == len(places) and embedded == 1  # the README's embedding too


def test_a_comparison_reads_the_readme_on_a_copy_that_lost_it(site, tmp_path) -> None:  # noqa: ANN001
    """On a host, a request may land on a copy of the site with files of its own, without the
    README that the check saved. It answered 400 with none of the places, and on the page they
    kept waiting for ever (7 November 2026). GitHub is now asked again."""
    client, fake, _, database = site
    event = checkable(database)
    part = client.get("/check", params={"repo": REPO, "event": event}, headers=HX)
    asked = re.search(r'hx-get="(/compare\?repo=[^"]+&amp;place=check)"', part.text).group(1)
    places = re.findall(r'id="check-compare-(\d+)"', part.text)
    another_copy = client.make(data_dir=str(tmp_path / "another-copy"))
    fake.answer_text = compare_answer(*[(n, ["what_it_does"]) for n in range(1, len(places) + 1)])
    before = len(fake.requests)
    done = another_copy.get(asked.replace("&amp;", "&"), headers=HX)
    assert done.status_code == 200 and model_calls(fake, before) == 1  # read again, then compared
    assert "Same 1." in done.text and "Compared by Gemini with this README" in done.text


def test_a_comparison_says_so_when_github_cannot_give_the_readme(site, tmp_path) -> None:  # noqa: ANN001
    """GitHub away, or answering with an error: the visitor is told, nothing waits, Gemini is not
    asked, and the button comes back."""
    import requests

    from fakes import Reply
    from hackathon_memory.collect.github import readme_address

    client, fake, ids, _ = site
    params = {"repo": REPO, "ids": str(ids["Pebble Pay"]), "place": "check"}
    answers = {"away": requests.ConnectionError("no route to GitHub"),
               "failing": Reply(500, b"{}"), "refusing": Reply(403, b"{}")}  # fmt: skip
    for name, answer in answers.items():
        client.github_site.pages[readme_address(REPO)] = [answer] * 10
        another_copy = client.make(data_dir=str(tmp_path / name))
        before = len(fake.requests)
        part = another_copy.get("/compare", params=params, headers=HX)
        assert part.status_code == 400, name
        assert model_calls(fake, before) == 0
        assert "could not be read from GitHub" in part.text
        assert f'id="check-compare-{ids["Pebble Pay"]}" hx-swap-oob="true"' in part.text
        assert "Compare these 1 with Gemini</button>" in part.text


def test_a_long_readme_is_compared_by_its_start_and_says_so(site) -> None:  # noqa: ANN001
    """Gemini reads at most LONGEST_COMPARED characters of a README, more than the 4,000 of an
    idea typed in the box, so a long one can neither break the call nor cost more, and the line
    under the button says what was read (7 November 2026)."""
    from checkfakes import readme_answer
    from fakes import Reply
    from hackathon_memory.check.submission import LONGEST_COMPARED
    from hackathon_memory.collect.github import readme_address
    from hackathon_memory.web.app import LONGEST_IDEA

    client, fake, ids, _ = site
    long_readme = "A long README about a coin on Hedera. " * 3000
    assert len(long_readme) > 100_000
    client.github_site.pages[readme_address(REPO)] = Reply(200, readme_answer(long_readme))
    fake.answer_text = compare_answer((1, ["what_it_does"]))
    before = len(fake.requests)
    params = {"repo": REPO, "ids": str(ids["Pebble Pay"]), "place": "check"}
    done = client.get("/compare", params=params, headers=HX)
    assert done.status_code == 200 and model_calls(fake, before) == 1
    assert f"the first {LONGEST_COMPARED:,} characters of this README" in done.text
    sentence = len("A long README about a coin on Hedera. ")
    read = str(fake.requests[-1]).count("A long README") * sentence
    assert LONGEST_IDEA < read <= LONGEST_COMPARED + sentence  # 10,000, not the idea's 4,000


def test_a_check_without_a_repository_or_with_wrong_days_says_what_to_do(site) -> None:  # noqa: ANN001
    client, _, _, database = site
    event = checkable(database)
    wrong = client.get("/check", params={"repo": "my project", "event": event}, headers=HX)
    assert wrong.status_code == 400 and "This is not a GitHub repository link" in wrong.text
    backwards = {"repo": REPO, "event": "other", "starts": "2026-03-08", "ends": "2026-03-06"}
    late = client.get("/check", params=backwards, headers=HX)
    assert late.status_code == 400 and "Enter the start and end dates" in late.text
    for odd in ("99999", "²", "1" * 5000):  # "²" passes str.isdigit(), and int() refuses it
        unknown = client.get("/check", params={"repo": REPO, "event": odd}, headers=HX)
        assert unknown.status_code == 400 and "That hackathon is not in the list" in unknown.text
    assert client.github_site.seen == []  # nothing was asked of GitHub
    typed = {"repo": REPO, "event": "other", "starts": "2026-03-06", "ends": "2026-03-08"}
    days = client.get("/check", params=typed, headers=HX)
    assert days.status_code == 200 and "6 March 2026 to 8 March 2026" in days.text
    # Typed days are checked, but a registration names a hackathon of the list.
    assert "Custom dates can be checked, but not registered." in days.text
    assert "Register on Hedera testnet" not in days.text
    form = {**typed, "account": ""}
    refused = client.post("/register", data=form, headers=HX)
    assert refused.status_code == 400 and "Pick it in the list" in refused.text
    assert client.writes.written == []


def test_with_no_hackathon_the_check_offers_the_one_of_the_same_code(site) -> None:  # noqa: ANN001
    """A faster registration: Pebble Pay of the collection holds the same code, so the check
    offers its hackathon, and the button checks the code again for it."""
    client, _, _, database = site
    event = checkable(database)
    part = client.get("/check", params={"repo": REPO}, headers=HX)
    assert "Register it for that hackathon?" in part.text
    offer = re.search(r'hx-get="(/check\?repo=[^"]+&amp;event=(\d+)&amp;progress=1)"', part.text)
    assert offer is not None and offer.group(2) == event
    again = answer_of(client, client.get(offer.group(1).replace("&amp;", "&"), headers=HX))
    assert again.status_code == 200 and "Register on Hedera testnet" in again.text


def test_a_hackathon_of_the_list_can_be_checked_and_registered(site) -> None:  # noqa: ANN001
    """A hackathon that the collection does not hold, added to the list by hand: it is offered
    in the list of the check with its days, and the register names it by its key."""
    from hackathon_memory.hedera.listed import LISTED

    client, _, _, _ = site
    one = LISTED[0]
    page = client.get("/")
    assert f'<option value="{one.key}">' in page.text
    check = client.get("/check", params={"repo": REPO, "event": one.key}, headers=HX)
    assert check.status_code == 200 and one.name in check.text
    assert one.key in check.text and "Register on Hedera testnet" in check.text


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
    assert "Transaction: token created, 7 March 2026." in part.text
    assert f'href="https://hashscan.io/testnet/transaction/{tx}"' in part.text


def test_a_scheduled_transaction_is_shown_in_plain_words(site) -> None:  # noqa: ANN001
    """HashScan shows a schedule at /schedule/, and the window names it in words."""
    from hackathon_memory.check.ledger import LedgerFacts
    from hackathon_memory.db.ledger import LedgerStore

    client, _, ids, database = site
    made, ran = datetime(2026, 3, 7, 12, tzinfo=UTC), datetime(2026, 3, 9, 12, tzinfo=UTC)
    LedgerStore(database).save_facts(LedgerFacts(
        "0.0.9743551", "testnet", datetime(2026, 10, 22, tzinfo=UTC), found=True,
        kind="schedule", ledger_id="0.0.9743551", created_at=made, first_activity_at=made,
        last_activity_at=ran, details={"executed": True},
    ))  # fmt: skip
    pebble = ids["Pebble Pay"]
    with psycopg.connect(database) as conn:
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, '0.0.9743551', 'testnet', 'schedule', "
            "'readme', 'invented', true) RETURNING id", (pebble,)).fetchone()  # fmt: skip
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                     "VALUES (%s, 'testnet', 'proof_found')", (hedera_id,))  # fmt: skip
    part = client.get(f"/project/{ids['Pebble Pay']}/panel")
    assert "Scheduled transaction, created 7 March 2026, last activity 9 March 2026." in part.text
    assert 'href="https://hashscan.io/testnet/schedule/0.0.9743551"' in part.text


def test_the_hackathon_of_a_check_is_optional(site) -> None:  # noqa: ANN001
    """The tool is a memory, not a live view: with no hackathon, the facts are shown with their
    own dates and not judged, and the register asks for one (design 12.1, S3)."""
    client, _, _, database = site
    alone = client.get("/check", params={"repo": REPO, "event": ""}, headers=HX)
    assert "Registering needs a hackathon." in alone.text  # no project keeps this code yet
    assert "no hackathon: none found in Jevadu's register" in alone.text  # it was looked for
    checkable(database)
    start = client.get("/")
    assert '<option value="">Find it in Jevadu\'s register on Hedera</option>' in start.text
    assert '<option value="none">None: show the facts, without judging dates</option>' in start.text
    assert '<optgroup label="2026"><option value="' in start.text  # a group for each year
    assert "ETHGlobal Sample Event (6 to 8 March)</option>" in start.text  # a dated one
    part = client.get("/check", params={"repo": REPO, "event": "none"}, headers=HX)
    assert part.status_code == 200 and "no hackathon selected" in part.text
    # "found, dates not judged", in grey, was not understood (24 October 2026)
    mark = 'status-azure hm-status"><span class="status-dot"></span>Proof: IDs found, no hackathon'
    assert mark in part.text
    assert 'href="#check-ledger" data-scroll-to="check-ledger"' in part.text
    ledger = part.text[part.text.index('id="check-ledger"') :]
    assert "Choose the hackathon in the check form to judge them." in ledger
    head = part.text.split("</header>")[0]  # the marks of the check itself
    assert "its dates are not judged without a hackathon" in ledger and "Activity:" not in head
    assert "Register it for that hackathon?" in part.text  # Pebble Pay keeps it
    assert "Register on Hedera testnet" not in part.text
    form = {"repo": REPO, "event": "", "starts": "", "ends": "", "account": ""}
    refused = client.post("/register", data=form, headers=HX)
    assert refused.status_code == 400 and "Registering needs a hackathon" in refused.text
    assert client.writes.written == []


def register(client, event: str) -> None:  # noqa: ANN001
    """The team checks its code for `event`, adds the line to its README, and registers."""
    asked = {"repo": REPO, "event": event}
    with_line(client, client.get("/check", params=asked, headers=HX).text)
    done = client.post("/register", data={**asked, "starts": "", "ends": ""}, headers=HX)
    assert "Registered on Hedera" in done.text


def test_a_hackathon_left_to_the_tool_is_found_in_the_register(site) -> None:  # noqa: ANN001
    """His words of 6 November 2026: "Can't our tool be proactive and locate which hackathon since
    it was registered on our register?" A check that leaves the hackathon to the tool reads the
    register: the one hackathon that the records of the code name is used, and said (S3)."""
    client, _, _, database = site
    register(client, checkable(database))
    part = client.get("/check", params={"repo": REPO, "event": ""}, headers=HX)
    head = part.text.split("</header>")[0]
    assert "ETHGlobal Sample Event, from its registration on Hedera" in head
    assert 'popovertarget="tip-hackathon-found"' in head  # its (i) says where it comes from
    assert "no hackathon" not in head and "Activity:" in head  # its dates are judged
    assert "It is already registered for this hackathon" in part.text  # nothing written twice
    assert "Register on Hedera testnet" not in part.text
    plain = client.get("/check", params={"repo": REPO, "event": "none"}, headers=HX)
    assert "no hackathon selected" in plain.text and "from its registration" not in plain.text


def test_a_code_registered_for_several_hackathons_names_them_all(site) -> None:  # noqa: ANN001
    """Several hackathons in the register: the check uses none, names them, and offers to check
    the code again for each (S3)."""
    from hackathon_memory.hedera.listed import LISTED

    client, _, _, database = site
    register(client, checkable(database))
    register(client, LISTED[0].key)
    part = client.get("/check", params={"repo": REPO, "event": ""}, headers=HX)
    assert "no hackathon: registered for several" in part.text
    names = f"ETHGlobal Sample Event, {LISTED[0].name}"
    said = f"This repository is registered on Hedera for {names}. Check it for one of them?"
    assert said in part.text
    assert f"Check it for {LISTED[0].name}</button>" in part.text
    assert f"event={LISTED[0].key}&amp;progress=1" in part.text


def test_a_register_that_cannot_be_read_leaves_the_check_without_a_hackathon(site) -> None:  # noqa: ANN001
    from hackathon_memory.hedera.mirror import MirrorError

    client, _, _, database = site
    checkable(database)

    def away(*_: object, **__: object) -> list:
        raise MirrorError("The mirror node does not answer.")

    client.mirrors["testnet"].topic_messages_from = away
    part = client.get("/check", params={"repo": REPO, "event": ""}, headers=HX)
    assert part.status_code == 200 and "no hackathon: the register could not be read" in part.text
    assert "Register it for that hackathon?" in part.text  # the collection still names its own


@pytest.mark.browser
def test_the_window_shows_the_steps_of_a_check_and_then_its_answer(site, chromium) -> None:  # noqa: ANN001
    """While a check runs, the window shows its five steps and the bar; the answer then takes
    the place of the whole window, with its title in focus (design 12.1, S3)."""
    client, _, _, database = site
    checkable(database)
    page = served(chromium, client, reduced_motion="reduce")
    page.goto("http://site.test/")
    page.fill("#check-repo", "github.com/sample-org/pebble-pay")
    page.locator("#check button[type=submit]").click()
    page.wait_for_selector("#viewer[open] #check-steps")
    assert page.locator("#check-steps .hm-step").count() == 5
    assert page.locator("#check-bar").count() == 1
    page.wait_for_selector("#viewer[open] .check-result")
    assert page.locator("#check-steps").count() == 0
    assert page.evaluate("document.activeElement.id") == "viewer-title"
    assert "Hedera services: README, code and ledger" in page.locator("#viewer-body").inner_text()
    page.context.close()


@pytest.mark.browser
def test_the_hackathons_of_a_check_can_be_searched(site, chromium) -> None:  # noqa: ANN001
    """The box above the list of hackathons keeps those whose name holds its words, and Enter
    picks the first; "Find it in Jevadu's register", "None" and "Other hackathon" always stay
    (1 November 2026; the first since 6 November)."""
    client, _, _, database = site
    event = checkable(database)
    with psycopg.connect(database) as conn:
        conn.execute(
            "INSERT INTO events (site, slug, name, starts_at, ends_on) VALUES "
            "('ethglobal.com', 'later', 'Later Summit', '2026-06-10', '2026-06-14')"
        )
    page = served(chromium, client, reduced_motion="reduce")
    page.goto("http://site.test/")
    shown = "[...document.querySelectorAll('#check-event option')].filter(o => !o.hidden)" \
            ".map(o => o.textContent)"  # fmt: skip
    assert any("Later Summit" in name for name in page.evaluate(shown))
    page.fill("#check-event-search", "sample")
    kept = page.evaluate(shown)
    assert not any("Later Summit" in name for name in kept)
    assert kept[0].startswith("Find it in Jevadu") and kept[1].startswith("None")
    assert kept[-1].startswith("Other hackathon")
    page.press("#check-event-search", "Enter")
    assert page.input_value("#check-event") == event
    assert page.input_value("#check-event-search") == ""  # the whole list is back
    assert any("Later Summit" in name for name in page.evaluate(shown))
    page.context.close()


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
    assert "Compared by Gemini with this README" in page.locator("#check-compare-ask").inner_text()
    page.locator(".check-result .hm-close-name a").first.click()
    page.wait_for_selector("#viewer[open] .project[data-project]")
    assert page.locator("[data-back-to-check]").is_visible()
    assert not page.locator("[data-viewer-step]").first.is_visible()  # no list to step through
    page.locator("[data-back-to-check]").click()
    page.wait_for_selector("#viewer[open] .check-result")
    assert page.locator("#register-form").count() == 1  # the check as it was
    page.context.close()


@pytest.mark.browser
def test_a_wrong_link_says_what_to_do_in_the_window(site, chromium) -> None:  # noqa: ANN001
    """An answer of 400 takes the place of the steps of the check, and shows above the register's
    form, which stays as it was, to be sent again (30 October 2026)."""
    client, _, _, database = site
    event = checkable(database)
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto("http://site.test/")
    page.fill("#check-repo", "my project")
    page.locator("#check button[type=submit]").click()
    page.wait_for_selector("#viewer-body:has-text('This is not a GitHub repository link')")
    page.goto("http://site.test/")
    page.fill("#check-repo", "github.com/sample-org/pebble-pay")
    page.select_option("#check-event", event)
    page.locator("#check button[type=submit]").click()
    page.wait_for_selector("#viewer[open] .check-result")
    page.locator("#register-form button[type=submit]").click()  # no line in the README yet
    page.wait_for_selector("#register-problem:has-text('does not contain the line')")
    assert page.locator("#register-form").count() == 1  # the box stays
    problem, form = (page.locator(name).bounding_box()["y"]
                     for name in ("#register-problem", "#register-form"))  # fmt: skip
    assert problem < form  # at the top of the box
    page.context.close()


@pytest.mark.browser
def test_a_request_that_fails_leaves_no_waiting_state(site, chromium) -> None:  # noqa: ANN001
    """With no answer, the window of a project, the check and the list say so; an answer of 503
    with its own words takes the place of the waiting state."""
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900},
                  reduced_motion="reduce")  # fmt: skip
    page.goto(SEARCH)
    page.route("**/project/*/panel*", lambda route: route.abort())  # the last route runs first
    page.locator(".result-link").first.click()
    page.wait_for_selector("#viewer[open] #viewer-body:has-text('The server did not answer')")
    assert page.locator("#viewer-body .bone").count() == 0  # no waiting shapes are left
    page.keyboard.press("Escape")
    page.unroute("**/project/*/panel*")
    page.route("**/project/*/panel*", lambda route: route.fulfill(
        status=503, body=client.get("/project/999999/panel").text.replace(
            "There is no project with this ID", "The database of this site is not answering"),
        headers={"content-type": "text/html; charset=utf-8"}))  # fmt: skip
    page.locator(".result-link").first.click()
    page.wait_for_selector(
        "#viewer[open] #viewer-body:has-text('The database of this site is not answering')"
    )
    page.keyboard.press("Escape")
    page.route(lambda url: "/check?" in url, lambda route: route.abort())
    page.fill("#check-repo", "github.com/sample-org/pebble-pay")
    page.locator("#check button[type=submit]").click()
    page.wait_for_selector("#viewer[open] #viewer-body:has-text('The server did not answer')")
    assert page.locator("#viewer-body .check-progress").count() == 0  # the steps are gone
    page.keyboard.press("Escape")
    page.route(lambda url: url.startswith("http://site.test/?idea="), lambda route: route.abort())
    page.locator("#idea").fill("a market for used bicycles")
    page.wait_for_selector("#workspace .hm-failed:has-text('The server did not answer')")
    assert page.locator("li.result").count() == 3  # the list that was there stays
    page.context.close()


@pytest.mark.browser
def test_the_offered_hackathon_checks_the_code_again_in_the_window(site, chromium) -> None:  # noqa: ANN001
    """The faster registration: with no hackathon given, the button of the hackathon where the
    collection keeps the same code checks it again for that hackathon, in the same window."""
    client, _, _, database = site
    checkable(database)
    page = served(chromium, client, reduced_motion="reduce")
    page.goto("http://site.test/")
    page.fill("#check-repo", "github.com/sample-org/pebble-pay")
    page.locator("#check button[type=submit]").click()
    page.wait_for_selector("#viewer[open] [data-check-again]")
    page.locator("[data-check-again]").first.click()
    page.wait_for_selector("#viewer[open] #register-form")
    assert "no hackathon selected" not in page.locator("#viewer-body").inner_text()
    page.context.close()


# ----------------------------------------------------------------- the register (S4)


def test_a_checked_submission_is_registered_once_and_read_back(site) -> None:  # noqa: ANN001
    import hashlib

    client, _, _, database = site
    event = checkable(database)
    asked = {"repo": "github.com/sample-org/pebble-pay", "event": event}
    check = client.get("/check", params=asked, headers=HX)
    assert "This repository is not registered yet." in check.text
    assert "ethglobal.com/sample-event" in check.text and "Register on Hedera testnet" in check.text
    form = {**asked, "starts": "", "ends": ""}  # no signature: a record of version 2
    asked_before = len(client.github_site.seen)
    missing = client.post("/register", data=form, headers=HX)
    assert missing.status_code == 400 and "does not contain the line" in missing.text
    # above the box of the register, which stays as it was, with the newest commit read again
    assert missing.headers["HX-Retarget"] == "#register-problem"
    assert missing.text.strip().startswith('<div class="alert alert-warning mb-3" role="alert"')
    assert 'id="register-box"' not in missing.text
    assert f'data-latest-commit="{COMMIT}"' in missing.text
    assert len(client.github_site.seen) == asked_before + 2  # the README and the version, again
    assert client.writes.written == []  # nothing is written without the team's line
    with_line(client, check.text)
    done = client.post("/register", data=form, headers=HX)
    assert done.status_code == 200 and "Registered on Hedera" in done.text
    assert "<dt>Sequence number</dt><dd>1, on topic" in done.text
    assert "https://hashscan.io/testnet/transaction/1791585601.000000001" in done.text
    (payload,) = client.writes.written
    assert json.loads(payload) == {
        "v": 2, "event": "ethglobal.com/sample-event",
        "commit": "7260ea7290637399c6ac181ed893a567144d96eb",
        "code": hashlib.sha256(REPO.encode()).hexdigest(),
    }  # fmt: skip
    assert b"github" not in payload and b"pebble" not in payload  # no link in clear text
    again = client.post("/register", data=form, headers=HX)
    assert "Already registered" in again.text and len(client.writes.written) == 1
    later = client.get("/check", params=asked, headers=HX)
    assert "Already registered." in later.text and "sequence number 1" in later.text
    assert "Register on Hedera testnet" not in later.text  # it is registered for this event already


def test_a_record_that_the_mirror_node_does_not_show_yet_is_called_sent(site) -> None:  # noqa: ANN001
    """The record went to Hedera, and the mirror node, a few seconds behind, does not show it yet:
    the box says that it was sent, not that nothing was registered (30 October 2026)."""
    from hackathon_memory.hedera.mirror import MirrorError

    client, _, _, database = site
    event = checkable(database)
    asked = {"repo": REPO, "event": event}
    with_line(client, client.get("/check", params=asked, headers=HX).text)

    def behind(*_: object, **__: object) -> dict:
        raise MirrorError("The mirror node does not show the message yet.")

    client.mirrors["testnet"].wait_for_message = behind
    sent = client.post("/register", data={**asked, "starts": "", "ends": ""}, headers=HX)
    assert sent.status_code == 202 and len(client.writes.written) == 1
    assert ">Sent to Hedera</h3>" in sent.text and "Not registered" not in sent.text
    assert "does not show it yet" in sent.text


def test_a_registration_needs_a_checked_repository_and_a_real_account(site) -> None:  # noqa: ANN001
    client, _, _, database = site
    event = checkable(database)
    form = {"repo": REPO, "event": event, "starts": "", "ends": ""}
    first = client.post("/register", data=form, headers=HX)
    assert first.status_code == 400 and "Check the repository first" in first.text
    check = client.get("/check", params={"repo": REPO, "event": event}, headers=HX)
    with_line(client, check.text)
    signed = {"signer": "my wallet", "scheme": "eip191", "signature": "0x00"}
    wrong = client.post("/register", data={**form, **signed}, headers=HX)
    assert wrong.status_code == 400 and "A Hedera account ID looks like 0.0.12345" in wrong.text
    assert client.writes.written == []
    page = client.post("/register", data=form)  # without JavaScript: a page of its own
    assert page.status_code == 200 and "<h1" in page.text and len(client.writes.written) == 1


def test_a_closed_register_is_said_and_offers_no_button(site) -> None:  # noqa: ANN001
    client, _, _, database = site
    event = checkable(database)
    closed = client.make(hedera_topic_id="")
    check = closed.get("/check", params={"repo": REPO, "event": event}, headers=HX)
    assert "The public register is not open yet" in check.text
    assert "Register on Hedera testnet" not in check.text


def test_the_box_says_plainly_what_the_line_does_before_and_after_it_is_added(site) -> None:  # noqa: ANN001
    """The words under the line say what it proves and what the button does with it, in both
    states (30 October 2026: "The README already contains it. When you click the button, the
    README is read again" was not clear)."""
    client, _, _, database = site
    asked = {"repo": REPO, "event": checkable(database)}
    before = client.get("/check", params=asked, headers=HX).text
    assert "Only someone who can change this repository can add the line" in before
    assert "the site reads your README on GitHub again, to find the line." in before
    with_line(client, before)
    # A check is kept for good (7 November 2026): "Read again now" reads the new README.
    after = client.get("/check", params={**asked, "again": "1"}, headers=HX).text
    assert "Your README already has this line, so you can register now." in after
    assert "once more, to make sure the line is still there." in after


# --------------------------------------------- the line of the register, through GitHub (9.2)


def with_github_app(client, stand_in):  # noqa: ANN001, ANN201
    """The same site with Jevadu's GitHub App set, talking with a stand-in GitHub."""
    import httpx
    from pydantic import SecretStr

    talk = httpx.Client(transport=httpx.MockTransport(stand_in))
    return client.make({"github_app_client": talk}, github_app_slug="jevadu-register",
                       github_app_client_id="Iv1.standin",
                       github_app_client_secret=SecretStr("standin-secret"))  # fmt: skip


def started(site_with, event: str) -> str:  # noqa: ANN001
    """The state that the site sends to GitHub's sign-in, for Pebble Pay and `event`."""
    start = site_with.get("/github/start", params={"repo": REPO, "event": event},
                          follow_redirects=False)  # fmt: skip
    assert start.status_code == 303
    return parse_qs(urlsplit(start.headers["location"]).query)["state"][0]


def came_back(site_with, state: str):  # noqa: ANN001, ANN201
    return site_with.get("/github/callback", params={"code": "the-code", "state": state},
                         follow_redirects=False)  # fmt: skip


def test_the_box_offers_github_for_the_line_only_with_the_app(site) -> None:  # noqa: ANN001
    from test_github_app import StandInGitHub

    client, _, _, database = site
    event = checkable(database)
    asked = {"repo": REPO, "event": event}
    assert "Add it for me with GitHub" not in client.get("/check", params=asked, headers=HX).text
    box = with_github_app(client, StandInGitHub()).get("/check", params=asked, headers=HX).text
    assert ">Add it for me with GitHub</a>" in box
    assert 'href="/github/start?repo=https%3A%2F%2Fgithub.com%2Fsample-org%2Fpebble-pay' in box
    missing = client.get("/github/start", params=asked)  # a copy with no app
    assert missing.status_code == 503 and "has no GitHub App" in missing.text


def test_the_github_app_adds_the_line_as_a_commit_of_the_person(site) -> None:  # noqa: ANN001
    """GitHub signs the person in; the site checks that the app is installed on the repository
    and that the person may write to it, adds the line to the README as a commit of theirs, and
    goes back to the check, which says so. A way back with another state is refused, the token
    never shows, and a request serves once (design 9.2, 30 October 2026)."""
    from test_github_app import StandInGitHub

    client, _, _, database = site
    event = checkable(database)
    stand_in = StandInGitHub()
    site_with = with_github_app(client, stand_in)
    start = site_with.get("/github/start", params={"repo": REPO, "event": event},
                          follow_redirects=False)  # fmt: skip
    there = urlsplit(start.headers["location"])
    query = parse_qs(there.query)
    assert (there.netloc, there.path) == ("github.com", "/login/oauth/authorize")
    assert query["client_id"] == ["Iv1.standin"]
    assert query["redirect_uri"] == ["http://testserver/github/callback"]
    cookie = start.headers["set-cookie"].lower()
    assert "httponly" in cookie and "path=/github" in cookie and "samesite=lax" in cookie
    forged = came_back(site_with, "forged")
    assert forged.status_code == 400 and "did not come back" in forged.text
    assert stand_in.written == [] and stand_in.asked == []  # GitHub was not even asked
    back = came_back(site_with, query["state"][0])
    assert back.status_code == 303
    location = back.headers["location"]
    assert location.startswith("/check?") and "line=added" in location
    assert "commit=c0ffee" in location
    (written,) = stand_in.written
    check = site_with.get("/check", params={"repo": REPO, "event": event}, headers=HX).text
    line = re.search(r"jevadu: [A-Z2-7]{8}", check).group(0)
    assert stand_in.readme == f"# Pebble Pay\n\n{line}\n" and written["branch"] == "main"
    shown = site_with.get(location).text
    # news of its own, with the way to the commit, not the box's standing words
    notice = shown.split('<div class="alert alert-success mb-2" role="status">', 1)[1]
    notice = notice.split("</div>", 1)[0]
    assert notice.startswith("<b>Added just now.</b> Jevadu's GitHub App added this line")
    commit = "c0ffee" + "0" * 34
    assert f'href="https://github.com/sample-org/pebble-pay/commit/{commit}"' in notice
    assert "Add it for me with GitHub" not in shown
    assert "ghu_STANDIN" not in back.text + shown + str(back.headers) + str(start.headers)
    assert came_back(site_with, query["state"][0]).status_code == 400  # spent: its cookie is gone


def test_the_app_is_installed_first_and_the_sign_in_starts_again(site) -> None:  # noqa: ANN001
    """The first time, the app is not installed on the repository: GitHub's page of the install
    comes first. GitHub then sends the person to the setup URL, whose installation ID is not
    trusted, and the sign-in starts again, with a new state, for the request of this browser."""
    from test_github_app import StandInGitHub

    client, _, _, database = site
    event = checkable(database)
    stand_in = StandInGitHub(installed=False)
    site_with = with_github_app(client, stand_in)
    state = started(site_with, event)
    first = came_back(site_with, state)
    assert first.status_code == 303
    assert first.headers["location"] == "https://github.com/apps/jevadu-register/installations/new"
    assert stand_in.written == []
    stand_in.installed = True  # the person installs the app on the repository
    setup = site_with.get("/github/installed", params={"installation_id": "1",
                          "setup_action": "install"}, follow_redirects=False)  # fmt: skip
    assert setup.status_code == 303
    again = parse_qs(urlsplit(setup.headers["location"]).query)["state"][0]
    assert again != state
    assert came_back(site_with, state).status_code == 400  # the first state serves no more
    done = came_back(site_with, again)
    assert "line=added" in done.headers["location"] and len(stand_in.written) == 1
    alone = with_github_app(client, StandInGitHub()).get("/github/installed")  # nothing kept
    assert alone.status_code == 200 and "GitHub App is installed" in alone.text


def test_a_person_who_cannot_write_gets_no_line(site) -> None:  # noqa: ANN001
    from test_github_app import StandInGitHub

    client, _, _, database = site
    event = checkable(database)
    stand_in = StandInGitHub(push=False)
    site_with = with_github_app(client, stand_in)
    refused = came_back(site_with, started(site_with, event))
    assert refused.status_code == 403 and "cannot write to this repository" in refused.text
    assert stand_in.written == []
    assert '<a href="/check?repo=https%3A%2F%2Fgithub.com%2Fsample-org%2Fpebble-pay' in refused.text


def test_a_readme_with_the_line_is_left_as_it_is(site) -> None:  # noqa: ANN001
    from test_github_app import StandInGitHub

    client, _, _, database = site
    event = checkable(database)
    check = client.get("/check", params={"repo": REPO, "event": event}, headers=HX).text
    line = re.search(r"jevadu: [A-Z2-7]{8}", check).group(0)
    stand_in = StandInGitHub(readme=f"# Pebble Pay\n\n{line}\n")
    site_with = with_github_app(client, stand_in)
    back = came_back(site_with, started(site_with, event))
    assert "line=there" in back.headers["location"] and "commit=" not in back.headers["location"]
    assert stand_in.written == []
    shown = site_with.get(back.headers["location"]).text
    assert ('<div class="alert alert-info mb-2" role="status"><b>Already there.</b> The README on '
            "GitHub has this line already, so nothing was added.</div>") in shown  # fmt: skip


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
    assert page.status_code == 200 and 'aria-current="true">Insights</a>' in page.text
    assert "Live counts for 3 projects." in page.text
    assert page.text.count("<canvas data-chart=") >= 3 and "Linked across events" in page.text
    assert 'href="https://ethglobal.com/events/sample-event"' in page.text  # the event's page
    assert 'class="result"' not in page.text and len(fake.requests) == before
    search = client.get("/", params={"idea": VENDOR, "view": "charts", "mode": "meaning"})
    assert "for 3 projects, the closest to your idea" in search.text
    assert model_calls(fake, before) == 0  # charts call no model that writes


def test_the_insights_name_linked_projects_that_won_again(site) -> None:  # noqa: ANN001
    """Two projects with the same code won a Hedera prize at two events: the insights say so,
    with a link to each; the same projects without the prizes give no such sentence."""
    from hackathon_memory.db.repositories import RepositoryStore

    client, fake, ids, database = site
    with psycopg.connect(database) as conn:
        (later,) = conn.execute(
            "INSERT INTO events (site, slug, name) VALUES ('ethglobal.com', 'later', 'Later') "
            "RETURNING id"
        ).fetchone()
        conn.execute("UPDATE projects SET event_id = %s WHERE id = %s", (later, ids["Cedar Post"]))
    RepositoryStore(database).link({ids["Pebble Pay"]: REPO, ids["Cedar Post"]: REPO})
    page = client.get("/", params={"view": "charts"})
    assert "Won again." not in page.text  # linked, but neither won a Hedera prize
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET prize_state = 'hedera_prize' WHERE id = ANY(%s)",
                     ([ids["Pebble Pay"], ids["Cedar Post"]],))  # fmt: skip
    before = len(fake.requests)
    page = client.make().get("/", params={"view": "charts"})  # the facts are read again
    box = page.text.split('id="chart-insights"', 1)[1].split("</section>", 1)[0]
    assert "Won again." in box and "each won a Hedera prize, at 2 events." in box
    assert f'hx-get="/project/{ids["Pebble Pay"]}/panel"' in box
    assert f'hx-get="/project/{ids["Cedar Post"]}/panel"' in box
    assert len(fake.requests) == before  # counted from the tables, with no model


def test_a_share_is_shown_only_with_twenty_projects_behind_it() -> None:
    from hackathon_memory.search.counts import Tally
    from hackathon_memory.web.charts import build

    few = Tally(
        projects=3, proof=__import__("collections").Counter({"proof_found": 2, "no_id_given": 1})
    )
    chart = next(one for one in build(few, {}).charts if one.key == "proof")
    assert [(bar.words, bar.count, bar.share) for bar in chart.bars] == [
        ("Proof found", 2, None), ("No ID given", 1, None)]  # fmt: skip
    many = Tally(
        projects=40, proof=__import__("collections").Counter({"proof_found": 10, "no_id_given": 30})
    )
    chart = next(one for one in build(many, {}).charts if one.key == "proof")
    assert [bar.share for bar in chart.bars] == [25, 75]
    assert '"labels": ["Proof found", "No ID given"]' in chart.data()


def test_what_winners_use_is_compared_only_with_twenty_projects_on_each_side() -> None:
    """Two shares of the projects whose code was read: with a Hedera prize, and without."""
    from collections import Counter

    from hackathon_memory.search.counts import Tally
    from hackathon_memory.web.charts import build

    def compared(won: int, read: int) -> object:
        services = Counter({"Token Service": 30, "File Service": 6})
        services_won = Counter({"Token Service": 10, "File Service": 4})
        found = Tally(projects=read, code_read=read, code_read_won=won, code_services=services,
                      code_services_won=services_won)  # fmt: skip
        return build(found, {}).winners_use

    too_few = compared(won=19, read=100)
    assert too_few.pairs == () and "each side needs 20" in too_few.note
    both = compared(won=20, read=100)
    assert [(p.words, p.won_share, p.other_share) for p in both.pairs] == [
        ("Token Service", 50, 25), ("File Service", 20, 2)]  # fmt: skip
    assert "not why they won" in both.note and '"unit": "%"' in both.data()


def test_the_insights_come_in_four_tabs(site) -> None:  # noqa: ANN001
    """Without the page's script, the tab bar stays hidden and the four parts show one under
    the other; each part holds its own blocks."""
    client, _, _, _ = site
    page = client.get("/", params={"view": "charts"}).text
    assert '<div class="btn-group hm-tablist" role="tablist"' in page and "hidden>" in page
    parts = page.split('<section class="hm-tabpanel" id="panel-')[1:]
    panels = {part.split('"', 1)[0]: part for part in parts}
    assert list(panels) == ["overview", "services", "winners", "events"]
    assert 'id="chart-proof"' in panels["overview"] and 'id="chart-life"' in panels["overview"]
    assert 'id="chart-code_services"' in panels["services"]
    assert 'id="chart-code_packages"' in panels["services"]
    assert 'id="chart-services"' in panels["services"]
    assert 'id="chart-winners_use"' in panels["winners"]
    assert 'id="chart-event-table"' in panels["events"] and 'id="chart-themes"' in panels["events"]
    # A chart of one row was 74 pixels high, and a filter left its bars flat (24 October 2026).
    heights = [int(h) for h in re.findall(r'class="hm-chart-canvas" style="height: (\d+)px"', page)]
    assert heights and min(heights) >= 140


def embed_calls(fake, since: int = 0) -> int:  # noqa: ANN001
    return len([path for path, _ in fake.requests[since:] if "embedContent" in path])


def test_the_graph_draws_the_whole_collection_or_a_filtered_list(site, monkeypatch) -> None:  # noqa: ANN001
    from hackathon_memory.search import closeness

    client, fake, ids, database = site
    asked = 0
    similarities = closeness.similarities

    def counted(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        nonlocal asked
        asked += 1
        return similarities(*args, **kwargs)

    monkeypatch.setattr(closeness, "similarities", counted)
    before = len(fake.requests)
    whole = client.get("/", params={"view": "graph"})
    assert whole.status_code == 200 and 'aria-current="true">Graph</a>' in whole.text
    assert "The whole collection: 3 projects" in whole.text
    assert whole.headers.get("content-encoding") == "gzip"  # a page of the graph is large
    assert client.get("/", params={"view": "graph"}).status_code == 200 and asked == 1  # kept
    with psycopg.connect(database) as conn:
        (event,) = conn.execute("SELECT id FROM events LIMIT 1").fetchone()
    page = client.get("/", params={"event": event, "view": "graph"}).text
    assert page.count('<a class="hm-dot ') == 3 and 'class="hm-graph-idea"' not in page
    assert '<svg class="hm-graph-svg"' in page and 'aria-hidden="true"' in page
    assert "The whole collection:" not in page and 'data-proof="not checked yet"' in page
    # the key names the dashed line to the closest project too (30 October 2026: it had none)
    dashed = '<span class="hm-graph-stroke is-dashed" aria-hidden="true"></span>'
    assert f"{dashed}Closest project in meaning, for a dot you point at or keep</li>" in page
    # The same projects as lists of links, for a keyboard and a screen reader.
    assert page.count("data-graph-link=") == 3
    assert f'hx-get="/project/{ids["Pebble Pay"]}/panel?view=graph&amp;event={event}"' in page
    assert "Like " in page and "1 project" not in page  # three projects: one group
    assert len(fake.requests) == before  # the graph of a list asks no model
    # The name of a group opens the card of its project, on the graph and in its list; the list
    # counts what its projects won and proved; a long list waits for the script's buttons.
    assert page.count("data-graph-centre=") == 1 and page.count('<b>Like <a href="/?') == 1
    assert 'class="hm-graph-tally">none won a Hedera prize · none with a Hedera proof' in page
    assert 'data-more-for="members-1" hidden' in page and 'data-r="' in page
    assert '<div class="hm-graph-tools" role="group" aria-label="Zoom of the graph" hidden>' in page


def test_the_view_beside_the_cards_stays_when_the_search_changes(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    graph = client.get("/", params={"idea": VENDOR, "view": "graph"}).text
    assert '<input type="hidden" name="view" value="graph" id="view-kept">' in graph
    assert ('href="/?clear=1&amp;view=graph" data-clear-search hx-get="/" '
            'hx-include="#view-kept"') in graph  # fmt: skip
    cards = client.get("/", params={"idea": VENDOR}).text
    assert 'id="view-kept"' not in cards and 'href="/?clear=1" data-clear-search' in cards
    start = client.get("/", params={"view": "charts"}).text  # the examples keep it too
    assert 'value="charts" id="view-kept"' in start
    assert 'hx-include="#view-kept" hx-target="#main"' in start


def test_the_graph_says_when_its_numbers_follow_another_order_than_meaning(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    plain = client.get("/", params={"idea": VENDOR, "view": "graph", "mode": "meaning"}).text
    assert "the closer the project is in meaning" in plain and "in the list, which is" not in plain
    fake.answer_queue = [json.dumps({"closest": [3, 2, 1]})]
    ordered = client.get("/", params={"idea": VENDOR, "ai": "1", "view": "graph"}).text
    assert "numbered as in the list, which is Gemini's order" in ordered
    words = client.get("/", params={"idea": "invented", "mode": "words", "view": "graph"}).text
    assert "numbered as in the list, which is the keyword order" in words


def test_the_graph_of_a_search_stands_around_the_idea(site, monkeypatch) -> None:  # noqa: ANN001
    from hackathon_memory.web import graph

    client, fake, ids, _ = site
    before = len(fake.requests)
    page = client.get("/", params={"idea": VENDOR, "view": "graph", "mode": "meaning"}).text
    assert 'class="hm-graph-idea"' in page and page.count('<a class="hm-dot ') == 3
    first = re.search(r'<a class="hm-dot[^>]*data-graph-id="(\d+)"[^>]*data-rank="1"', page)
    assert first and int(first.group(1)) == ids["Pebble Pay"]  # the vendor's project
    assert "the closer the project is in meaning" in page
    assert embed_calls(fake, before) == 1 and model_calls(fake, before) == 0  # the search's own
    switch = re.search(r'href="/\?([^"]*)"[^>]*>Graph</a>', page)
    assert switch and "view=graph" in switch.group(1) and "idea=" in switch.group(1)
    monkeypatch.setattr(graph, "MOST", 2)
    many = client.get("/", params={"idea": VENDOR, "view": "graph", "mode": "meaning"}).text
    assert "the graph draws at most 2" in many and '<a class="hm-dot ' not in many


def test_the_first_ten_wear_a_crown_for_a_prize(site) -> None:  # noqa: ANN001
    """A filled gold crown for a Hedera prize, an outlined grey one for another sponsor's prize,
    each named in the key and in the lists under the graph (31 October 2026)."""
    client, _, ids, database = site
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET prize_state = 'hedera_prize' WHERE id = %s",
                     (ids["Pebble Pay"],))  # fmt: skip
        conn.execute("UPDATE projects SET prize_state = 'other_prize' WHERE id = %s",
                     (ids["Cedar Post"],))  # fmt: skip
    page = client.get("/", params={"idea": VENDOR, "view": "graph", "mode": "meaning"}).text
    dots = re.findall(r'<a class="hm-dot[^>]*data-graph-id="(\d+)".*?</a>', page, re.S)
    assert len(dots) == 3
    crowns = re.findall(r'data-graph-id="(\d+)"(?:(?!</a>).)*?class="hm-crown is-(\w+)"',
                        page, re.S)  # fmt: skip
    assert sorted(crowns) == sorted([(str(ids["Pebble Pay"]), "hedera"),
                                     (str(ids["Cedar Post"]), "other")])  # fmt: skip
    assert "Won a Hedera prize</li>" in page and "Won another sponsor's prize</li>" in page
    assert "&middot; won a Hedera prize</span>" in page  # the lists say it too
    # an event's list has no ranks, so no crowns, and no key of them
    with psycopg.connect(database) as conn:
        (event,) = conn.execute("SELECT id FROM events LIMIT 1").fetchone()
    listed = client.get("/", params={"event": event, "view": "graph"}).text
    assert 'class="hm-crown' not in listed and "Won a Hedera prize</li>" not in listed


@pytest.mark.browser
def test_a_crown_keeps_its_size_and_its_place_when_the_graph_zooms(site, chromium) -> None:  # noqa: ANN001
    client, _, ids, database = site
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET prize_state = 'hedera_prize' WHERE id = %s",
                     (ids["Pebble Pay"],))  # fmt: skip
    page = served(chromium, client, viewport={"width": 1280, "height": 900})
    page.goto(f"http://site.test/?idea={VENDOR}&view=graph&mode=meaning")
    crown = page.locator(f'.hm-dot[data-graph-id="{ids["Pebble Pay"]}"] .hm-crown')
    mark = page.locator(f'.hm-dot[data-graph-id="{ids["Pebble Pay"]}"] .hm-mark')

    def measured() -> tuple[float, float]:
        top, dot = crown.bounding_box(), mark.bounding_box()
        return top["width"], dot["y"] - (top["y"] + top["height"])  # its width, the gap

    page.locator(".hm-graph-svg").scroll_into_view_if_needed()  # below the box of the idea
    width, gap = measured()
    assert width > 4 and 0 <= gap < 6  # small, and just above its dot
    box = page.locator(".hm-graph-svg").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.keyboard.down("Control")
    page.mouse.wheel(0, -400)
    page.keyboard.up("Control")
    page.wait_for_selector(".hm-graph-svg.is-zoomed")
    zoomed_width, zoomed_gap = measured()
    assert abs(zoomed_width - width) < 1.5 and abs(zoomed_gap - gap) < 1.5
    page.context.close()


@pytest.mark.browser
def test_right_clicks_keep_dots_lit_and_each_empty_click_lets_the_latest_go(site, chromium) -> None:  # noqa: ANN001
    """A right click keeps a dot lit with its closest project and their line, for as many dots as
    one likes, in the order of the clicks; a right click on it again lets it go, and each click on
    an empty place lets go of the latest dot kept, by a click or by a right click (30 October
    2026: a click on an empty place let them all go at once)."""
    client, _, ids, database = site
    with psycopg.connect(database) as conn:
        (event,) = conn.execute("SELECT id FROM events LIMIT 1").fetchone()
    page = served(chromium, client, viewport={"width": 1280, "height": 900})
    page.goto(f"http://site.test/?event={event}&view=graph")
    page.evaluate("document.addEventListener('contextmenu', (e) => { window.hmMenu = "
                  "e.defaultPrevented; })")  # fmt: skip
    pebble = page.locator(f'.hm-dot[data-graph-id="{ids["Pebble Pay"]}"]')
    fern = page.locator(f'.hm-dot[data-graph-id="{ids["Fern Vote"]}"]')
    pebble.click(button="right")
    assert page.evaluate("window.hmMenu") is True  # the browser's menu does not open on a dot
    fern.click(button="right")
    lines = page.locator(".hm-graph-pins line")
    assert lines.count() == 2
    assert page.locator("[data-graph]").get_attribute("data-pinned") == (
        f"{ids['Pebble Pay']} {ids['Fern Vote']}")  # fmt: skip
    assert "is-pinned" in (pebble.get_attribute("class") or "")
    assert page.locator("#viewer[open]").count() == 0  # a right click opens no card
    pebble.click(button="right")  # again: it lets go
    assert lines.count() == 1 and "is-pinned " not in (pebble.get_attribute("class") or "") + " "
    graph = page.locator("[data-graph]")
    box = page.locator(".hm-graph-svg").bounding_box()

    def empty_click() -> None:
        page.mouse.move(5, 5)
        page.mouse.click(box["x"] + 3, box["y"] + 3)

    cedar = page.locator(f'.hm-dot[data-graph-id="{ids["Cedar Post"]}"]')
    pebble.click(button="right")
    cedar.click(button="right")
    order = [ids[name] for name in ("Fern Vote", "Pebble Pay", "Cedar Post")]
    assert graph.get_attribute("data-pinned") == " ".join(map(str, order))
    empty_click()  # the latest only
    assert graph.get_attribute("data-pinned") == f"{ids['Fern Vote']} {ids['Pebble Pay']}"
    assert lines.count() == 2
    fern.click()  # a click keeps a dot too, and opens its card
    page.wait_for_selector("#viewer[open]")
    page.keyboard.press("Escape")
    page.wait_for_function("!document.getElementById('viewer').open")
    assert graph.get_attribute("data-kept") == str(ids["Fern Vote"])
    empty_click()  # the kept dot is the latest
    assert graph.get_attribute("data-kept") is None and lines.count() == 2
    empty_click()
    empty_click()
    assert lines.count() == 0 and page.locator(".is-pinned, .is-pinned-near").count() == 0
    empty_click()  # nothing is left: nothing happens
    page.context.close()


def test_a_dot_of_the_graph_shows_its_project_and_opens_its_card(site, chromium) -> None:  # noqa: ANN001
    client, _, ids, database = site
    with psycopg.connect(database) as conn:
        (event,) = conn.execute("SELECT id FROM events LIMIT 1").fetchone()
    page = served(chromium, client, viewport={"width": 1280, "height": 900})
    page.goto(f"http://site.test/?event={event}&view=graph")
    dot = page.locator(f'.hm-dot[data-graph-id="{ids["Pebble Pay"]}"]')
    dot.hover()
    tip = page.locator(".hm-graph-tip")
    assert tip.is_visible() and tip.locator(".hm-tip-name").inner_text() == "Pebble Pay"
    titles = [title.strip() for title in tip.locator(".hm-tip-label").all_inner_texts()]
    assert titles == ["Proof:", "Group:", "Closest in meaning:"]
    looks = page.evaluate("""() => {
      const label = document.querySelector('.hm-graph-tip .hm-tip-label');
      const value = label.parentElement;
      return [getComputedStyle(label).color, getComputedStyle(value).color,
              getComputedStyle(label).fontWeight];
    }""")
    assert looks[0] != looks[1] and int(looks[2]) >= 600  # the title stands out from its value
    dot.click()
    page.wait_for_selector("#viewer[open] .project[data-project]")
    assert page.locator("#viewer-body .project").get_attribute("data-project") == str(
        ids["Pebble Pay"])  # fmt: skip
    assert f"open={ids['Pebble Pay']}" in page.url
    # The click kept the dashed line to its closest project, after the card closes, until a
    # click on an empty place of the graph (24 October 2026).
    page.keyboard.press("Escape")
    page.wait_for_selector("#viewer:not([open])", state="attached")
    page.mouse.move(5, 5)
    kept = page.locator(".hm-graph-kept")
    assert "is-kept" in (dot.get_attribute("class") or "")
    assert kept.get_attribute("visibility") == "visible"
    # Another dot shows its own line while the kept one stays (24 October 2026, evening).
    page.locator(f'.hm-dot[data-graph-id="{ids["Fern Vote"]}"]').hover()
    assert page.locator(".hm-graph-hover").get_attribute("visibility") == "visible"
    assert kept.get_attribute("visibility") == "visible"
    assert "is-kept" in (dot.get_attribute("class") or "")
    page.mouse.move(5, 5)
    box = page.locator(".hm-graph-svg").bounding_box()
    page.mouse.click(box["x"] + 3, box["y"] + 3)
    assert kept.get_attribute("visibility") == "hidden"
    assert "is-kept" not in (dot.get_attribute("class") or "")


@pytest.mark.browser
def test_the_graph_zooms_with_ctrl_and_the_wheel(site, chromium) -> None:  # noqa: ANN001
    client, _, ids, database = site
    with psycopg.connect(database) as conn:
        (event,) = conn.execute("SELECT id FROM events LIMIT 1").fetchone()
    page = served(chromium, client, viewport={"width": 1280, "height": 900})
    page.goto(f"http://site.test/?event={event}&view=graph")
    svg = page.locator(".hm-graph-svg")
    start = [float(n) for n in svg.get_attribute("viewBox").split()]
    # The picture takes the whole width of its card, so a zoom fills the card (24 October 2026:
    # it was a window in its middle).
    wide = page.evaluate("[document.querySelector('.hm-graph-svg').getBoundingClientRect().width,"
                         " document.querySelector('.hm-graph').clientWidth]")  # fmt: skip
    assert wide[0] >= 0.9 * wide[1]
    mark = page.locator(f'.hm-dot[data-graph-id="{ids["Pebble Pay"]}"] .hm-mark')
    size = mark.bounding_box()["width"]
    box = svg.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    scrolled = page.evaluate("window.scrollY")
    page.keyboard.down("Control")
    page.mouse.wheel(0, -400)
    page.keyboard.up("Control")
    page.wait_for_selector(".hm-graph-svg.is-zoomed")
    zoomed = [float(n) for n in svg.get_attribute("viewBox").split()]
    assert zoomed[2] < start[2] and zoomed[3] < start[3]  # a smaller part of the graph
    assert abs(mark.bounding_box()["width"] - size) < 1.5  # a dot keeps its size on the screen
    assert page.evaluate("window.scrollY") == scrolled  # the graph zoomed, not the page
    assert page.locator("[data-zoom=reset]").is_enabled()
    zoomed = svg.get_attribute("viewBox")
    page.mouse.wheel(0, 120)  # two fingers on a touchpad send the wheel, with no Ctrl
    page.wait_for_timeout(100)
    assert svg.get_attribute("viewBox") != zoomed and page.evaluate("window.scrollY") == scrolled
    page.locator("[data-zoom=reset]").click()
    assert [float(n) for n in svg.get_attribute("viewBox").split()] == start
    box = svg.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, 120)  # not zoomed: the wheel is the page's
    page.wait_for_timeout(100)
    assert [float(n) for n in svg.get_attribute("viewBox").split()] == start
    page.locator("[data-zoom=in]").click()
    assert float(svg.get_attribute("viewBox").split()[2]) < start[2]
    page.locator(".hm-graph-name").first.hover()  # a link of the picture is never underlined
    assert page.evaluate("getComputedStyle(document.querySelector('.hm-graph-name'))"
                         ".textDecorationLine") == "none"  # fmt: skip


@pytest.mark.browser
def test_a_long_list_shows_ten_lines_and_buttons_for_more(site, chromium) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1280, "height": 900})
    page.goto("http://site.test/")
    page.evaluate("""() => {
      const list = document.createElement('ol');
      list.id = 'long-list';
      for (let i = 1; i <= 25; i++) list.insertAdjacentHTML('beforeend', '<li>Line ' + i + '</li>');
      const place = document.createElement('div');
      place.className = 'hm-more';
      place.dataset.moreFor = 'long-list';
      place.hidden = true;
      document.getElementById('results').append(list, place);
      const settled = {detail: {target: document.body}};
      document.dispatchEvent(new CustomEvent('htmx:afterSettle', settled));
    }""")
    lines = page.locator("#long-list li")
    shown = "() => [...document.querySelectorAll('#long-list li')].filter(l => !l.hidden).length"
    assert lines.count() == 25 and page.evaluate(shown) == 10
    page.get_by_role("button", name="Show 10 more").click()
    assert page.evaluate(shown) == 20
    page.get_by_role("button", name="Show the last 5").click()
    assert page.evaluate(shown) == 25
    page.get_by_role("button", name="Show fewer").click()
    assert page.evaluate(shown) == 10
    page.get_by_role("button", name="Show all 25").click()
    assert page.evaluate(shown) == 25


@pytest.mark.browser
@pytest.mark.parametrize("motion", ["no-preference", "reduce"])
def test_a_mark_lights_the_part_it_leads_to(site, chromium, motion) -> None:  # noqa: ANN001
    """A ring shows the part, also when the computer asks for less motion: there the light was
    an outline, which the rule of no focus frame took away (24 October 2026). The ring is read
    the moment the part is lit, which lasts 2 seconds: a fixed wait read it too early or too late
    when the computer was busy (30 October 2026)."""
    client, _, ids, _ = site
    pebble = ids["Pebble Pay"]
    page = served(chromium, client, viewport={"width": 1440, "height": 900}, reduced_motion=motion)
    page.goto(f"http://site.test/?open={pebble}")
    page.wait_for_selector("#viewer[open] .project[data-project]")
    watch = """(id) => {
      window.hmRing = null;
      const part = document.getElementById(id);
      new MutationObserver(() => {
        if (window.hmRing === null && part.classList.contains('is-pointed')) {
          window.hmRing = getComputedStyle(part).boxShadow;
        }
      }).observe(part, { attributes: true, attributeFilter: ['class'] });
    }"""
    page.evaluate(watch, f"ledger-{pebble}")  # the ring, read the moment the part is lit
    page.locator("#viewer .project-marks .hm-mark-link").first.click()
    page.wait_for_function("window.hmRing !== null", timeout=10000)
    assert "0px 0px 0px 2px" in page.evaluate("window.hmRing")
    page.context.close()


@pytest.mark.browser
def test_the_eight_filters_stand_in_one_row(site, chromium) -> None:  # noqa: ANN001
    """The prize had wrapped to a second row (24 October 2026); the organiser came as a seventh
    filter, with the year and the activity in narrower columns (30 October 2026), and the main
    network as an eighth, narrow too (31 October 2026). One row also when "Clear filters" takes its
    place at the end."""
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1280, "height": 900})
    for address in ("http://site.test/", "http://site.test/?organiser=ETHGlobal"):
        page.goto(address)
        tops = page.evaluate("[...document.querySelectorAll('.hm-filter')]"
                             ".map(f => Math.round(f.getBoundingClientRect().top))")  # fmt: skip
        assert len(tops) == 8 and len(set(tops)) == 1, address
        # the text shown in each select, measured against its room: a select's own cut-off is
        # not seen by its scrollWidth ("All years" showed as "Al..." with the button there)
        fits = page.evaluate("""[...document.querySelectorAll('.hm-filter select')].map(s => {
          const style = getComputedStyle(s);
          const pen = document.createElement('canvas').getContext('2d');
          pen.font = style.font;
          const room = s.clientWidth - parseFloat(style.paddingLeft)
            - parseFloat(style.paddingRight);
          return pen.measureText(s.options[s.selectedIndex].text).width <= room;
        })""")
        # every value shown whole here: the words of "all" and the short choices (a long name of
        # an event may show its start, by design); the arrow's room was cut (31 October 2026)
        assert all(fits), (address, fits)
    assert page.locator(".hm-clear-filters").count() == 1


@pytest.mark.browser
def test_a_long_text_of_an_i_stays_on_the_screen_and_scrolls(site, chromium) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1280, "height": 420})
    page.goto("http://site.test/")
    page.wait_for_timeout(1600)  # the first screen of the visit has gone
    page.locator(".hm-filter .info[data-tip='tip-proof']").click()
    page.wait_for_selector("#tip-proof:popover-open")
    box = page.locator("#tip-proof").bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= 420  # whole on the screen
    tall = "(t => t.scrollHeight > t.clientHeight)(document.getElementById('tip-proof'))"
    assert page.evaluate(tall)  # it scrolls inside itself


@pytest.mark.browser
def test_the_graph_stays_while_the_idea_changes_and_after_clear(site, chromium) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1280, "height": 900})
    page.goto("http://site.test/?view=graph")
    page.wait_for_timeout(1600)  # the first screen of the visit has gone
    page.locator('label[for="mode-meaning"]').click()
    page.locator("#idea").fill(VENDOR)
    page.wait_for_function("new URL(location.href).searchParams.get('idea')")
    page.wait_for_selector(".hm-graph-idea")  # the graph of the search, around the idea
    assert "view=graph" in page.url
    page.locator("[data-clear-search]").click()
    page.wait_for_function("!new URL(location.href).searchParams.get('idea')")
    assert "view=graph" in page.url and page.locator(".hm-graph-svg").count() == 1


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


def test_each_id_says_why_it_counts_in_plain_words() -> None:
    from hackathon_memory.search.listing import LedgerLine
    from hackathon_memory.web.data import reason_of, window_of

    window = window_of(datetime(2026, 3, 6, tzinfo=UTC), date(2026, 3, 8))
    made = datetime(2026, 3, 7, tzinfo=UTC)
    found = LedgerLine("0.0.5", "readme", "testnet", "proof_found", "topic", made, None, made)
    assert reason_of(found, window) == "made inside the window"
    other = LedgerLine("0.0.5", "readme", "mainnet", "another_kind", "account", made, None, made,
                       said_kind="contract")  # fmt: skip
    assert reason_of(other, window) == (
        "the README calls it a contract, but the ledger knows it as an account"
    )


def test_a_network_that_does_not_know_an_id_is_left_out_when_the_other_knows_it() -> None:
    """An ID named with no network is asked on both networks; the card does not say "Not found"
    beside the proof of the same ID (28 October 2026)."""
    from hackathon_memory.search.listing import LedgerLine
    from hackathon_memory.web.data import lines_to_show

    made = datetime(2026, 9, 8, tzinfo=UTC)
    deal = "0.0.7-1788884980-415990532"
    main = LedgerLine(deal, "readme", "mainnet", "not_found", None, None, None, made)
    test = LedgerLine(deal, "readme", "testnet", "proof_found", "transaction", made, None, made)
    assert lines_to_show([main, test]) == [test]
    # the page names the main network: what that network says stays, beside the other row
    said = LedgerLine("0.0.8", "page", "mainnet", "not_found", None, None, None, made,
                      named_network="mainnet")  # fmt: skip
    elsewhere = LedgerLine("0.0.8", "readme", "testnet", "proof_found", "topic", made, None, made)
    # known by no network: both answers stay; not asked yet: no line
    nowhere = [LedgerLine("0.0.9", "readme", network, "not_found", None, None, None, made)
               for network in ("mainnet", "testnet")]  # fmt: skip
    waiting = LedgerLine("0.0.10", "readme", None, None, None, None, None, None)
    assert lines_to_show([said, elsewhere, *nowhere, waiting]) == [said, elsewhere, *nowhere]


def test_a_card_with_nothing_to_read_again_has_no_block_of_the_readings(site) -> None:  # noqa: ANN001
    """A winners' list entry has no repository and no Hedera ID: nothing to read again, so no
    block and no "Read again now" (28 October 2026)."""
    client, _, ids, database = site
    fern = ids["Fern Vote"]
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET entry_kind = 'winner_entry', repository_id = NULL "
                     "WHERE id = %s", (fern,))  # fmt: skip
        conn.execute("DELETE FROM hedera_ids WHERE project_id = %s", (fern,))
    panel = client.get(f"/project/{fern}/panel").text
    assert f'id="read-{fern}"' not in panel and "Read again now" not in panel
    assert '<header class="project-head">' in panel
    checkable(database)  # Pebble Pay keeps the code of REPO: it has something to read again
    pebble = client.get(f"/project/{ids['Pebble Pay']}/panel").text
    assert "Read again now" in pebble and 'class="project-head has-readings"' in pebble


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
        "Fetched from GitHub: the repository details and the README (README.md) on 16 October "
        "2026, the latest commit on 18 October 2026."
    )
    assert github_reads(code, SimpleNamespace(status="none"), None) == (
        "Fetched from GitHub on 16 October 2026: the repository details."
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


SEARCH = "http://site.test/?idea=help+a+street+vendor+get+paid+with+a+coin&mode=meaning"


def served(chromium, client, before_compare=lambda: None, tour_offer=False, **context):  # noqa: ANN001, ANN201
    """A page whose every request is answered by the website's test client: no server runs.

    The visit counts as seen, so the name of the tool never covers its first page: a test that
    pointed or clicked within its 1.45 seconds made Playwright scroll to try again while the page
    scrolls smoothly, and the pointer landed elsewhere (30 October 2026, after a restart of the
    computer made the race lose every time). The tour counts as seen too, so its offer stands in
    no corner, unless the test is about it (`tour_offer`)."""
    page = chromium.new_context(**context).new_page()
    page.add_init_script("try { window.sessionStorage.setItem('hm-seen', '1'); } catch (e) {}")
    if not tour_offer:
        page.add_init_script("try { window.localStorage.setItem('hm-tour', 'seen'); } catch (e) {}")

    def answer(route) -> None:  # noqa: ANN001
        parts = urlsplit(route.request.url)
        if parts.path == "/compare":
            before_compare()
        headers = {k: v for k, v in route.request.headers.items() if k.lower().startswith("hx-")}
        address = parts.path + (f"?{parts.query}" if parts.query else "")
        if route.request.method == "POST":  # a form: the register's, or a token of Turnstile
            headers["content-type"] = route.request.headers.get("content-type", "")
            got = client.post(address, content=route.request.post_data_buffer, headers=headers)
        else:
            got = client.get(address, headers=headers)
        # the headers that htmx reads, such as HX-Retarget, go with the answer as from a server
        back = {k: v for k, v in got.headers.items() if k.lower().startswith("hx-")}
        kind = got.headers.get("content-type")  # an answer of 204 has none
        if kind:
            back["content-type"] = kind
        route.fulfill(status=got.status_code, body=got.content, headers=back)

    page.route(lambda url: url.startswith("http://site.test/"), answer)
    return page


@pytest.mark.browser
def test_a_comparison_in_the_window_shows_on_its_card_at_once(site, chromium) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    pebble = ids["Pebble Pay"]
    fake.answer_text = compare_answer((1, ["what_it_does"]))
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto(SEARCH)
    assert page.locator(f"#result-{pebble} .hm-compare").count() == 0
    page.locator(f"#result-{pebble} .result-link").click()
    page.locator(f"#one-compare-{pebble} button").click()
    page.wait_for_selector(f"#one-compare-{pebble} .hm-compare-text")
    page.wait_for_selector(f"#result-{pebble} .hm-compare-text")  # the card, behind the window
    assert "Same 1." in page.locator(f"#result-{pebble} .hm-compare").inner_text()
    page.context.close()


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
    assert "No comparison for this project." in results.nth(2).inner_text()
    page.context.close()


@pytest.mark.browser
def test_the_button_of_gemini_moves_the_form_to_the_semantic_search(site, chromium) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    fake.answer_queue = [json.dumps({"closest": [1, 2, 3]})]
    fake.answer_text = compare_answer((1, ["what_it_does"]))
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto(SEARCH.replace("mode=meaning", "mode=words"))
    assert page.locator("#mode-words").is_checked()
    page.locator("#ai-button").click()
    page.wait_for_selector("#results-title:has-text('Sorted by Gemini')")
    page.wait_for_function("document.getElementById('mode-meaning').checked")  # what was searched
    page.context.close()


@pytest.mark.browser
def test_a_failed_comparison_says_so_and_the_results_stay(site, chromium) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    fake.answer_queue = [json.dumps({"closest": [1, 2, 3]})]
    page = served(chromium, client, lambda: setattr(fake, "fail_with", (503, "unavailable")))
    page.goto(SEARCH + "&ai=1")
    page.wait_for_function("!document.querySelector('.compare.waiting')")
    texts = page.locator(".compare").all_inner_texts()
    assert len(texts) == 3 and all("could not be generated just now" in text for text in texts)
    assert page.locator("li.result .result-link").count() == 3  # the results stay
    page.context.close()


@pytest.mark.browser
def test_a_click_that_replaces_the_page_does_not_move_it(site, chromium) -> None:  # noqa: ANN001
    """A clicked link keeps the focus, and the browser's scroll anchoring followed it down while
    htmx put the new page above the old one: "Clear" and an example sent the page to the bottom
    (23 October 2026)."""
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 700, "height": 500})
    page.goto(SEARCH)
    page.wait_for_selector("li.result")
    page.evaluate(
        "document.addEventListener('mousedown', () => { window.hmAt = scrollY; }, true);"
        "document.addEventListener('htmx:afterSettle', () => { window.hmDone = true; })"
    )
    for link in ("[data-clear-search]", "p.try a"):
        page.evaluate("window.hmDone = false")
        page.locator(link).first.click()
        page.wait_for_function("window.hmDone")
        assert page.evaluate("Math.round(scrollY) === Math.round(window.hmAt)"), link
    page.context.close()


@pytest.mark.browser
def test_quick_results_come_while_typing_and_ask_no_model(site, chromium) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto("http://site.test/")
    assert page.locator("#mode-words").is_checked()  # the page opens on Keyword
    page.locator('label[for="mode-meaning"]').click()
    before = len(fake.requests)
    page.locator("#idea").fill(VENDOR)
    page.wait_for_function("new URL(location.href).searchParams.get('idea')")
    page.wait_for_selector("#results-title:has-text('Results')")
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
def test_a_word_of_the_page_marks_each_place_where_the_page_says_it(site, chromium) -> None:  # noqa: ANN001
    """The words of the page in the ledger story are buttons (design 7.5): a press marks every
    place where the page's texts say the word and brings the first into view; the next press, or
    a press on a marked place, goes on to the next one."""
    from hackathon_memory.check.history import CONSENSUS, History
    from hackathon_memory.db.history import HistoryStore

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    own_id(database, pebble, "0.0.4511", "topic")
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE events SET ends_on = %s", (date(2026, 3, 8),))
        conn.execute("UPDATE projects SET short_line = %s WHERE id = %s",
                     ("Paid with HTS, and HTS again.", pebble))  # fmt: skip
    message = {stamp(datetime(2026, 3, 7, 12, tzinfo=UTC), 1): CONSENSUS}
    HistoryStore(database).save("0.0.4511", "testnet", "topic", History(message, False),
                                datetime(2026, 10, 23, tzinfo=UTC))  # fmt: skip
    page = served(chromium, client, viewport={"width": 1440, "height": 900},
                  reduced_motion="reduce")  # fmt: skip
    page.goto(f"http://site.test/project/{pebble}")
    word = page.locator(".hm-story [data-said-word='hts']")
    marks = page.locator("mark.hm-said[data-word='hts']")
    status = page.locator(".hm-said-status")
    assert marks.count() == 2 and "is-shown" not in (marks.nth(0).get_attribute("class") or "")
    word.click()
    assert "is-current" in marks.nth(0).get_attribute("class")
    assert "is-shown" in marks.nth(1).get_attribute("class")
    assert "place 1 of 2" in status.inner_text()
    word.click()
    assert "is-current" in marks.nth(1).get_attribute("class")
    assert "place 2 of 2" in status.inner_text()
    marks.nth(1).click()  # a marked place goes on to the next one, here back to the first
    assert "is-current" in marks.nth(0).get_attribute("class")
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


def test_every_page_has_the_switch_of_the_theme(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    for address in ("/", f"/project/{ids['Pebble Pay']}", "/about/how"):
        page = client.get(address).text
        assert "data-theme-switch hidden" in page  # shown by the script that makes it work
        for value in ("light", "dark", "auto"):
            assert f'name="hm-theme" value="{value}"' in page


@pytest.mark.browser
def test_the_theme_switch_holds_its_choice_and_redraws_the_charts(site, chromium) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900}, color_scheme="light",
                  reduced_motion="reduce")  # fmt: skip
    theme = "document.documentElement.getAttribute('data-bs-theme')"
    chart = "Chart.getChart(document.querySelector('canvas[data-chart]'))"
    colour = f"{chart}.data.datasets[0].backgroundColor"
    page.goto("http://site.test/?view=charts")
    page.wait_for_function(f"window.Chart && {chart}")
    assert page.evaluate(theme) == "light" and page.locator("#theme-auto").is_checked()
    light = page.evaluate(colour)
    page.locator("label[for='theme-dark']").click()
    assert page.evaluate(theme) == "dark" and page.evaluate(colour) != light  # drawn again
    page.reload()
    assert page.evaluate(theme) == "dark" and page.locator("#theme-dark").is_checked()
    page.locator("label[for='theme-auto']").click()
    assert page.evaluate(theme) == "light"  # the computer's
    assert page.evaluate("localStorage.getItem('hm-theme')") is None
    page.context.close()


@pytest.mark.browser
def test_the_tabs_of_the_insights_show_one_part_at_a_time(site, chromium) -> None:  # noqa: ANN001
    """One part shows at a time, the arrow keys move between the tabs, a chart is drawn when its
    tab is shown, and the tab chosen stays for the visit."""
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900},
                  reduced_motion="reduce")  # fmt: skip
    page.goto("http://site.test/?view=charts")
    page.wait_for_selector("#tab-overview[aria-selected='true']")
    assert page.locator("#panel-overview").is_visible()
    assert page.locator("#panel-events").is_hidden()
    page.locator("#tab-events").click()
    assert page.locator("#panel-events").is_visible()
    assert page.locator("#panel-overview").is_hidden()
    drawn = "Chart.getChart(document.querySelector('#panel-events canvas[data-chart]'))"
    page.wait_for_function(f"{drawn} && {drawn}.width > 0")
    assert page.evaluate(f"{drawn}.data.datasets.every(d => d.maxBarThickness === 20)")
    page.keyboard.press("ArrowLeft")
    assert page.evaluate("document.activeElement.id") == "tab-winners"
    assert page.locator("#panel-winners").is_visible() and page.locator("#panel-events").is_hidden()
    page.reload()
    page.wait_for_selector("#tab-winners[aria-selected='true']")
    assert page.locator("#panel-winners").is_visible()
    page.context.close()


@pytest.mark.browser
def test_the_window_how_it_works_gives_its_table_the_whole_width(site, chromium) -> None:  # noqa: ANN001
    """The numbers of its table were squeezed into the width of a line of text (seen on 18
    October 2026); the lines of text keep that width, the table takes the whole window."""
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900},
                  reduced_motion="reduce")  # fmt: skip
    page.goto("http://site.test/")
    page.locator("[data-sheet='how']").click()
    page.wait_for_selector("#sheet[open] .table-wrap table")
    sheet = page.locator("#sheet").bounding_box()
    table = page.locator("#sheet .table-wrap table").bounding_box()
    line = page.locator("#sheet .about-lede").bounding_box()
    assert sheet and table and line
    assert sheet["width"] >= 1000 and table["width"] > line["width"] + 100
    steps = "getComputedStyle(document.querySelector('#sheet .about ol')).listStyleType"
    assert page.evaluate(steps) == "decimal"  # the text refers to "step 1"
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
def test_a_number_of_the_table_opens_its_note_like_an_info_mark(site, chromium) -> None:  # noqa: ANN001
    """The number of a service opens what it holds as an (i) opens its text: on pointing, and
    with the keyboard. The note stays in the window of the card, where a shared text moves, and
    axe finds nothing (3 November 2026)."""
    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    a_card_with_days(database, pebble)  # an own topic with two messages on 7 March 2026
    note = f"#held-{pebble}-consensus"
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto(f"http://site.test/?open={pebble}")
    number = page.locator("#viewer .story-section .hm-count")
    number.hover()
    page.wait_for_selector(f"{note}:popover-open")
    assert page.locator(note).inner_text() == "2 messages to a topic."
    assert page.locator(f"#viewer {note}").count() == 1  # in the window, not moved out of it
    wraps = page.locator(note).evaluate("n => getComputedStyle(n).whiteSpace")
    assert wraps == "normal"  # a long note wraps: its cell keeps a number on one line
    page.mouse.move(4, 4)
    page.wait_for_selector(f"{note}:not(:popover-open)", state="attached")
    number.focus()
    page.keyboard.press("Enter")
    page.wait_for_selector(f"{note}:popover-open")
    assert problems(page) == []
    page.keyboard.press("Escape")
    page.wait_for_selector(f"{note}:not(:popover-open)", state="attached")
    page.context.close()


STRIP_STATE = """() => {
  const days = document.querySelector('[data-strip] .hm-strip-svg');
  const names = document.querySelector('[data-strip] .hm-strip-names').getBoundingClientRect();
  const box = days.getBoundingClientRect();
  return {zoom: Number(days.getAttribute('data-zoom') || 1), width: box.width,
          height: box.height, namesHeight: names.height,
          font: getComputedStyle(days.querySelector('.hm-strip-mark')).fontSize,
          ticks: days.querySelector('.hm-strip-ticks').getAttribute('display') === 'none' ? 0
            : days.querySelectorAll('.hm-strip-ticks text[display="inline"]').length,
          narrower: !document.querySelector('[data-strip] [data-zoom="out"]').disabled,
          wider: !document.querySelector('[data-strip] [data-zoom="in"]').disabled};
}"""


@pytest.mark.browser
def test_the_days_of_the_strip_widen_and_their_words_keep_their_size(site, chromium) -> None:  # noqa: ANN001
    """+ and -, and Ctrl with the mouse wheel over the strip, widen and narrow its days; the
    names stay in line with the days, the words keep their size, and dates come under the days
    (design 12.1, S2, 28 October 2026)."""
    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    a_card_with_days(database, pebble)
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto(f"http://site.test/project/{pebble}")
    strip = page.locator("[data-strip]")
    first = page.evaluate(STRIP_STATE)
    assert first["zoom"] == 1 and not first["narrower"] and first["wider"] and first["ticks"] == 0
    assert abs(first["height"] - first["namesHeight"]) < 1  # the rows of the names and the days
    strip.locator('[data-zoom="in"]').click()
    wider = page.evaluate(STRIP_STATE)
    assert wider["zoom"] == 2 and abs(wider["width"] - 2 * first["width"]) < 1
    assert (wider["height"], wider["font"]) == (first["height"], first["font"])
    assert wider["narrower"] and wider["ticks"] > 0
    box = strip.locator(".hm-strip-scroll").bounding_box()
    page.mouse.move(box["x"] + 40, box["y"] + 10)
    page.keyboard.down("Control")
    page.mouse.wheel(0, -300)  # up, with Ctrl: wider, as a pinch of a touchpad would
    page.keyboard.up("Control")
    page.wait_for_function("Number(document.querySelector('[data-strip] .hm-strip-svg')"
                           ".getAttribute('data-zoom')) > 2")  # fmt: skip
    assert page.evaluate("() => window.devicePixelRatio") == 1  # the page itself did not zoom
    # a pinch of a touchpad over the strip, as Chrome sends it: the days follow the fingers
    before = page.evaluate(STRIP_STATE)["zoom"]
    page.context.new_cdp_session(page).send(
        "Input.synthesizePinchGesture",
        {"x": box["x"] + 40, "y": box["y"] + 10, "scaleFactor": 1.5, "gestureSourceType": "mouse"},
    )
    page.wait_for_function("Number(document.querySelector('[data-strip] .hm-strip-svg')"
                           f".getAttribute('data-zoom')) > {before} * 1.4")  # fmt: skip
    assert page.evaluate("() => window.devicePixelRatio") == 1
    for _ in range(8):
        if strip.locator('[data-zoom="out"]').is_enabled():
            strip.locator('[data-zoom="out"]').click()
    back = page.evaluate(STRIP_STATE)
    assert back["zoom"] == 1 and abs(back["width"] - first["width"]) < 1 and back["ticks"] == 0
    assert problems(page) == []
    page.context.close()


@pytest.mark.browser
def test_the_table_of_the_services_stays_inside_a_narrow_card(site, chromium) -> None:  # noqa: ANN001
    """The words of the table stay whole and the table stays inside its card, in the window over
    the results of a narrow screen (28 October 2026: "Consen sus", and a table past the border)."""
    from hackathon_memory.check.story import time_of

    client, _, ids, database = site
    pebble = ids["Pebble Pay"]
    a_card_with_days(database, pebble)  # an own topic, with messages during the event
    escrow = "0.0.4516"
    own_id(database, pebble, escrow, "contract")
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET short_line = %s WHERE id = %s",
                     ("Each sale goes to the Hedera Consensus Service, and the Hedera Token "
                      "Service mints its receipts from Solidity.", pebble))  # fmt: skip
        (starts_at,) = conn.execute("SELECT starts_at FROM events").fetchone()
        span = time_of(starts_at, date(2026, 3, 8))
        conn.execute("INSERT INTO contract_calls (entity_id, network, starts_at, ends_at, read, "
                     "cut, reached, asked_at) VALUES (%s, 'testnet', %s, %s, 40, false, %s, %s)",
                     (escrow, *span, json.dumps({"0.0.359": 28}),
                      datetime(2026, 10, 28, tzinfo=UTC)))  # fmt: skip
    page = served(chromium, client, viewport={"width": 1024, "height": 800})
    page.goto(f"http://site.test/?open={pebble}")
    page.wait_for_selector("#viewer .story-section table.hm-story")
    measured = page.evaluate("""() => {
      const body = document.querySelector('#viewer .story-section .card-body');
      const style = getComputedStyle(body);
      const sides = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
      const inner = body.clientWidth - sides;
      const table = body.querySelector('table.hm-story');
      const first = table.querySelector('tbody th');
      const probe = document.createElement('span');
      probe.textContent = 'Consensus';
      first.appendChild(probe);
      const word = probe.getBoundingClientRect().width;
      probe.remove();
      return {inner, table: table.getBoundingClientRect().width,
              first: first.clientWidth - 6, word,
              note: !!table.querySelector('.hm-from-contracts')};
    }""")
    assert measured["note"]  # the calls of its contract, in the row of the Token Service
    assert measured["table"] <= measured["inner"] + 1  # inside its card
    assert measured["first"] >= measured["word"]  # "Consensus" stays whole
    assert problems(page) == []
    page.context.close()


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


@pytest.mark.browser
def test_a_view_alone_does_not_come_back_but_a_filter_does(site, chromium) -> None:  # noqa: ANN001
    """With nothing searched, the switch "Mainnet" is not a search: the plain address opens the
    first page, and the memory is forgotten (2 November 2026: the public copy kept going back to
    ?view=mainnet). A filter is a search, and comes back with its view."""
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto("http://site.test/")
    page.locator('[aria-label="How to show the projects"] a[href*="view=mainnet"]').click()
    page.wait_for_function("new URL(location.href).searchParams.get('view') === 'mainnet'")
    page.goto("http://site.test/")
    assert page.url == "http://site.test/"
    assert page.evaluate("window.localStorage.getItem('hm-last')") is None
    page.evaluate("window.localStorage.setItem('hm-last', 'proof=no_id_given&view=mainnet')")
    page.goto("http://site.test/")
    page.wait_for_function("new URL(location.href).searchParams.get('proof') === 'no_id_given'")
    assert "view=mainnet" in page.url
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
    page.locator(".check-result .hm-close-name a").first.click()  # a project of the check
    page.wait_for_selector("[data-back-to-check]")
    assert problems(page) == []
    page.locator("[data-back-to-check]").click()
    page.wait_for_selector("#viewer[open] .check-result")
    with_line(client, page.content())  # the team adds its line to the README
    page.locator("#register-form button[type=submit]").click()  # the register, with its receipt
    page.wait_for_selector("#register-box .hm-receipt")
    assert problems(page) == []
    page.context.close()


# ----------------------------------------------------------- a team signs its own record (9.6)

COMMIT = "7260ea7290637399c6ac181ed893a567144d96eb"  # the latest commit of the stand-in GitHub


def signing_account(client) -> tuple[object, str, str]:  # noqa: ANN001
    """An ECDSA account of the test network, as the stand-in mirror node gives it by its ID and by
    its 0x address: the key that signs, the account and the address."""
    from hiero_sdk_python.crypto.private_key import PrivateKey

    key = PrivateKey.generate_ecdsa()
    address = "0x" + key.public_key().to_evm_address().to_string().removeprefix("0x").lower()
    answer = {
        "account": "0.0.7001",
        "evm_address": address,
        "deleted": False,
        "key": {"_type": "ECDSA_SECP256K1", "key": key.public_key().to_bytes_raw().hex()},
    }
    accounts = client.mirrors["testnet"].things.setdefault("account", {})
    accounts["0.0.7001"] = accounts[address] = answer
    return key, "0.0.7001", address


def metamask_signature(key, event_key: str, commit: str = COMMIT) -> str:  # noqa: ANN001
    """What MetaMask's personal_sign answers: r, s, and the v with which its address is found."""
    import hashlib

    from hackathon_memory.hedera.signing import ethereum_message, signed_text, signer_address

    text = signed_text(event_key, hashlib.sha256(REPO.encode()).hexdigest(), commit, "0.0.7001")
    raw = key.sign(ethereum_message(text))
    address = "0x" + key.public_key().to_evm_address().to_string().removeprefix("0x").lower()
    v = next(v for v in (27, 28)
             if signer_address(ethereum_message(text), raw + bytes([v])) == address)  # fmt: skip
    return "0x" + (raw + bytes([v])).hex()


def test_a_team_signs_its_registration_and_the_record_holds_the_signature(site) -> None:  # noqa: ANN001
    """The server checks the signature against the key that the ledger shows for the account,
    then writes a record of version 3 (design 9.6, 29 October 2026)."""
    client, _, _, database = site
    event = checkable(database)
    key, account, address = signing_account(client)
    found = client.get("/register/account", params={"address": address})
    assert found.json() == {"account": account, "key": "ECDSA_SECP256K1"}
    assert client.get("/register/account", params={"address": "0x" + "12" * 20}).status_code == 404
    asked = {"repo": REPO, "event": event}
    check = client.get("/check", params=asked, headers=HX)
    assert 'data-sign-with="evm">Sign with an EVM wallet<' in check.text
    assert f'data-commit="{COMMIT}"' in check.text
    # no WalletConnect project ID here: the Hedera wallets wait for it
    assert 'data-sign-with="hedera" disabled>Sign with a Hedera wallet<' in check.text
    assert "HashPack" in check.text and "MetaMask" in check.text  # named as examples of a kind
    with_line(client, check.text)
    form = {**asked, "starts": "", "ends": "", "signer": account, "scheme": "eip191",
            "signed_commit": COMMIT}  # fmt: skip
    other = metamask_signature(type(key).generate_ecdsa(), "ethglobal.com/sample-event")
    wrong = client.post("/register", data={**form, "signature": other}, headers=HX)
    assert wrong.status_code == 400 and "not that of the key of 0.0.7001" in wrong.text
    old = metamask_signature(key, "ethglobal.com/sample-event", "ab" * 20)
    late = client.post("/register", data={**form, "signature": old, "signed_commit": "ab" * 20},
                       headers=HX)  # fmt: skip
    assert late.status_code == 400 and "A new commit reached the repository" in late.text
    assert client.writes.written == []
    good = metamask_signature(key, "ethglobal.com/sample-event")
    done = client.post("/register", data={**form, "signature": good}, headers=HX)
    assert done.status_code == 200 and "<dt>Signed by</dt>" in done.text
    assert "with an EVM wallet." in done.text
    (payload,) = client.writes.written
    record = json.loads(payload)
    assert (record["v"], record["account"], record["scheme"]) == (3, account, "eip191")
    later = client.get("/check", params=asked, headers=HX)
    assert f'signed by the account <span class="id">{account}</span>' in later.text


def test_an_account_made_by_the_faucet_signs_by_its_address(site) -> None:  # noqa: ANN001
    """Test HBAR sent to a 0x address makes an account with no key on the ledger until it pays for
    a first transaction (30 October 2026): its EVM wallet's signature is checked by the address
    that made it, and the record is written."""
    client, _, _, database = site
    event = checkable(database)
    key, account, address = signing_account(client)
    client.mirrors["testnet"].things["account"][account]["key"] = None  # by its ID and its address
    found = client.get("/register/account", params={"address": address})
    assert found.status_code == 200 and found.json()["account"] == account
    asked = {"repo": REPO, "event": event}
    with_line(client, client.get("/check", params=asked, headers=HX).text)
    form = {**asked, "starts": "", "ends": "", "signer": account, "scheme": "eip191",
            "signed_commit": COMMIT}  # fmt: skip
    other = metamask_signature(type(key).generate_ecdsa(), "ethglobal.com/sample-event")
    wrong = client.post("/register", data={**form, "signature": other}, headers=HX)
    assert wrong.status_code == 400 and "not that of the address of 0.0.7001" in wrong.text
    good = metamask_signature(key, "ethglobal.com/sample-event")
    done = client.post("/register", data={**form, "signature": good}, headers=HX)
    assert done.status_code == 200 and "<dt>Signed by</dt>" in done.text
    (payload,) = client.writes.written
    assert json.loads(payload)["account"] == account


def test_the_box_offers_hedera_wallets_once_walletconnect_has_a_project_id(site) -> None:  # noqa: ANN001
    client, _, _, database = site
    event = checkable(database)
    with_id = client.make(walletconnect_project_id="0123456789abcdef0123456789abcdef")
    check = with_id.get("/check", params={"repo": REPO, "event": event}, headers=HX)
    assert 'data-project-id="0123456789abcdef0123456789abcdef"' in check.text
    assert 'data-sign-with="hedera">Sign with a Hedera wallet<' in check.text


@pytest.mark.browser
def test_the_list_of_wallets_opens_inside_the_window(site, chromium) -> None:  # noqa: ANN001
    """WalletConnect adds its list of wallets (wcm-modal) at the end of the page, once, and the list
    listens for "open" from its birth until it leaves the page (@walletconnect/modal-ui 2.7.0).
    Behind the modal window of a check it could not be reached; a first fix moved it into the
    window, which cut its listening, so it never opened (30 October 2026). It is born there."""
    client, _, ids, _ = site
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto(f"http://site.test/?open={ids['Pebble Pay']}")
    page.wait_for_selector("#viewer[open] .project")
    page.evaluate("""() => {
      const listening = new Set();  // the library's ModalCtrl.subscribe, played
      window.openWallets = () => listening.forEach((hear) => hear());
      customElements.define('wcm-modal', class extends HTMLElement {
        constructor() {
          super();
          const hear = () => { this.innerHTML =
            '<div id="wallets" style="position: fixed; inset: 0; z-index: 99">x</div>'; };
          listening.add(hear);
          this.stop = () => listening.delete(hear);
        }
        disconnectedCallback() { this.stop(); }
      });
      document.body.insertAdjacentElement('beforeend', document.createElement('wcm-modal'));
    }""")
    page.evaluate("window.openWallets()")
    page.wait_for_selector("#viewer > wcm-modal #wallets", timeout=5000)
    on_top = page.evaluate("document.elementFromPoint(innerWidth / 2, innerHeight / 2).id")
    assert on_top == "wallets"
    page.locator("#wallets").click(timeout=3000)  # a modal window leaves the page behind inert
    page.context.close()


def check_in_window(page, event: str) -> None:  # noqa: ANN001
    """The check of Pebble Pay for `event`, from the search page, up to the register's box."""
    page.goto("http://site.test/")
    page.fill("#check-repo", "github.com/sample-org/pebble-pay")
    page.select_option("#check-event", event)
    page.locator("#check button[type=submit]").click()
    page.wait_for_selector("#viewer[open] [data-sign]")


def fake_metamask(address: str, signatures: dict[str, str], permissions: bool = True) -> str:
    """A stand-in MetaMask (EIP-1193) for the page: it gives its address, and signs a text with
    the signature made for the commit that the text names. As MetaMask does, it opens its list of
    accounts (wallet_requestPermissions) and lets a site go (wallet_revokePermissions), unless
    `permissions` is False. Each call is kept in window.ethereum.asked; a method that it does not
    know is refused as one that does not exist."""
    known = ["wallet_requestPermissions", "wallet_revokePermissions"] if permissions else []
    return f"""window.ethereum = {{ isMetaMask: true, asked: [], async request(call) {{
      this.asked.push(call);
      const asks = call.method === "eth_requestAccounts" || call.method === "eth_accounts";
      if (asks) return ["{address}"];
      if ({json.dumps(known)}.includes(call.method)) return null;
      if (call.method === "personal_sign") {{
        const text = new TextDecoder().decode(new Uint8Array(
          call.params[0].slice(2).match(/../g).map((pair) => parseInt(pair, 16))));
        const signatures = {json.dumps(signatures)};
        for (const [commit, signature] of Object.entries(signatures)) {{
          if (text.includes(commit)) return signature;
        }}
      }}
      throw Object.assign(new Error("not known to this stand-in"), {{ code: -32601 }});
    }} }};"""


@pytest.mark.browser
def test_metamask_signs_in_the_page_and_the_register_writes_it(site, chromium) -> None:  # noqa: ANN001
    """The page's script with a stand-in MetaMask: it opens the wallet's list of accounts, asks
    for the account of the address, has the exact text signed, names the connected wallet, fills
    the form, and the receipt says who signed (static/sign.js)."""
    import hashlib

    from hackathon_memory.hedera.registry import readme_line

    client, _, _, database = site
    event = checkable(database)
    key, account, address = signing_account(client)
    line = readme_line("ethglobal.com/sample-event", hashlib.sha256(REPO.encode()).hexdigest())
    with_line(client, line)
    signatures = {COMMIT: metamask_signature(key, "ethglobal.com/sample-event")}
    page = served(chromium, client, reduced_motion="reduce")
    page.add_init_script(fake_metamask(address, signatures))
    check_in_window(page, event)
    page.locator("[data-sign-with=evm]").click()
    page.wait_for_function("document.querySelector('[name=signer]').value !== ''")
    assert f"Signed by the account {account}." in page.locator(".hm-sign-status").inner_text()
    assert page.locator(".hm-sign-status").get_attribute("data-state") == "done"
    shown = f"MetaMask, address {address[:6]}…{address[-4:]}, Hedera account {account}"
    assert page.locator(".hm-wallet-who").inner_text() == shown
    assert page.locator(".hm-sign-choice").is_hidden()
    # signed: the box says so, offers no signing again, and the next step has the focus
    assert page.locator(".hm-wallet-state").inner_text() == "Signed:"
    assert page.locator("[data-sign-now]").is_hidden()
    assert page.evaluate("document.activeElement.matches('#register-form [type=submit]')")
    asked = page.evaluate("window.ethereum.asked")
    methods = [call["method"] for call in asked]
    assert methods == ["wallet_requestPermissions", "eth_accounts", "personal_sign"]
    message = asked[2]["params"][0]
    assert bytes.fromhex(message[2:]).decode().endswith(f"Commit: {COMMIT}\nAccount: {account}")
    page.locator("#register-form button[type=submit]").click()
    page.wait_for_selector("#register-box dt:has-text('Signed by')")
    assert json.loads(client.writes.written[0])["scheme"] == "eip191"
    page.context.close()


@pytest.mark.browser
def test_a_wallet_without_a_list_of_accounts_still_connects(site, chromium) -> None:  # noqa: ANN001
    """An EVM wallet that does not know wallet_requestPermissions connects as before."""
    client, _, _, database = site
    event = checkable(database)
    key, account, address = signing_account(client)
    signatures = {COMMIT: metamask_signature(key, "ethglobal.com/sample-event")}
    page = served(chromium, client, reduced_motion="reduce")
    page.add_init_script(fake_metamask(address, signatures, permissions=False))
    check_in_window(page, event)
    page.locator("[data-sign-with=evm]").click()
    page.wait_for_selector(".hm-sign-status[data-state=done]")
    methods = page.evaluate("window.ethereum.asked.map((call) => call.method)")
    assert methods == ["wallet_requestPermissions", "eth_requestAccounts", "personal_sign"]
    assert page.locator("[name=signer]").input_value() == account
    page.context.close()


@pytest.mark.browser
def test_a_wallet_stays_connected_after_a_refresh_and_another_can_be_chosen(site, chromium) -> None:  # noqa: ANN001
    """After a refresh the box names the wallet that is still connected, asks nothing of the
    person to find it, and signs in one click; "Use another wallet" lets it go, in the wallet too,
    and offers the two kinds again (30 October 2026: a refresh showed the buttons as if no wallet
    were connected, and nothing let another wallet be chosen)."""
    client, _, _, database = site
    event = checkable(database)
    key, account, address = signing_account(client)
    signatures = {COMMIT: metamask_signature(key, "ethglobal.com/sample-event")}
    page = served(chromium, client, reduced_motion="reduce")
    page.add_init_script(fake_metamask(address, signatures))
    check_in_window(page, event)
    page.locator("[data-sign-with=evm]").click()
    page.wait_for_selector(".hm-sign-status[data-state=done]")
    check_in_window(page, event)  # the page again, as after a refresh
    page.wait_for_selector(f".hm-wallet:not([hidden]) .hm-wallet-who:has-text('{account}')")
    assert page.locator(".hm-sign-choice").is_hidden()
    assert page.evaluate("window.ethereum.asked.map((call) => call.method)") == ["eth_accounts"]
    page.locator("[data-sign-now]").click()
    page.wait_for_selector(".hm-sign-status[data-state=done]")
    assert page.locator("[name=signer]").input_value() == account
    page.locator("[data-wallet-other]").click()
    page.wait_for_selector(".hm-sign-choice:not([hidden]) [data-sign-with=evm]")
    assert page.locator(".hm-wallet").is_hidden()
    assert page.locator("[name=signature]").input_value() == ""  # it named the account let go
    assert "Disconnected." in page.locator(".hm-sign-status").inner_text()
    methods = page.evaluate("window.ethereum.asked.map((call) => call.method)")
    assert methods[-1] == "wallet_revokePermissions"
    assert page.evaluate("window.localStorage.getItem('hm-wallet')") is None
    check_in_window(page, event)  # after a refresh, nothing is looked for any more
    assert page.locator(".hm-sign-choice").is_visible()
    assert page.evaluate("window.ethereum.asked.length") == 0
    page.context.close()


# A stand-in for Hedera's WalletConnect library (@hashgraph/hedera-wallet-connect 2.1.3), with the
# parts that static/sign.js uses: a connection that the wallet keeps comes back with init, as
# DAppConnector.init makes a signer of each session that it finds.
STAND_IN_WALLETCONNECT = """
export const HederaJsonRpcMethod = { SignMessage: "hedera_signMessage" };
export const HederaSessionEvent = {
  ChainChanged: "chainChanged", AccountsChanged: "accountsChanged",
};
export const HederaChainId = { Testnet: "hedera:testnet" };
const signer = (account) => ({
  topic: "topic-1", getAccountId: () => ({ toString: () => account }),
});
export class DAppConnector {
  constructor() { this.signers = []; this.asked = []; window.standIn = this; }
  async init() {
    this.asked.push("init");
    const named = { peer: { metadata: { name: "HashPack" } } };
    this.walletConnectClient = { session: { get: () => named } };
    const kept = window.localStorage.getItem("stand-in-session");
    if (kept) this.signers = [signer(kept)];
  }
  async openModal() {
    this.asked.push("openModal");
    window.localStorage.setItem("stand-in-session", "0.0.11235177");
    this.signers = [signer("0.0.11235177")];
  }
  async signMessage(call) {
    this.asked.push(call.signerAccountId);
    return { signatureMap: "c2ln" };
  }
  async disconnectAll() {
    this.asked.push("disconnectAll");
    window.localStorage.removeItem("stand-in-session");
    this.signers = [];
  }
}
"""


@pytest.mark.browser
def test_a_hedera_wallet_comes_back_after_a_refresh_and_can_be_let_go(site, chromium) -> None:  # noqa: ANN001
    """With a stand-in for Hedera's WalletConnect library that keeps its connection as HashPack
    does: after a refresh the box names the wallet and its account with no list of wallets, signs
    with it, and "Use another wallet" ends the connection (30 October 2026)."""
    client, _, _, database = site
    event = checkable(database)
    with_id = client.make(walletconnect_project_id="0123456789abcdef0123456789abcdef")
    page = served(chromium, with_id, reduced_motion="reduce")
    library = {
        "https://esm.sh/@hashgraph/hedera-wallet-connect@2.1.3": STAND_IN_WALLETCONNECT,
        "https://esm.sh/@hiero-ledger/sdk@2.79.0": "export const LedgerId = {TESTNET: 'testnet'};",
    }
    page.route(lambda url: url in library, lambda route: route.fulfill(
        body=library[route.request.url], content_type="text/javascript",
        headers={"Access-Control-Allow-Origin": "*"}))  # fmt: skip
    check_in_window(page, event)
    page.locator("[data-sign-with=hedera]").click()
    page.wait_for_selector(".hm-sign-status[data-state=done]")
    assert page.locator(".hm-wallet-who").inner_text() == "HashPack, account 0.0.11235177"
    signed = "hedera:testnet:0.0.11235177"
    assert page.evaluate("window.standIn.asked") == ["init", "openModal", signed]
    check_in_window(page, event)  # the page again, as after a refresh
    page.wait_for_selector(".hm-wallet:not([hidden]) .hm-wallet-who:has-text('0.0.11235177')")
    page.locator("[data-sign-now]").click()
    page.wait_for_selector(".hm-sign-status[data-state=done]")
    assert page.evaluate("window.standIn.asked") == ["init", signed]  # no list of wallets
    page.locator("[data-wallet-other]").click()
    page.wait_for_selector(".hm-sign-choice:not([hidden]) [data-sign-with=hedera]")
    assert page.evaluate("window.standIn.asked")[-1] == "disconnectAll"
    assert page.evaluate("window.localStorage.getItem('hm-wallet')") is None
    page.context.close()


@pytest.mark.browser
def test_a_newer_commit_lets_the_old_signature_go_and_the_next_one_names_it(site, chromium) -> None:  # noqa: ANN001
    """The team signs, then adds its line to the README, which makes a commit. The register
    refuses the signature of the older commit above its box, which stays; the box lets that
    signature go, and the next one names the newer commit (30 October 2026: with the box kept,
    every new signature would have named the old commit)."""
    from checkfakes import commits_answer
    from fakes import Reply
    from hackathon_memory.collect.github_commits import commits_address

    client, _, _, database = site
    event = checkable(database)
    key, account, address = signing_account(client)
    newer = "ab" * 20
    signatures = {made: metamask_signature(key, "ethglobal.com/sample-event", made)
                  for made in (COMMIT, newer)}  # fmt: skip
    page = served(chromium, client, reduced_motion="reduce")
    page.add_init_script(fake_metamask(address, signatures))
    check_in_window(page, event)
    page.locator("[data-sign-with=evm]").click()
    page.wait_for_selector(".hm-sign-status[data-state=done]")
    with_line(client, page.content())  # the line makes a commit
    client.github_site.pages[commits_address(REPO)] = Reply(200, commits_answer(newer))
    page.locator("#register-form button[type=submit]").click()
    page.wait_for_selector("#register-problem:has-text('A new commit reached the repository')")
    page.wait_for_function(f"document.querySelector('[data-sign]').dataset.commit === '{newer}'")
    assert page.locator("[name=signature]").input_value() == ""
    assert page.locator(".hm-commit-now").inner_text() == f"{newer[:12]}…"
    assert page.locator(".hm-sign-status").get_attribute("data-state") == "problem"
    assert page.locator(".hm-wallet-state").inner_text() == "Connected:"  # to sign again
    page.locator("[data-sign-now]").click()
    page.wait_for_selector(".hm-sign-status[data-state=done]")
    assert page.locator("#register-problem").inner_text() == ""  # the new signature answers it
    page.locator("#register-form button[type=submit]").click()
    page.wait_for_selector("#register-box dt:has-text('Signed by')")
    record = json.loads(client.writes.written[0])
    assert (record["commit"], record["account"]) == (newer, account)
    page.context.close()


@pytest.mark.browser
def test_an_address_with_no_account_is_shown_how_to_make_one(site, chromium) -> None:  # noqa: ANN001
    """An EVM wallet connects, and its address has no Hedera account yet: the box says so where it
    names the wallet, with the address to copy and the faucet that makes the account, and once the
    faucet made it, the same button finds it and signs (30 October 2026: one red line said that
    the account was missing, and not how to make it)."""
    client, _, _, database = site
    event = checkable(database)
    key, account, address = signing_account(client)
    accounts = client.mirrors["testnet"].things["account"]
    made = {name: accounts.pop(name) for name in (account, address)}  # not made yet
    signatures = {COMMIT: metamask_signature(key, "ethglobal.com/sample-event")}
    page = served(chromium, client, reduced_motion="reduce")
    page.add_init_script(fake_metamask(address, signatures))
    check_in_window(page, event)
    page.locator("[data-sign-with=evm]").click()
    page.wait_for_selector(".hm-wallet-new:not([hidden])")
    assert page.locator(".hm-wallet-who").inner_text().endswith(", no Hedera account yet")
    assert page.locator(".hm-wallet-address").inner_text() == address
    faucet = page.locator(".hm-wallet-new a")
    assert faucet.get_attribute("href") == "https://portal.hedera.com/faucet"
    status = page.locator(".hm-sign-status")
    assert status.get_attribute("data-state") == "problem"
    assert "has no Hedera account on the test network yet" in status.inner_text()
    accounts.update(made)  # the faucet makes the account
    page.locator("[data-sign-now]").click()
    page.wait_for_selector(".hm-sign-status[data-state=done]")
    assert page.locator(".hm-wallet-new").is_hidden()
    assert page.locator("[name=signer]").input_value() == account
    page.context.close()


# --------------------------------------------------------- a wait for Gemini (7 November 2026)


def checked_page(chromium, client, database, **context):  # noqa: ANN001, ANN003, ANN201
    """A page with the result of a check in its window, and the button of Gemini ready."""
    event = checkable(database)  # before the page, which lists the hackathons
    page = served(chromium, client, viewport={"width": 1440, "height": 900}, **context)
    page.goto("http://site.test/")
    page.fill("#check-repo", "github.com/sample-org/pebble-pay")
    page.select_option("#check-event", event)
    page.locator("#check button[type=submit]").click()
    page.wait_for_selector("#viewer[open] .check-result")
    return page


def answers_each_place(page, fake) -> None:  # noqa: ANN001
    """The model's answer has a comparison for each project of the check on the page."""
    places = page.locator(".check-result .hm-compare").count()
    fake.answer_text = compare_answer(*[(n, ["what_it_does"]) for n in range(1, places + 1)])


def is_comparison(url: str) -> bool:
    return "/compare?" in url


def holds_comparisons(page) -> list:  # noqa: ANN001
    """The requests of a comparison wait here: `fallback()` on one lets the site answer it."""
    held: list = []
    page.route(is_comparison, lambda route: held.append(route))
    return held


@pytest.mark.browser
def test_a_wait_for_gemini_shows_its_time_and_when_it_ends(site, chromium) -> None:  # noqa: ANN001
    """A line says what Gemini does, for how long, and that the page stops waiting by itself. No
    button cancels: a wait has an end anyway, his word of 7 November 2026."""
    client, fake, _, database = site
    page = checked_page(chromium, client, database)
    answers_each_place(page, fake)
    held = holds_comparisons(page)
    page.locator("[data-check-compare]").click()
    line = page.locator(".hm-wait")
    line.wait_for()
    assert "Gemini is comparing these projects with the README" in line.inner_text()
    assert "stops waiting by itself after 90 seconds" in line.inner_text()
    assert line.locator("button").count() == 0
    page.wait_for_function("parseInt(document.querySelector('.hm-wait-time').textContent) >= 2")
    assert page.locator("[data-check-compare]").is_disabled()
    held[0].fallback()
    page.wait_for_selector(".check-result .hm-compare-text")
    assert page.locator(".hm-wait").count() == 0
    page.context.close()


@pytest.mark.browser
def test_no_answer_leaves_a_comparison_waiting(site, chromium) -> None:  # noqa: ANN001
    """An answer with none of the places, an error of the host, or no answer at all: the wait
    ends, the page says so once, and the button can be pressed again. An answer with none of the
    places left them waiting for ever on the public copy (7 November 2026)."""
    client, _, _, database = site
    page = checked_page(chromium, client, database)
    endings = {
        "could not be generated": lambda route: route.fulfill(
            status=200, body="", headers={"content-type": "text/html"}),
        "went wrong on the server": lambda route: route.fulfill(status=504, body="timed out"),
        "did not answer": lambda route: route.abort(),
    }  # fmt: skip
    for words, ending in endings.items():
        page.route(is_comparison, ending)
        page.locator("[data-check-compare]").click()
        page.wait_for_selector(f".hm-compare-said:has-text('{words}')")
        page.wait_for_function("!document.querySelector('.compare.waiting')")
        assert page.locator(".hm-wait").count() == 0
        assert page.locator(".hm-compare-said").count() == 1  # said once, not for each project
        page.wait_for_function("!document.querySelector('[data-check-compare]').disabled")
        page.unroute(is_comparison, ending)
    page.context.close()


@pytest.mark.browser
def test_a_comparison_goes_on_while_a_project_of_the_check_is_open(site, chromium) -> None:  # noqa: ANN001
    """The check waits with its elements alive, not as text: its wait goes on, and an answer that
    comes while a project is open shows on the way back. As text, its places kept waiting for
    ever (7 November 2026)."""
    client, fake, _, database = site
    page = checked_page(chromium, client, database)
    answers_each_place(page, fake)
    held = holds_comparisons(page)
    page.locator("[data-check-compare]").click()
    page.locator(".hm-wait").wait_for()
    project = page.locator(".check-result .hm-close-name a").first

    def to_the_project() -> None:
        project.click()
        page.wait_for_selector("#viewer[open] .project[data-project]")

    def back() -> None:
        page.locator("[data-back-to-check]").click()
        page.wait_for_selector("#viewer[open] .check-result")

    to_the_project()
    assert page.locator(".hm-wait").is_hidden()
    back()
    page.locator(".hm-wait").wait_for()  # still waiting, and still counting
    page.wait_for_function("parseInt(document.querySelector('.hm-wait-time').textContent) >= 1")
    to_the_project()
    held[0].fallback()
    page.wait_for_selector("#check-kept .hm-compare-text", state="attached")
    back()
    page.wait_for_selector(".check-result .hm-compare-text")
    assert page.locator(".compare.waiting").count() == 0
    assert page.locator("#check-kept").count() == 0 and page.locator("#register-form").count() == 1
    page.context.close()


@pytest.mark.browser
def test_the_search_shows_the_wait_of_each_step_of_gemini(site, chromium) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    fake.answer_queue = [json.dumps({"closest": [1, 2, 3]})]
    fake.answer_text = compare_answer((1, ["what_it_does"]), (2, ["what_it_does"]))
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto(SEARCH)
    sorting: list = []
    page.route(lambda url: "ai=1" in url, lambda route: sorting.append(route))
    held = holds_comparisons(page)
    page.locator("#ai-button").click()
    page.wait_for_selector(".hm-wait:has-text('Gemini is sorting the closest projects')")
    assert page.locator(".hm-asking").is_hidden()  # the line says it, with the time
    sorting[0].fallback()
    page.wait_for_selector(".hm-wait:has-text('comparing these projects with your idea')")
    held[0].fallback()
    page.wait_for_function("!document.querySelector('.compare.waiting')")
    assert page.locator(".hm-wait").count() == 0
    page.context.close()


@pytest.mark.browser
def test_a_comparison_in_a_window_can_be_asked_again_after_a_failure(site, chromium) -> None:  # noqa: ANN001
    client, fake, ids, _ = site
    fake.fail_with = (503, "unavailable")
    page = served(chromium, client, viewport={"width": 1440, "height": 900})
    page.goto(SEARCH)
    pebble = ids["Pebble Pay"]
    page.locator(f"#result-{pebble} .result-link").click()
    page.locator(f"#one-compare-{pebble} button").click()
    page.wait_for_selector(f"#one-compare-{pebble}:has-text('could not be generated')")
    fake.fail_with = None
    fake.answer_text = compare_answer((1, ["what_it_does"]))
    page.locator(f"#one-compare-{pebble} button").click()
    page.wait_for_selector(f"#one-compare-{pebble} .hm-compare-text")
    assert page.locator(".hm-wait").count() == 0
    page.context.close()


# ------------------------------------------------------------------ the tour (design 12.1, S8)


def told(what: str):  # noqa: ANN201
    """The request in which the tour's script tells the copy what the visitor did (S9)."""

    def asked(request) -> bool:  # noqa: ANN001
        return request.method == "POST" and urlsplit(request.url).path == f"/tour/{what}"

    return asked


def said(request) -> dict:  # noqa: ANN001
    return {name: value for name, (value,) in parse_qs(urlsplit(request.url).query).items()}


def test_the_search_page_holds_the_tour_and_every_page_offers_it_again(site) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = client.get("/").text
    offer = '<aside class="hm-tour-offer" id="tour-offer" aria-label="A tour of this page" hidden>'
    assert offer in page  # hidden until the page's script offers it
    steps = page.split('<template id="tour-steps">', 1)[1].split("</template>", 1)[0]
    assert steps.count("<div data-step") == 10 and "<h3>Welcome to Jevadu</h3>" in steps
    for address in ("/", "/about/how", "/check?repo=github.com/sample-org/pebble-pay"):
        assert '<a href="/?tour=1" data-tour-again>Take the tour</a>' in client.get(address).text
    for name in ("driver.js.iife.js", "driver.css", "driver-LICENSE.txt"):
        assert client.get(f"/static/vendor/{name}").status_code == 200


@pytest.mark.browser
def test_a_first_visit_is_offered_a_tour_that_can_be_skipped_at_any_step(site, chromium) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = served(chromium, client, tour_offer=True, viewport={"width": 1440, "height": 900})
    page.goto("http://site.test/")
    page.wait_for_selector("#tour-offer:not([hidden])")
    with page.expect_request(told("start")) as started:
        page.locator("[data-tour-start]").click()
    assert said(started.value) == {"from": "offer"}  # noted on the public copy (S9)
    assert started.value.response().status == 204  # the site's own answer to what was sent
    popover = page.locator(".driver-popover.hm-tour")
    popover.wait_for()
    assert page.locator("#tour-offer").is_hidden()
    assert popover.locator(".driver-popover-title").inner_text() == "Welcome to Jevadu"
    assert popover.locator(".driver-popover-progress-text").inner_text() == "1 of 10"
    popover.locator(".driver-popover-next-btn").click()
    page.wait_for_function("document.querySelector('.driver-popover-title').textContent === "
                           "'Your idea'")  # fmt: skip
    assert "driver-active-element" in (page.locator("#idea").get_attribute("class") or "")
    with page.expect_request(told("skip")) as skipped:
        popover.locator(".hm-tour-skip").click()  # on any step
    assert said(skipped.value) == {"step": "2", "of": "10", "how": "button"}
    assert skipped.value.response().status == 204
    page.wait_for_selector(".driver-popover", state="detached")
    assert page.evaluate("localStorage.getItem('hm-tour')") == "seen"
    page.reload()
    page.wait_for_timeout(500)
    assert page.locator("#tour-offer").is_hidden()  # never offered again in this browser
    page.context.close()


@pytest.mark.browser
def test_no_thanks_is_kept_and_the_link_at_the_bottom_starts_the_tour(site, chromium) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = served(chromium, client, tour_offer=True, viewport={"width": 1440, "height": 900})
    page.goto("http://site.test/")
    page.wait_for_selector("#tour-offer:not([hidden])")
    with page.expect_request(told("decline")) as declined:
        page.locator("[data-tour-decline]").click()
    assert said(declined.value) == {}
    assert page.locator("#tour-offer").is_hidden()
    assert page.evaluate("localStorage.getItem('hm-tour')") == "declined"
    page.goto("http://site.test/about/how")  # another page: its link loads the search page
    with page.expect_request(told("start")) as started:
        page.locator("[data-tour-again]").click()
    assert said(started.value) == {"from": "link"}
    page.locator(".driver-popover.hm-tour").wait_for()
    assert "tour=1" not in page.url  # a reload does not start it again
    with page.expect_request(told("skip")) as skipped:
        page.keyboard.press("Escape")  # Escape skips it too
    assert said(skipped.value) == {"step": "1", "of": "10", "how": "escape"}
    page.wait_for_selector(".driver-popover", state="detached")
    assert page.evaluate("localStorage.getItem('hm-tour')") == "seen"
    page.context.close()


@pytest.mark.browser
def test_a_click_anywhere_but_the_note_ends_the_tour_and_reaches_nothing(site, chromium) -> None:  # noqa: ANN001
    """While the tour runs, the page does not react: a click on the part that a step lights ends
    the tour and opens nothing, and a click on the shade ends it too (30 October 2026: a click on
    the lit part went through to the page, which opened a project's window, and the tour went
    on)."""
    client, _, _, _ = site
    page = served(chromium, client, tour_offer=True, viewport={"width": 1440, "height": 900},
                  reduced_motion="reduce")  # fmt: skip
    page.goto("http://site.test/?tour=1")
    popover = page.locator(".driver-popover.hm-tour")
    popover.wait_for()
    for at in range(2, 7):  # step 6 lights the list of projects
        popover.locator(".driver-popover-next-btn").click()
        page.wait_for_function("document.querySelector('.driver-popover-progress-text')"
                               f".textContent === '{at} of 10'")  # fmt: skip
    link = page.locator("#result-list .result-link").first.bounding_box()
    x, y = link["x"] + 10, link["y"] + link["height"] / 2
    lit = page.locator(".driver-active-element").bounding_box()  # the point is in the lit part
    assert lit["x"] < x < lit["x"] + lit["width"] and lit["y"] < y < lit["y"] + lit["height"]
    with page.expect_request(told("skip")) as skipped:
        page.mouse.click(x, y)
    assert said(skipped.value) == {"step": "6", "of": "10", "how": "click"}
    page.wait_for_selector(".driver-popover", state="detached")
    page.wait_for_timeout(500)
    assert page.locator("dialog[open]").count() == 0  # no project's window opened
    page.goto("http://site.test/?tour=1")
    popover.wait_for()
    with page.expect_request(told("skip")) as skipped:
        page.mouse.click(1300, 860)  # the shade
    assert said(skipped.value) == {"step": "1", "of": "10", "how": "click"}
    page.wait_for_selector(".driver-popover", state="detached")
    page.context.close()


@pytest.mark.browser
def test_a_tour_followed_to_its_last_step_is_told_as_finished(site, chromium) -> None:  # noqa: ANN001
    """Done on the last step ends the tour as finished, once (7 November 2026)."""
    client, _, _, _ = site
    page = served(chromium, client, tour_offer=True, viewport={"width": 1440, "height": 900},
                  reduced_motion="reduce")  # fmt: skip
    endings: list[str] = []
    page.on("request", lambda one: endings.append(urlsplit(one.url).path)
            if one.method == "POST" and "/tour/" in one.url else None)  # fmt: skip
    page.goto("http://site.test/?tour=1")
    popover = page.locator(".driver-popover.hm-tour")
    popover.wait_for()
    for at in range(2, 11):
        popover.locator(".driver-popover-next-btn").click()
        page.wait_for_function("document.querySelector('.driver-popover-progress-text')"
                               f".textContent === '{at} of 10'")  # fmt: skip
    with page.expect_request(told("done")) as done:
        popover.locator(".driver-popover-next-btn").click()  # it reads Done
    assert said(done.value) == {"of": "10"}
    page.wait_for_selector(".driver-popover", state="detached")
    page.wait_for_timeout(300)
    assert endings == ["/tour/start", "/tour/done"]
    page.context.close()


@pytest.mark.browser
def test_the_tour_rings_the_part_it_shows_and_shades_a_dark_page_deeper(site, chromium) -> None:  # noqa: ANN001
    """In the dark theme the lit part hardly stood out under the shade (30 October 2026): the part
    of a step has a ring in the main colour, and the shade over a dark page is deeper."""
    client, _, _, _ = site
    shades = {}
    for scheme in ("light", "dark"):
        page = served(chromium, client, tour_offer=True, color_scheme=scheme,
                      reduced_motion="reduce", viewport={"width": 1440, "height": 900})  # fmt: skip
        page.goto("http://site.test/?tour=1")
        popover = page.locator(".driver-popover.hm-tour")
        popover.wait_for()
        popover.locator(".driver-popover-next-btn").click()
        page.wait_for_function("document.querySelector('.driver-popover-progress-text')"
                               ".textContent === '2 of 10'")  # fmt: skip
        ring = page.evaluate("""() => {
          const idea = getComputedStyle(document.getElementById('idea'));
          const primary = getComputedStyle(document.body).getPropertyValue('--tblr-primary');
          const probe = document.createElement('i');
          probe.style.color = primary;
          document.body.append(probe);
          const colour = getComputedStyle(probe).color;
          probe.remove();
          return [idea.outlineStyle, idea.outlineWidth, idea.outlineColor === colour];
        }""")
        assert ring == ["solid", "2px", True], scheme
        shade = "getComputedStyle(document.querySelector('.driver-overlay path')).opacity"
        shades[scheme] = float(page.evaluate(shade))
        page.context.close()
    assert shades == {"light": 0.45, "dark": 0.72}
