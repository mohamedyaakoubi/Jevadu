"""Test 2, the maintainer's ideas: the draw of the projects and the reading of the ideas. Every
project and every idea here is invented."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.test2 import ideas
from evals.test2.ideas import IdeasError, Project, copies, drawn, read, write


def projects(count: int) -> list[Project]:
    return [
        Project(
            f"https://ethglobal.com/showcase/p{n}-x1y2z",
            f"Pebble {n}",
            f"Pay a street vendor number {n} with a coin.",
        )
        for n in range(count)
    ]


def with_idea(path: Path, number: int, words: str) -> None:
    """Writes an idea into the block of one project, as the maintainer would."""
    head, mark, rest = path.read_text(encoding="utf-8").partition(f"== {number}\n")
    text = head + mark + rest.replace("idea:", f"idea: {words}", 1)
    path.write_text(text, encoding="utf-8")


def test_the_draw_is_repeatable_and_leaves_out_the_pages_of_other_tests() -> None:
    every = projects(40)
    left_out = {every[0].page, every[1].page}
    one = drawn(every, left_out)
    assert len(one) == ideas.DRAWN and drawn(list(reversed(every)), left_out) == one
    assert not left_out & {p.page for p in one}
    few = projects(31)
    with pytest.raises(IdeasError):
        drawn(few, {few[0].page, few[1].page})


def test_the_file_is_written_once_and_its_ideas_are_read_back(tmp_path: Path) -> None:
    path = write(tmp_path, projects(3))
    assert "Pick 15 of them" in path.read_text(encoding="utf-8")
    with pytest.raises(IdeasError):
        write(tmp_path, projects(3))
    with_idea(path, 1, "a coin box for people who sell on the street")
    with_idea(path, 2, "pay a street vendor number 1 quickly")
    found = read(path)
    assert [(idea.number, idea.copied) for idea in found] == [(1, False), (2, True)]
    assert found[0].page == "https://ethglobal.com/showcase/p0-x1y2z"


def test_an_idea_copies_its_project_with_four_words_in_a_row() -> None:
    source = "Pebble: Pay a street vendor with a coin."
    assert copies("I want to pay a street vendor online", source)
    assert not copies("a coin box for people who sell on the street", source)


def test_check_counts_the_ideas_and_names_the_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from hackathon_memory.settings import Settings

    folder = tmp_path / "data" / "evals" / "test2"
    path = write(folder, projects(2))
    with_idea(path, 1, "pay a street vendor number 0 now")
    settings = Settings(_env_file=None, data_dir=str(tmp_path / "data"))
    monkeypatch.setattr("hackathon_memory.settings.Settings", lambda: settings)
    assert ideas.main(["check"]) == 1
    printed = capsys.readouterr().out
    assert "1 idea(s) written, 15 wanted." in printed and "from their project: 1" in printed
    assert "street vendor" not in printed  # numbers only, no words of a page or an idea
