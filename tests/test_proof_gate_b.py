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
# Blind ideas, and one written on purpose about something that the data does not hold.
MIXED = BLIND + "\nidea: a song that writes its own second verse\nexpect: none\n"


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
    assert {q.expect for q in questions} == {gate_b.CLOSE}


def test_an_idea_needs_no_known_project(tmp_path: Path) -> None:
    questions = gate_b.read_questions(write(tmp_path / "q.txt", BLIND))
    assert [q.finds for q in questions] == [(), (), ()]


def test_an_idea_may_expect_nothing_close(tmp_path: Path) -> None:
    questions = gate_b.read_questions(write(tmp_path / "q.txt", MIXED.replace("none", "None")))
    assert [q.expect for q in questions] == [gate_b.CLOSE] * 3 + [gate_b.NONE]


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("idea: one\nfinds: https://a.example.test/p\nwhat is this\n", "line 3"),
        ("finds: https://a.example.test/p\n", "line 1"),  # no idea before it
        ("idea: one\nfinds: not-a-link\n", "line 2"),
        ("idea:\n", "line 1"),  # an idea with no words
        ("idea: one\nexpect: maybe\n", "line 2"),
        ("expect: none\n", "line 1"),  # no idea before it
    ],
)
def test_a_wrong_file_is_refused_and_the_line_is_named_without_its_words(
    tmp_path: Path, text: str, line: str
) -> None:
    with pytest.raises(gate_b.QuestionsError) as wrong:
        gate_b.read_questions(write(tmp_path / "q.txt", text))
    assert line in str(wrong.value)
    for words in ("what is this", "not-a-link", "maybe"):
        assert words not in str(wrong.value)


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
    assert saved["measurements"]["file_of_ideas"] == gate_b.QUESTIONS
    text = json.dumps(saved)
    for words in ("vendor", "parcel", "ballot", "ethglobal.com", "Pebble"):
        assert words not in text  # no idea, no name, no address
    # The new database of this run was deleted. Another run of the proof, on the same server
    # at the same time, may have one of its own: only the ones that this run made count.
    assert gate_databases(server_conninfo) <= before


