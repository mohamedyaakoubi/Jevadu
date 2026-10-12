"""The step that embeds the projects: one embedding each, made again only when its text changes.

All data is invented. The real google-genai library runs, with the network faked.
"""

from __future__ import annotations

import psycopg
import pytest

from hackathon_memory.db.embeddings import EmbeddingStore
from hackathon_memory.db.runs import recorded_run
from hackathon_memory.llm.embeddings import SEARCH_MODEL
from hackathon_memory.pipeline import embed
from hackathon_memory.pipeline.__main__ import main as pipeline_main
from hackathon_memory.settings import Settings
from searchfakes import embed_all, google, three_projects

pytestmark = pytest.mark.integration


@pytest.fixture
def database(empty_database: str) -> str:
    return three_projects(empty_database)


def test_every_project_gets_one_embedding_and_a_second_run_pays_nothing(database: str) -> None:
    client, fake, calls = google()
    first = embed_all(database, client)
    assert (first.counts["projects"], first.counts["made"]) == (3, 3)
    assert len(calls.calls()) == 3
    sent = [body["content"]["parts"][0]["text"] for _, body in fake.requests]
    assert sent[0].startswith("title: Pebble Pay | text: Pebble Pay, invented.\n\nA street vendor")
    again = embed_all(database, client)
    assert (again.counts["made"], again.counts["the_same_as_before"]) == (0, 3)
    assert len(calls.calls()) == 3  # nothing more was paid for
    assert EmbeddingStore(database).counts(SEARCH_MODEL) == {
        "embeddings": 3,
        "embeddings_of_a_cut_text": 0,
    }


def test_a_changed_text_is_embedded_again(database: str) -> None:
    client, _, calls = google()
    embed_all(database, client)
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET short_line = 'A new line.' WHERE name = 'Fern Vote'")
    again = embed_all(database, client)
    assert again.counts["made"] == 1
    assert len(calls.calls()) == 4


def test_a_text_cut_by_the_model_is_counted(database: str) -> None:
    client, fake, _ = google()
    fake.truncated = True
    run = embed_all(database, client)
    assert run.counts["texts_cut_by_the_model"] == 3
    assert EmbeddingStore(database).counts(SEARCH_MODEL)["embeddings_of_a_cut_text"] == 3


def test_google_failing_three_times_in_a_row_stops_the_step(database: str) -> None:
    client, fake, _ = google()
    fake.fail_with = (400, "Invalid request")
    with pytest.raises(embed.GoogleIsAway), recorded_run(database, embed.STEP) as run:
        embed.embed_pages(EmbeddingStore(database), client, run, model=SEARCH_MODEL)
    # Three projects that failed, then the step itself, which stopped.
    assert [problem["rule"] for problem in run.problems] == ["ClientError"] * 3 + ["GoogleIsAway"]


def test_the_embed_step_of_the_pipeline_says_what_it_did(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    client, _, _ = google()
    settings = Settings(_env_file=None, database_url=database)
    assert pipeline_main(["embed", "--limit", "2"], settings, google=client) == 0
    said = capsys.readouterr().out
    assert "Projects: 3. Embeddings made: 2 (18 tokens)." in said
    assert "Left for a later run, because of the limit: 1." in said


@pytest.mark.parametrize("argv", [["embed", "--limit", "0"], ["embed", "--repos", "3"]])
def test_options_that_do_not_go_with_embed_are_refused(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert pipeline_main(argv, Settings(_env_file=None)) == 2
    assert "usage:" in capsys.readouterr().out
