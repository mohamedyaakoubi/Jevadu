"""The times of the readings of the code (evals/code_times.py). Every archive here is invented."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from evals import code_times
from fakes import archive
from hackathon_memory.collect.github import archive_address, raw_dir
from hackathon_memory.collect.github_code import save_reading
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.parse.hedera_code import LimitedStream, scan_archive
from hackathon_memory.settings import Settings


def save(store: RawStore, name: str, seconds: float | None, status: int = 200) -> None:
    url = archive_address(f"https://github.com/sample-org/{name}")
    if status != 200:
        body = b'{"message": "Not Found"}'
        fetch = FetchResult(url, url, status, body, "application/json", "2026-10-21T20:00:00Z")
        save_reading(store, fetch, None, "TestTool/0.1.0")
        return
    scan = scan_archive(LimitedStream(io.BytesIO(archive({"a.ts": b"let a = 1;\n"})).read))
    fetch = FetchResult(url, url, 200, b"", "application/x-gzip", "2026-10-21T20:00:00Z")
    save_reading(store, fetch, scan, "TestTool/0.1.0", seconds=seconds)


def test_the_readings_that_kept_their_time_are_counted(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    for n, seconds in enumerate([2.0, 3.0, 4.0, 5.0, 40.0]):
        save(store, f"repo-{n}", seconds)
    save(store, "no-time", None)  # read before the time was kept
    save(store, "gone", None, status=404)
    found = code_times.measured(store)
    assert sorted(took for _, took in found) == [2.0, 3.0, 4.0, 5.0, 40.0]
    numbers = code_times.summary(found)
    assert numbers["readings"] == 5
    assert numbers["seconds"] == {"median": 4.0, "p90": 40.0, "p95": 40.0, "largest": 40.0,
                                  "all": 54.0}  # fmt: skip
    assert numbers["under_both_live_limits"] == 4  # 40 seconds is over the limit of 30
    assert code_times.summary([]) == {"readings": 0}


def test_the_result_file_holds_numbers_and_no_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings(_env_file=None, data_dir=str(tmp_path / "data"))
    save(RawStore(raw_dir(settings)), "pebble-pay", 3.5)
    monkeypatch.setattr(code_times, "RESULTS", tmp_path / "results")
    assert code_times.main([], settings) == 0
    assert "Readings: 1. Seconds: median 3.5" in capsys.readouterr().out
    (written,) = (tmp_path / "results").iterdir()
    text = written.read_text(encoding="utf-8")
    assert "pebble" not in text and "sample-org" not in text
    assert json.loads(text)["test"] == "code-times"
