"""The years of the events that no page dates, typed in by hand (parse/event_years.py)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from hackathon_memory.parse.event_years import EventYearsError, read_event_days, read_event_years


def written(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "event-years.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_each_line_gives_the_site_the_event_and_its_year(tmp_path: Path) -> None:
    path = written(tmp_path, "# typed by hand\n"
                             "hedera.com  hello-future-2024  2024   # the title of the post\n"
                             "\n"
                             "web.archive.org hedera18-hackathon 2018\n")  # fmt: skip
    assert read_event_years(path) == {("hedera.com", "hello-future-2024"): 2024,
                                      ("web.archive.org", "hedera18-hackathon"): 2018}  # fmt: skip


def test_no_file_gives_no_year(tmp_path: Path) -> None:
    assert read_event_years(tmp_path / "missing.txt") == {}


@pytest.mark.parametrize("line", [
    "hedera.com hello-future-2024",  # no year
    "hedera.com hello-future-2024 24",  # not a year of four digits
    "hedera.com hello-future-2024 1999",  # before the hackathons of Hedera
    "Hedera.com hello-future-2024 2024",  # a site in capitals
    "hedera.com hello future 2024",  # a name with a space
])  # fmt: skip
def test_a_line_that_cannot_be_read_stops_the_whole_file(tmp_path: Path, line: str) -> None:
    with pytest.raises(EventYearsError, match="line 1"):
        read_event_years(written(tmp_path, line + "\n"))


def test_an_event_named_twice_stops_the_whole_file(tmp_path: Path) -> None:
    path = written(tmp_path, "hedera.com hedera20 2020\nhedera.com hedera20 2021\n")
    with pytest.raises(EventYearsError, match="a second line"):
        read_event_years(path)


def test_a_line_may_give_the_first_and_the_last_day_of_the_event(tmp_path: Path) -> None:
    path = written(tmp_path, "hedera.com hello-future-2024 2024 2024-07-22 2024-08-20  # the post\n"
                             "hedera.com hedera20 2020\n")  # fmt: skip
    assert read_event_years(path) == {("hedera.com", "hello-future-2024"): 2024,
                                      ("hedera.com", "hedera20"): 2020}  # fmt: skip
    assert read_event_days(path) == {
        ("hedera.com", "hello-future-2024"): (date(2024, 7, 22), date(2024, 8, 20))
    }


@pytest.mark.parametrize("days", ["2024-08-20 2024-07-22", "2024-07-22 2024-13-01",
                                  "2024-07-22 tomorrow", "2024-7-22 2024-08-20"])  # fmt: skip
def test_days_that_do_not_make_a_time_stop_the_whole_file(tmp_path: Path, days: str) -> None:
    path = written(tmp_path, f"hedera.com hello-future-2024 2024 {days}\n")
    with pytest.raises(EventYearsError, match="line 1"):
        read_event_years(path)
    with pytest.raises(EventYearsError, match="line 1"):
        read_event_days(path)
