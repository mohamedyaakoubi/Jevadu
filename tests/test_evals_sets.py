"""The draw of the sets of the tests (design 13.2). Every page here is invented."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.sets import (
    Candidate,
    Found,
    SetError,
    draw,
    draw_test3,
    group_of,
    pages_of,
    thirds,
    write_set,
)


def candidates(per_group: int = 20) -> list[Candidate]:
    found = []
    for size in (100, 1000, 5000):  # three lengths, far apart
        for id_given in (False, True):
            for n in range(per_group):
                page = f"https://example.test/{size}-{id_given}-{n}"
                found.append(Candidate(page, size + n, id_given, "2026-10-10T19:00:00Z", "a" * 64))
    return found


def test_the_lengths_are_cut_at_the_thirds() -> None:
    assert thirds(list(range(9))) == (3, 6)
    cuts = thirds([c.length for c in candidates()])
    assert group_of(Candidate("x", 100, False, "", ""), cuts) == "short, no id given"
    assert group_of(Candidate("x", 5000, True, "", ""), cuts) == "long, an id given"


def test_fifteen_tuning_pages_and_sixty_others_ten_from_each_group() -> None:
    tuning, test1, _ = draw(candidates())
    assert len(tuning) == 15 and len(test1) == 60
    assert not {c["page"] for c in tuning} & {c["page"] for c in test1}
    groups = {c["group"] for c in test1}
    assert len(groups) == 6
    assert all(sum(c["group"] == g for c in test1) == 10 for g in groups)
    assert sorted(sum(c["group"] == g for c in tuning) for g in groups) == [2, 2, 2, 3, 3, 3]


def test_the_same_seed_gives_the_same_draw_and_another_seed_another() -> None:
    first, again = draw(candidates()), draw(list(reversed(candidates())))
    assert first == again
    assert draw(candidates(), seed=7)[1] != first[1]


def test_a_group_that_is_too_small_is_refused() -> None:
    with pytest.raises(SetError, match="fewer than the draw needs"):
        draw(candidates(per_group=11))


def test_a_set_is_written_once_and_read_back_without_page_text(tmp_path: Path) -> None:
    tuning, _, cuts = draw(candidates())
    path = tmp_path / "tuning.json"
    write_set(path, "tuning", tuning, cuts)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["seed"] and record["cases"][0].keys() == {"page", "group", "read_at", "sha256"}
    assert pages_of(path) == [c["page"] for c in tuning]
    with pytest.raises(SetError, match="never drawn again"):
        write_set(path, "tuning", tuning, cuts)


def test_a_wrong_set_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"cases": [{"page": "a"}, {"page": "a"}]}', encoding="utf-8")
    with pytest.raises(SetError, match="the same page twice"):
        pages_of(path)
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(SetError, match="cannot be read"):
        pages_of(path)


def found(per_group: int = 25) -> list[Found]:
    pages = []
    for on_page, in_readme in ((True, True), (False, True), (False, False)):
        for n in range(per_group):
            page = f"https://example.test/{on_page}-{in_readme}-{n}"
            pages.append(Found(page, on_page, in_readme, "2026-10-10T19:00:00Z", "a" * 64))
    return pages


def test_test3_takes_fifteen_twenty_and_fifteen_pages_by_where_the_ids_stand(
    tmp_path: Path,
) -> None:
    cases = draw_test3(found())
    shares = {
        group: sum(c["group"] == group for c in cases) for group in {c["group"] for c in cases}
    }
    assert shares == {"an id on the page": 15, "an id in the README only": 20, "no id found": 15}
    assert draw_test3(list(reversed(found()))) == cases  # the same seed, the same draw
    path = tmp_path / "test3.json"
    write_set(path, "test3", cases, groups="where the ids stand", seed=7)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["groups"] == "where the ids stand" and record["seed"] == 7
    with pytest.raises(SetError, match="fewer than the draw needs"):
        draw_test3(found(per_group=16))
