"""The words that the steps of a check show about their usual time (web/evidence.py), read from
dated result files; the files here are invented."""

from __future__ import annotations

import json
from pathlib import Path

from hackathon_memory.web.evidence import check_notes


def write(folder: Path, name: str, body: dict) -> None:
    (folder / name).write_text(json.dumps(body), encoding="utf-8")


def test_a_slow_step_says_its_usual_time_from_the_newest_measure(tmp_path: Path) -> None:
    assert check_notes(tmp_path) == {}  # no measure, no words
    seconds = {"median": 3.0, "p90": 9.0, "p95": 12.0}
    write(tmp_path, "20261020T000000Z-code-times.json", {"made_on": "2026-10-20",
                                                          "seconds": seconds})  # fmt: skip
    newer = {"median": 3.45, "p90": 10.8, "p95": 17.7}
    write(tmp_path, "20261021T190159Z-code-times.json", {"made_on": "2026-10-21",
                                                          "seconds": newer})  # fmt: skip
    per_project = {"median": 1.39, "p90": 6.98}
    write(tmp_path, "20261023T045317Z-history-times.json",
          {"made_on": "2026-10-23", "seconds_per_project": per_project})  # fmt: skip
    notes = check_notes(tmp_path)
    assert notes["code"] == ("Code that the tool never read takes about 3.5 seconds, and under "
                             "17.7 seconds for 95 of 100 repositories (measured on 21 October "
                             "2026).")  # fmt: skip
    assert notes["history"] == ("For the IDs of one project this takes about 1.4 seconds, and "
                                "under 7.0 seconds for 9 of 10 (measured on 23 October "
                                "2026).")  # fmt: skip
