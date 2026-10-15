"""The website: the search and the project card, on three invented projects, with Google faked."""

from __future__ import annotations

import json
from pathlib import Path

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
            "category": field("inferred", "Payments and remittance", [ON_PEBBLE]),
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
    return TestClient(create_app(settings, google=client)), fake, ids, database


def test_the_start_page_asks_for_an_idea_and_calls_no_model(site) -> None:  # noqa: ANN001
    client, fake, _, _ = site
    before = len(fake.requests)  # the embeddings of the three projects were made already
    page = client.get("/")
    assert page.status_code == 200
    assert '<textarea id="idea"' in page.text and "Search past projects" in page.text
    assert 'class="result"' not in page.text
    assert len(fake.requests) == before


def test_a_search_shows_the_closest_projects_with_their_marks(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get("/", params={"idea": "help a street vendor get paid with a coin"})
    assert page.status_code == 200
    first = page.text.index('class="result"')
    assert f'href="/project/{ids["Pebble Pay"]}?idea=' in page.text[first : first + 400]
    assert "A vendor takes coins." in page.text  # the model's sentence, with its label
    assert "written by a model, stated" in page.text
    assert "from the project's page" in page.text  # the others have no card yet
    assert "Hedera proof:" in page.text and "What the marks mean" in page.text


def test_the_card_keeps_the_three_sources_apart(site) -> None:  # noqa: ANN001
    client, _, ids, _ = site
    page = client.get(f"/project/{ids['Pebble Pay']}")
    assert page.status_code == 200
    text = page.text
    places = [text.index(words) for words in
              ("From the project's page", "From the code and the ledger",
               "Written by a model")]  # fmt: skip
    assert places == sorted(places)
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
    assert f'href="/project/{ids["Pebble Pay"]}?idea=' in page.text


def test_without_the_database_the_page_says_how_to_start_it() -> None:
    from fastapi.testclient import TestClient

    from hackathon_memory.web.app import create_app

    # Nothing listens on port 1. On some computers such a connection is dropped and not refused;
    # the website gives up after a few seconds and says what to do.
    settings = Settings(_env_file=None, database_url="postgresql://nobody@127.0.0.1:1/none")
    client = TestClient(create_app(settings, google=object()))
    page = client.get("/", params={"idea": "anything"})
    assert page.status_code == 503 and "docker compose up -d --wait db" in page.text


def test_the_text_of_a_page_is_shown_as_text_never_as_code(site) -> None:  # noqa: ANN001
    client, _, ids, database = site
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET short_line = %s WHERE id = %s",
                     ("<script>alert(1)</script>", ids["Fern Vote"]))  # fmt: skip
    page = client.get(f"/project/{ids['Fern Vote']}")
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text
