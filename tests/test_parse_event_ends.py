"""The file of the ends of events, typed in by hand. Every name of an event here is invented."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from hackathon_memory.parse.event_ends import FILE_NAME, EventEndsError, read_event_ends


def written(tmp_path: Path, text: str) -> Path:
    path = tmp_path / FILE_NAME
    path.write_text(text, encoding="utf-8")
    return path


def test_no_file_gives_no_end(tmp_path: Path) -> None:
    assert read_event_ends(tmp_path / FILE_NAME) == {}


def test_each_line_gives_an_event_and_its_last_day(tmp_path: Path) -> None:
    path = written(
        tmp_path,
        "# The last day of each event.\n"
        "\n"
        "sample-event   2026-03-08   # the page of the event, read on 11 October 2026\n"
        "other2024 2024-11-17\n",
    )
    assert read_event_ends(path) == {
        "sample-event": date(2026, 3, 8),
        "other2024": date(2024, 11, 17),
    }


@pytest.mark.parametrize(
    "line",
    [
        "sample-event",  # no day
        "sample-event 2026-3-8",  # not written as YYYY-MM-DD
        "sample-event 08/03/2026",
        "sample-event 2026-03-08 2026-03-09",  # two days
        "Sample-Event 2026-03-08",  # the short names of the site are in small letters
        "sample event 2026-03-08",
    ],
)
def test_a_line_of_another_shape_is_refused_with_its_number(tmp_path: Path, line: str) -> None:
    path = written(tmp_path, f"# a comment\n{line}\n")
    with pytest.raises(EventEndsError, match=f"{FILE_NAME}, line 2: expected the short name"):
        read_event_ends(path)


def test_a_day_that_is_not_in_the_calendar_is_refused(tmp_path: Path) -> None:
    with pytest.raises(EventEndsError, match="line 1: 2026-02-30 is not a day of the calendar"):
        read_event_ends(written(tmp_path, "sample-event 2026-02-30\n"))


def test_an_event_with_two_lines_is_refused(tmp_path: Path) -> None:
    path = written(tmp_path, "sample-event 2026-03-08\nsample-event 2026-03-09\n")
    with pytest.raises(EventEndsError, match="line 2: the event sample-event has a second line"):
        read_event_ends(path)
