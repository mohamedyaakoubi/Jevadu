"""Promises to the sites that are about the repository, not about one module (design 5.7).

"The collected pages stay on my laptop. No text taken from a collected page is committed."
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GIT_PLACES = [
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Program Files\Git\bin\git.exe",
]


def git(*args: str) -> subprocess.CompletedProcess[str]:
    program = shutil.which("git") or next((p for p in GIT_PLACES if Path(p).exists()), None)
    if program is None:
        # Not a skip: a skipped test would look like a pass.
        pytest.fail("git was not found, so this promise cannot be checked")
    return subprocess.run(  # noqa: S603
        [program, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


def test_the_data_folder_and_the_secrets_file_are_ignored_by_git() -> None:
    for path in ("data/raw/ethglobal.com/page.html", "data/by-hand/x.txt", ".env"):
        result = git("check-ignore", "--quiet", path)
        assert result.returncode == 0, f"git does not ignore {path}"


def test_no_file_of_the_data_folder_is_tracked_by_git() -> None:
    result = git("ls-files", "--", "data")
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_the_example_settings_file_holds_no_value() -> None:
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        allowed = {
            "HEDERA_NETWORK": "testnet",
            "COLLECTOR_NAME": "HackathonMemory-research",
            "COLLECT_ETHGLOBAL": "off",
        }
        assert value == allowed.get(name, ""), f"{name} has a value in .env.example"


def test_every_sample_page_says_that_it_is_invented() -> None:
    # A real page saved here by mistake would put other people's text into git.
    samples = [p for p in (ROOT / "tests" / "samples").rglob("*") if p.is_file()]
    assert samples, "no sample files found"
    for path in samples:
        start = path.read_text(encoding="utf-8")[:400]
        assert "INVENTED" in start, f"{path.relative_to(ROOT)} does not start with INVENTED"
