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
# Ideas written without reading a page: no known project.
BLIND = """# Gate B: invented blind ideas
idea: help a street vendor get paid with a coin

idea: follow every parcel that moves

idea: a ballot that a small club can count
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
    """Three saved invented pages and a file of ideas."""
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


def the_result(results_dir: Path, proof: str = "gate_b") -> dict:
    files = sorted(results_dir.glob(f"*-{proof}.json"))
    return json.loads(files[-1].read_text(encoding="utf-8"))


def gate_databases(server_conninfo: str) -> set[str]:
    """The names of the databases that a run of the proof makes, on the server now."""
    with psycopg.connect(server_conninfo) as conn:
        rows = conn.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE 'gate_b_%'"
        ).fetchall()
    return {name for (name,) in rows}


def failed(saved: dict) -> list[str]:
    return [check["name"] for check in saved["checks"] if not check["passed"]]


# --------------------------------------------------------------------- the file of ideas


def test_the_ideas_are_read_in_blocks(tmp_path: Path) -> None:
    questions = gate_b.read_questions(write(tmp_path / "q.txt", QUESTIONS))
    assert [q.idea for q in questions] == [
        "help a street vendor get paid with a coin",
        "follow every parcel that moves",
        "a ballot that a small club can count",
    ]
    assert questions[1].finds == ("https://ethglobal.com/showcase/cedar-post-x1y2z",)


def test_an_idea_needs_no_known_project(tmp_path: Path) -> None:
    questions = gate_b.read_questions(write(tmp_path / "q.txt", BLIND))
    assert [q.finds for q in questions] == [(), (), ()]


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("idea: one\nfinds: https://a.example.test/p\nwhat is this\n", "line 3"),
        ("finds: https://a.example.test/p\n", "line 1"),  # no idea before it
        ("idea: one\nfinds: not-a-link\n", "line 2"),
        ("idea:\n", "line 1"),  # an idea with no words
    ],
)
def test_a_wrong_file_is_refused_and_the_line_is_named_without_its_words(
    tmp_path: Path, text: str, line: str
) -> None:
    with pytest.raises(gate_b.QuestionsError) as wrong:
        gate_b.read_questions(write(tmp_path / "q.txt", text))
    assert line in str(wrong.value)
    assert "what is this" not in str(wrong.value) and "not-a-link" not in str(wrong.value)


# --------------------------------------------------------------------- part 1: the path


def test_the_path_passes_and_finds_the_known_projects(
    tmp_path: Path, empty_database: str, results_dir: Path, server_conninfo: str
) -> None:
    settings = Settings(_env_file=None, database_url=empty_database, data_dir=str(data(tmp_path)))
    client, _, _ = google()
    before = gate_databases(server_conninfo)
    code = gate_b.run(settings, mirrors=stand_ins(), google=client, minimum_projects=3)
    saved = the_result(results_dir)
    assert code == 0, failed(saved)
    assert saved["gate"] == "B"
    assert saved["measurements"]["places_of_the_known_projects"] == [[1], [1], [1]]
    assert saved["measurements"]["projects"] == 3
    text = json.dumps(saved)
    for words in ("vendor", "parcel", "ballot", "ethglobal.com", "Pebble"):
        assert words not in text  # no idea, no name, no address
    # The new database of this run was deleted. Another run of the proof, on the same server
    # at the same time, may have one of its own: only the ones that this run made count.
    assert gate_databases(server_conninfo) <= before


def test_a_known_project_that_is_not_found_fails_the_path(
    tmp_path: Path, empty_database: str, results_dir: Path
) -> None:
    wrong = QUESTIONS.replace("cedar-post-x1y2z/", "a-project-that-is-not-there-z9z9z")
    settings = Settings(
        _env_file=None, database_url=empty_database, data_dir=str(data(tmp_path, wrong))
    )
    client, _, _ = google()
    assert gate_b.run(settings, mirrors=stand_ins(), google=client, minimum_projects=3) == 1
    assert failed(the_result(results_dir)) == [
        "idea 2: its known project(s) in the first 10 results"
    ]


def test_blind_ideas_pass_the_path_and_their_results_are_written_to_mark(
    tmp_path: Path, empty_database: str, results_dir: Path
) -> None:
    folder = data(tmp_path, BLIND)
    settings = Settings(_env_file=None, database_url=empty_database, data_dir=str(folder))
    client, _, _ = google()
    assert gate_b.run(settings, mirrors=stand_ins(), google=client, minimum_projects=3) == 0
    saved = the_result(results_dir)
    assert saved["measurements"]["ideas_with_known_projects"] == 0
    text = (folder / "by-hand" / gate_b.RESULTS).read_text(encoding="utf-8")
    assert text.count("== idea ") == 3
    assert text.count("   mark:") == 9  # three projects for each of the three ideas
    assert "idea: follow every parcel that moves" in text
    assert "1. Cedar Post  (ETHGlobal Sample Event)\n   Cedar Post, invented." in text
    assert "   page: https://ethglobal.com/showcase/cedar-post-x1y2z" in text


# --------------------------------------------------------------------- part 2: the marks


def marked(text: str, idea_marks: dict[int, list[str]]) -> str:
    """Fill the marks of each idea, in order: {idea: ["yes", "no", ...]}."""
    out, idea, place = [], 0, 0
    for line in text.splitlines():
        if line.startswith("== idea "):
            idea, place = int(line.split()[-1]), 0
        if line == "   mark:":
            marks = idea_marks.get(idea, [])
            line = f"   mark: {marks[place]}" if place < len(marks) else line
            place += 1
        out.append(line)
    return "\n".join(out) + "\n"


@pytest.fixture
def results(tmp_path: Path, empty_database: str, results_dir: Path) -> Path:
    """The results of the three blind ideas, written by part 1, not marked yet."""
    folder = data(tmp_path, BLIND)
    settings = Settings(_env_file=None, database_url=empty_database, data_dir=str(folder))
    client, _, _ = google()
    gate_b.run(settings, mirrors=stand_ins(), google=client, minimum_projects=3)
    return folder / "by-hand" / gate_b.RESULTS


def test_the_marks_pass_when_each_idea_has_a_yes(results: Path, results_dir: Path) -> None:
    text = results.read_text(encoding="utf-8")
    results.write_text(marked(text, {1: ["yes", "no"], 2: ["no", "yes"], 3: ["yes"]}),
                       encoding="utf-8")  # fmt: skip
    settings = Settings(_env_file=None, data_dir=str(results.parent.parent))
    assert gate_b.judge(settings) == 0
    saved = the_result(results_dir, "gate_b_marks")
    assert saved["measurements"]["ideas"] == [
        {"results": 3, "yes": 1, "no": 1, "not_marked": 1, "first_yes_at": 1},
        {"results": 3, "yes": 1, "no": 1, "not_marked": 1, "first_yes_at": 2},
        {"results": 3, "yes": 1, "no": 0, "not_marked": 2, "first_yes_at": 1},
    ]


def test_the_marks_fail_when_an_idea_has_no_yes(results: Path, results_dir: Path) -> None:
    text = results.read_text(encoding="utf-8")
    results.write_text(marked(text, {1: ["yes"], 2: ["no", "no", "no"], 3: ["yes"]}),
                       encoding="utf-8")  # fmt: skip
    settings = Settings(_env_file=None, data_dir=str(results.parent.parent))
    assert gate_b.judge(settings) == 1
    assert failed(the_result(results_dir, "gate_b_marks")) == [
        'idea 2: at least one result marked "yes" in the first 10'
    ]


def test_a_mark_that_is_not_yes_or_no_is_refused(results: Path, results_dir: Path) -> None:
    text = results.read_text(encoding="utf-8")
    results.write_text(marked(text, {1: ["maybe"]}), encoding="utf-8")
    settings = Settings(_env_file=None, data_dir=str(results.parent.parent))
    assert gate_b.judge(settings) == 1
    [check] = the_result(results_dir, "gate_b_marks")["checks"]
    assert check["detail"].startswith("line ") and "maybe" not in check["detail"]


def test_a_new_run_never_loses_the_marks_of_an_earlier_one(
    results: Path, empty_database: str, results_dir: Path
) -> None:
    text = results.read_text(encoding="utf-8")
    results.write_text(marked(text, {1: ["yes"]}), encoding="utf-8")
    settings = Settings(
        _env_file=None, database_url=empty_database, data_dir=str(results.parent.parent)
    )
    client, _, _ = google()
    gate_b.run(settings, mirrors=stand_ins(), google=client, minimum_projects=3)
    kept = sorted(results.parent.glob("gate-b-results-*.txt"))
    assert len(kept) == 1
    assert "   mark: yes" in kept[0].read_text(encoding="utf-8")
    assert "   mark: yes" not in results.read_text(encoding="utf-8")  # the new file is clean


def test_the_proof_needs_three_ideas(tmp_path: Path, results_dir: Path) -> None:
    one = "idea: one idea\n"
    settings = Settings(_env_file=None, data_dir=str(data(tmp_path, one)))
    assert gate_b.run(settings) == 1
    assert [c["passed"] for c in the_result(results_dir)["checks"]] == [False]
