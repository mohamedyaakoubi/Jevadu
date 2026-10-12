"""The proof of Gate B, run on invented pages with stand-ins for the mirror node and Google."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

from fakes import StandInMirror, project_page
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.settings import Settings
from proofs import gate_b
from proofs import result as result_module
from searchfakes import PAGES, google

pytestmark = pytest.mark.integration

QUESTIONS = """# Gate B: invented questions
idea: help a street vendor get paid with a coin
finds: https://ethglobal.com/showcase/pebble-pay-x1y2z

idea: follow every parcel that moves
finds: https://ethglobal.com/showcase/cedar-post-x1y2z/

idea: a ballot that a small club can count
finds: https://ethglobal.com/showcase/fern-vote-x1y2z
"""


@pytest.fixture
def results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "proofs" / "results"
    monkeypatch.setattr(result_module, "RESULTS_DIR", folder)
    return folder


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def data(tmp_path: Path, questions: str = QUESTIONS) -> Path:
    """Three saved invented pages and a file of questions."""
    folder = tmp_path / "data"
    pages = RawStore(folder / "raw" / "ethglobal.com")
    for slug, (name, text) in PAGES.items():
        url = f"https://ethglobal.com/showcase/{slug}-x1y2z"
        body = project_page(name=name, slug=slug, short_line=f"{name}, invented.", description=text)
        fetch = FetchResult(url, url, 200, body, "text/html", "2026-10-10T19:00:00Z")
        pages.save(fetch, body, received=body, collector="TestTool/0.1.0")
    write(folder / "by-hand" / gate_b.QUESTIONS, questions)
    return folder


def stand_ins() -> dict:
    return {"testnet": StandInMirror("testnet"), "mainnet": StandInMirror("mainnet")}


# --------------------------------------------------------------------- the file of questions


def test_the_questions_are_read_in_blocks(tmp_path: Path) -> None:
    questions = gate_b.read_questions(write(tmp_path / "q.txt", QUESTIONS))
    assert [q.idea for q in questions] == [
        "help a street vendor get paid with a coin",
        "follow every parcel that moves",
        "a ballot that a small club can count",
    ]
    assert questions[1].finds == ("https://ethglobal.com/showcase/cedar-post-x1y2z",)


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("idea: one\nfinds: https://a.example.test/p\nwhat is this\n", "line 3"),
        ("finds: https://a.example.test/p\n", "line 1"),  # no idea before it
        ("idea: one\nfinds: not-a-link\n", "line 2"),
        ("idea: one\nidea: two\nfinds: https://a.example.test/p\n", "line 2"),
        ("idea: one\n", "the last idea"),
    ],
)
def test_a_wrong_file_is_refused_and_the_line_is_named_without_its_words(
    tmp_path: Path, text: str, line: str
) -> None:
    with pytest.raises(gate_b.QuestionsError) as wrong:
        gate_b.read_questions(write(tmp_path / "q.txt", text))
    assert line in str(wrong.value)
    assert "what is this" not in str(wrong.value) and "not-a-link" not in str(wrong.value)


# --------------------------------------------------------------------- the proof


def test_the_proof_passes_when_the_path_finds_the_known_projects(
    tmp_path: Path, empty_database: str, results_dir: Path, server_conninfo: str
) -> None:
    settings = Settings(_env_file=None, database_url=empty_database, data_dir=str(data(tmp_path)))
    client, _, _ = google()
    code = gate_b.run(settings, mirrors=stand_ins(), google=client, minimum_projects=3)
    [file] = results_dir.glob("*-gate_b.json")
    saved = json.loads(file.read_text(encoding="utf-8"))
    assert code == 0, [c for c in saved["checks"] if not c["passed"]]
    assert saved["gate"] == "B"
    assert saved["measurements"]["places_of_the_known_projects"] == [[1], [1], [1]]
    assert saved["measurements"]["projects"] == 3
    text = file.read_text(encoding="utf-8")
    for words in ("vendor", "parcel", "ballot", "ethglobal.com", "Pebble"):
        assert words not in text  # no question, no name, no address
    with psycopg.connect(server_conninfo) as conn:  # the new database was deleted
        left = conn.execute(
            "SELECT count(*) FROM pg_database WHERE datname LIKE 'gate_b_%'"
        ).fetchone()[0]
    assert left == 0


def test_the_proof_fails_when_a_known_project_is_not_found(
    tmp_path: Path, empty_database: str, results_dir: Path
) -> None:
    wrong = QUESTIONS.replace("cedar-post-x1y2z/", "a-project-that-is-not-there-z9z9z")
    settings = Settings(
        _env_file=None, database_url=empty_database, data_dir=str(data(tmp_path, wrong))
    )
    client, _, _ = google()
    assert gate_b.run(settings, mirrors=stand_ins(), google=client, minimum_projects=3) == 1
    [file] = results_dir.glob("*-gate_b.json")
    failed = [c["name"] for c in json.loads(file.read_text(encoding="utf-8"))["checks"]
              if not c["passed"]]  # fmt: skip
    assert failed == ["question 2: its known project(s) in the first 10 results"]


def test_the_proof_needs_three_questions(tmp_path: Path, results_dir: Path) -> None:
    one = "idea: one idea\nfinds: https://ethglobal.com/showcase/pebble-pay-x1y2z\n"
    settings = Settings(_env_file=None, data_dir=str(data(tmp_path, one)))
    assert gate_b.run(settings) == 1
    [file] = results_dir.glob("*-gate_b.json")
    checks = json.loads(file.read_text(encoding="utf-8"))["checks"]
    assert [c["passed"] for c in checks] == [False]
