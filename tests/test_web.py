"""The website (design 12.1, fourth version): the search, the window of a project, the check of
a submission, the windows of the bottom of the page and the charts, on invented projects, with
Google, GitHub and the mirror node faked."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import pytest

from checkfakes import REGISTER, REPO, TOPIC, RegisterWrites, found_code, nodes
from fakes import ARCHIVE_COMMIT, project_page
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.projects import ProjectStore
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
        return TestClient(
            create_app(changed, google=client, llm=client, github_client=asker, mirrors=mirrors,
                       register_writer=writes, stand_in_client=open_client(stand_in),
                       refresh_inline=True, **(app_options or {}))
        )  # fmt: skip

    served = make()
    served.stand_in = stand_in  # what the stand-in of the search model was asked
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
    assert "&ldquo;HCS&rdquo;" in rows[0][1] and ">1</td>" in rows[0][1]
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
    assert "<dd>1 Consensus Service transaction, the last on 1 June 2026</dd>" in block
    assert "Read from the mirror node on 23 October 2026: 2 of its own IDs." in block


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
    assert "2 accounts that the page does not name." in block
    assert ("1 day with a transaction: 1 during the event, 0 in the 30 days before it, 0 in the "
            "30 days after it.") in block  # fmt: skip
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
    assert ("Its token 0.0.4515: an NFT collection with no supply limit; a royalty of 5% on each "
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
    assert '<span class="badge bg-green-lt">Mainnet</span>' in named("mainnet", during)
    found = client.get("/", params={"idea": "help a street vendor get paid with a coin"}).text
    assert '<span class="badge bg-green-lt">Mainnet</span>' in found  # and on the result
    assert "Mainnet" not in named(None, during)  # named with no network
    assert "Mainnet" not in named("mainnet", datetime(2021, 9, 20, tzinfo=UTC))  # long before


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
    for holders, said in (((team,), "No account that it does not name holds its tokens now."),
                          ((team, "0.0.9001"), "Its tokens are held now by 1 account that it "
                                               "does not name.")):  # fmt: skip
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
    assert '<option value="hedera_prize">Won a Hedera prize (2)</option>' in page
    assert '<option value="winners_list">Winners&#39; list only (1)</option>' in page
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
    # The stand-in's answers are dated 11 October 2026, more than an hour old, so this check
    # asks GitHub again (design 7.3): the facts, the README and the commit, and the archive,
    # which the stand-in made from another commit than its newest one.
    assert len(client.github_site.seen) == 10
    hidden = '<h2 class="visually-hidden">What the check found</h2>'
    assert hidden in page.text and hidden not in part.text


def test_a_rehearsal_says_so_at_the_top_of_every_page(site) -> None:  # noqa: ANN001
    """Started with --rehearsal, the website writes to the topic for rehearsals, and a band says
    so, so that a rehearsal is never taken for the register (design 9.3, 25 October 2026)."""
    client, _, ids, _ = site
    assert "hm-rehearsal" not in client.get("/").text
    rehearsal = client.make({"rehearsal": True})
    for page in ("/", f"/project/{ids['Pebble Pay']}"):
        band = rehearsal.get(page).text.split('class="hm-rehearsal"', 1)[1].split("</p>")[0]
        assert f"goes to the practice topic {REGISTER} on Hedera testnet" in band


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
    assert unknown.status_code == 400 and model_calls(fake, before) == 1  # no README was saved


def test_a_check_without_a_repository_or_with_wrong_days_says_what_to_do(site) -> None:  # noqa: ANN001
    client, _, _, database = site
    event = checkable(database)
    wrong = client.get("/check", params={"repo": "my project", "event": event}, headers=HX)
    assert wrong.status_code == 400 and "This is not a GitHub repository link" in wrong.text
    backwards = {"repo": REPO, "event": "other", "starts": "2026-03-08", "ends": "2026-03-06"}
    late = client.get("/check", params=backwards, headers=HX)
    assert late.status_code == 400 and "Enter the start and end dates" in late.text
    unknown = client.get("/check", params={"repo": REPO, "event": "99999"}, headers=HX)
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
    checkable(database)
    start = client.get("/")
    assert '<option value="">None: show the facts, without judging dates</option>' in start.text
    assert '<optgroup label="2026"><option value="' in start.text  # a group for each year
    assert "ETHGlobal Sample Event (6 to 8 March)</option>" in start.text  # a dated one
    part = client.get("/check", params={"repo": REPO, "event": ""}, headers=HX)
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
    """An answer of 400 takes the place of the steps of the check, and of the register's form."""
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
    page.wait_for_selector("#register-box:has-text('does not contain the line')")
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
    form = {**asked, "starts": "", "ends": "", "account": "0.0.4567891"}
    asked_before = len(client.github_site.seen)
    missing = client.post("/register", data=form, headers=HX)
    assert missing.status_code == 400 and "does not contain the line" in missing.text
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
        "account": hashlib.sha256(b"0.0.4567891").hexdigest(),
    }  # fmt: skip
    assert b"github" not in payload and b"pebble" not in payload  # no link in clear text
    again = client.post("/register", data=form, headers=HX)
    assert "Already registered" in again.text and len(client.writes.written) == 1
    later = client.get("/check", params=asked, headers=HX)
    assert "Already registered." in later.text and "sequence number 1" in later.text
    assert "Register on Hedera testnet" not in later.text  # it is registered for this event already


def test_a_registration_needs_a_checked_repository_and_a_real_account(site) -> None:  # noqa: ANN001
    client, _, _, database = site
    event = checkable(database)
    form = {"repo": REPO, "event": event, "starts": "", "ends": "", "account": ""}
    first = client.post("/register", data=form, headers=HX)
    assert first.status_code == 400 and "Check the repository first" in first.text
    check = client.get("/check", params={"repo": REPO, "event": event}, headers=HX)
    with_line(client, check.text)
    wrong = client.post("/register", data={**form, "account": "my wallet"}, headers=HX)
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


@pytest.mark.browser
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
    an outline, which the rule of no focus frame took away (24 October 2026)."""
    client, _, ids, _ = site
    pebble = ids["Pebble Pay"]
    page = served(chromium, client, viewport={"width": 1440, "height": 900}, reduced_motion=motion)
    page.goto(f"http://site.test/?open={pebble}")
    page.wait_for_selector("#viewer[open] .project[data-project]")
    page.locator("#viewer .project-marks .hm-mark-link").first.click()
    page.wait_for_timeout(200)
    part = f"document.getElementById('ledger-{pebble}')"
    assert "0px 0px 0px 2px" in page.evaluate(f"getComputedStyle({part}).boxShadow")
    page.context.close()


@pytest.mark.browser
def test_the_six_filters_stand_in_one_row(site, chromium) -> None:  # noqa: ANN001
    client, _, _, _ = site
    page = served(chromium, client, viewport={"width": 1280, "height": 900})
    page.goto("http://site.test/")
    tops = page.evaluate("[...document.querySelectorAll('.hm-filter')]"
                         ".map(f => Math.round(f.getBoundingClientRect().top))")  # fmt: skip
    assert len(tops) == 6 and len(set(tops)) == 1  # the prize had wrapped to a second row


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
    assert "No comparison for this project." in results.nth(2).inner_text()
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
    for _ in range(6):
        if strip.locator('[data-zoom="out"]').is_enabled():
            strip.locator('[data-zoom="out"]').click()
    back = page.evaluate(STRIP_STATE)
    assert back["zoom"] == 1 and abs(back["width"] - first["width"]) < 1 and back["ticks"] == 0
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