def test_every_call_of_the_proof_is_counted_in_the_main_database(
    tmp_path: Path, empty_database: str, results_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(_env_file=None, database_url=empty_database, data_dir=str(data(tmp_path)))
    client, _, calls = google()
    ledgers: list[str] = []

    def counted_on(given: Settings, purpose: str, **_: object) -> object:
        ledgers.append(given.database_conninfo())
        return client.tagged(purpose=purpose)

    monkeypatch.setattr(gate_b, "metered_client", counted_on)
    code = gate_b.run(settings, mirrors=stand_ins(), minimum_projects=3)
    assert code == 0, failed(the_result(results_dir))
    # The new database of the run is deleted at its end: a count kept there would be lost.
    assert ledgers == [settings.database_conninfo()]
    assert {call.purpose for call in calls.calls()} == {"embed_document", "embed_query"}


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
    assert 'write "yes", "n/a" or "no" after "mark:"' in text
    assert "idea: follow every parcel that moves" in text
    assert "1. Cedar Post  (ETHGlobal Sample Event)\n   Cedar Post, invented." in text
    assert "   page: https://ethglobal.com/showcase/cedar-post-x1y2z" in text


def test_another_file_of_ideas_writes_its_own_results(
    tmp_path: Path, empty_database: str, results_dir: Path
) -> None:
    folder = data(tmp_path, BLIND)
    write(folder / "by-hand" / "more-ideas.txt", MIXED)
    settings = Settings(_env_file=None, database_url=empty_database, data_dir=str(folder))
    client, _, _ = google()
    code = gate_b.run(settings, mirrors=stand_ins(), google=client, minimum_projects=3,
                      questions="more-ideas.txt", results="more-results.txt")  # fmt: skip
    saved = the_result(results_dir)
    assert code == 0, failed(saved)
    assert saved["measurements"]["file_of_ideas"] == "more-ideas.txt"
    assert saved["measurements"]["ideas_that_expect_nothing_close"] == 1
    assert not (folder / "by-hand" / gate_b.RESULTS).exists()
    text = (folder / "by-hand" / "more-results.txt").read_text(encoding="utf-8")
    assert "== idea 4\nidea: a song that writes its own second verse\nexpect: none\n" in text
    assert "python -m proofs.gate_b --marks more-results.txt" in text


def test_a_file_named_with_a_folder_is_refused(tmp_path: Path, results_dir: Path) -> None:
    folder = data(tmp_path, BLIND)
    settings = Settings(_env_file=None, data_dir=str(folder))
    assert gate_b.run(settings, questions="../gate-b-questions.txt") == 1
    assert failed(the_result(results_dir)) == ["the written ideas can be read"]
    assert gate_b.judge(settings, files=["../gate-b-results.txt"]) == 1
    assert failed(the_result(results_dir, "gate_b_marks")) == ["../gate-b-results.txt can be read"]


def test_the_proof_needs_three_ideas(tmp_path: Path, results_dir: Path) -> None:
    one = "idea: one idea\n"
    settings = Settings(_env_file=None, data_dir=str(data(tmp_path, one)))
    assert gate_b.run(settings) == 1
    assert [c["passed"] for c in the_result(results_dir)["checks"]] == [False]


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


def marks_file(path: Path, ideas: list[tuple[str, list[str]]]) -> Path:
    """A results file in the shape that part 1 writes, already marked: [(expect, marks)]. The
    marks are written as a person may write them, with no space after "mark:"."""
    lines = ["# invented results"]
    for number, (expect, marks) in enumerate(ideas, start=1):
        lines += [f"== idea {number}", "idea: an invented idea"]
        lines += ["expect: none"] if expect == gate_b.NONE else []
        lines.append("")
        for place, mark in enumerate(marks, start=1):
            lines += [f"{place}. Invented Project {place}  (Sample Event)",
                      "   An invented line.", f"   mark:{mark}", ""]  # fmt: skip
    return write(path, "\n".join(lines) + "\n")


def judged(folder: Path, *files: str) -> int:
    return gate_b.judge(Settings(_env_file=None, data_dir=str(folder)), files=files)


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
    marks = {1: ["yes", "no", "n/a"], 2: ["no", "yes", "no"], 3: ["yes", "N/A", "No"]}
    results.write_text(marked(text, marks), encoding="utf-8")
    settings = Settings(_env_file=None, data_dir=str(results.parent.parent))
    assert gate_b.judge(settings) == 0
    saved = the_result(results_dir, "gate_b_marks")
    common = {"file": gate_b.RESULTS, "expect": "close", "results": 3, "not_marked": 0}
    assert saved["measurements"]["ideas"] == [
        common | {"idea": 1, "yes": 1, "n/a": 1, "no": 1, "first_yes_at": 1,
                  "places": {"yes": [1], "n/a": [3], "no": [2]}},
        common | {"idea": 2, "yes": 1, "n/a": 0, "no": 2, "first_yes_at": 2,
                  "places": {"yes": [2], "n/a": [], "no": [1, 3]}},
        common | {"idea": 3, "yes": 1, "n/a": 1, "no": 1, "first_yes_at": 1,
                  "places": {"yes": [1], "n/a": [2], "no": [3]}},
    ]  # fmt: skip


def test_the_marks_fail_when_an_idea_has_no_yes(results: Path, results_dir: Path) -> None:
    text = results.read_text(encoding="utf-8")
    marks = {1: ["yes", "no", "no"], 2: ["no", "n/a", "no"], 3: ["yes", "no", "no"]}
    results.write_text(marked(text, marks), encoding="utf-8")
    settings = Settings(_env_file=None, data_dir=str(results.parent.parent))
    assert gate_b.judge(settings) == 1
    assert failed(the_result(results_dir, "gate_b_marks")) == [
        f'{gate_b.RESULTS}, idea 2: at least one "yes" in the first 10, and every result marked'
    ]


def test_an_idea_that_expects_close_projects_needs_every_mark(
    tmp_path: Path, results_dir: Path
) -> None:
    folder = tmp_path / "data"
    ideas = [("close", ["yes", "no"]), ("close", ["yes", ""]), ("close", ["yes", "no"])]
    marks_file(folder / "by-hand" / "r.txt", ideas)
    assert judged(folder, "r.txt") == 1
    saved = the_result(results_dir, "gate_b_marks")
    assert failed(saved) == [
        'r.txt, idea 2: at least one "yes" in the first 10, and every result marked'
    ]
    assert saved["measurements"]["ideas"][1]["not_marked"] == 1


def test_ideas_that_expect_nothing_close_need_only_their_marks(
    tmp_path: Path, results_dir: Path
) -> None:
    folder = tmp_path / "data"
    ideas = [("close", ["no", "yes"])] * 3 + [("none", ["N/A", "No", "no"])]
    marks_file(folder / "by-hand" / "r.txt", ideas)
    assert judged(folder, "r.txt") == 0
    saved = the_result(results_dir, "gate_b_marks")
    assert saved["measurements"]["ideas"][3] == {
        "file": "r.txt", "idea": 4, "expect": "none", "results": 3, "yes": 0, "n/a": 1, "no": 2,
        "not_marked": 0, "first_yes_at": None, "places": {"yes": [], "n/a": [1], "no": [2, 3]},
    }  # fmt: skip
    marks_file(folder / "by-hand" / "r.txt", [*ideas[:3], ("none", ["n/a", "", "no"])])
    assert judged(folder, "r.txt") == 1
    assert failed(the_result(results_dir, "gate_b_marks")) == [
        "r.txt, idea 4: expects nothing close, and every result is marked"
    ]


def test_ideas_that_expect_nothing_close_do_not_count_for_the_three(
    tmp_path: Path, results_dir: Path
) -> None:
    folder = tmp_path / "data"
    marks_file(folder / "by-hand" / "absent.txt", [("none", ["n/a", "no"])] * 3)
    assert judged(folder, "absent.txt") == 1
    assert failed(the_result(results_dir, "gate_b_marks")) == [
        "at least 3 ideas that expect close projects"
    ]


def test_the_marks_of_two_files_are_read_together(tmp_path: Path, results_dir: Path) -> None:
    folder = tmp_path / "data"
    marks_file(folder / "by-hand" / "absent.txt", [("none", ["n/a", "no"])] * 3)
    marks_file(folder / "by-hand" / "close.txt", [("close", ["yes", "n/a"])] * 3)
    assert judged(folder, "absent.txt", "close.txt") == 0
    ideas = the_result(results_dir, "gate_b_marks")["measurements"]["ideas"]
    assert [(idea["file"], idea["idea"], idea["expect"]) for idea in ideas] == [
        ("absent.txt", 1, "none"), ("absent.txt", 2, "none"), ("absent.txt", 3, "none"),
        ("close.txt", 1, "close"), ("close.txt", 2, "close"), ("close.txt", 3, "close"),
    ]  # fmt: skip


def refused_without_its_words(results_dir: Path, words: str) -> None:
    [check] = the_result(results_dir, "gate_b_marks")["checks"]
    assert check["name"] == "r.txt can be read"
    assert check["detail"].startswith("line ") and words not in check["detail"]


def test_a_mark_that_is_not_one_of_the_three_is_refused(tmp_path: Path, results_dir: Path) -> None:
    folder = tmp_path / "data"
    marks_file(folder / "by-hand" / "r.txt", [("close", ["maybe"])])
    assert judged(folder, "r.txt") == 1
    refused_without_its_words(results_dir, "maybe")


def test_an_expect_line_that_is_not_close_or_none_is_refused(
    tmp_path: Path, results_dir: Path
) -> None:
    folder = tmp_path / "data"
    path = marks_file(folder / "by-hand" / "r.txt", [("close", ["yes"])])
    line = "idea: an invented idea\n"
    text = path.read_text(encoding="utf-8").replace(line, line + "expect: perhaps\n")
    path.write_text(text, encoding="utf-8")
    assert judged(folder, "r.txt") == 1
    refused_without_its_words(results_dir, "perhaps")


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


# --------------------------------------------------------------------- the command line


def test_the_command_line_picks_the_part_and_the_files(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(gate_b, "run", lambda **given: calls.append(("run", given)) or 0)
    monkeypatch.setattr(gate_b, "judge", lambda **given: calls.append(("judge", given)) or 0)
    gate_b.main([])
    gate_b.main(["--keep", "--questions", "q.txt", "--results", "r.txt"])
    gate_b.main(["--marks"])
    gate_b.main(["--marks", "a.txt", "b.txt"])
    assert calls == [
        ("run", {"keep": False, "questions": gate_b.QUESTIONS, "results": gate_b.RESULTS}),
        ("run", {"keep": True, "questions": "q.txt", "results": "r.txt"}),
        ("judge", {"files": [gate_b.RESULTS]}),
        ("judge", {"files": ["a.txt", "b.txt"]}),
    ]
