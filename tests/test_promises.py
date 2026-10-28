"""Promises to the sites that are about the repository, not about one module (design 5.7).

"The collected pages stay on my laptop. No text taken from a collected page is committed."
"""

from __future__ import annotations

import re
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
            "COLLECT_GITHUB": "off",
            "COLLECT_AFRICA_WINNERS": "off",
            "COLLECT_HEDERA_POSTS": "off",
            # model names and levels, chosen by the maintainer: not secrets
            "GEMINI_REWRITE_MODEL": "gemini-3.1-pro-preview",
            "GEMINI_REWRITE_THINKING_LEVEL": "HIGH",
            "GEMINI_SEARCH_MODEL": "gemini-3.8-flash",
            "GEMINI_SEARCH_THINKING_LEVEL": "LOW",
            "GEMINI_EMBEDDING_MODEL": "gemini-embedding-2",
            # how old an answer is before it is asked again, and the background switch (design 7.3)
            "REFRESH_AFTER_HOURS": "24",
            "REFRESH_IN_BACKGROUND": "off",
        }
        assert value == allowed.get(name, ""), f"{name} has a value in .env.example"


def test_every_sample_page_says_that_it_is_invented() -> None:
    # A real page saved here by mistake would put other people's text into git.
    samples = [p for p in (ROOT / "tests" / "samples").rglob("*") if p.is_file()]
    assert samples, "no sample files found"
    for path in samples:
        start = path.read_text(encoding="utf-8")[:400]
        assert "INVENTED" in start, f"{path.relative_to(ROOT)} does not start with INVENTED"


# ---------------------------------------------------------------- no secret in the repository

SECRET_SHAPES = {
    "a private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "a Google refresh token": re.compile(r"1//0[0-9A-Za-z_-]{40,}"),
    "a Google access token": re.compile(r"ya29\.[0-9A-Za-z_-]{20,}"),
    "a Google API key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "a GitHub token": re.compile(
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36,}|github_pat_[0-9A-Za-z_]{40,}"
    ),
    "a Hedera Ed25519 private key": re.compile(r"302e020100300506032b657004220420[0-9a-fA-F]{64}"),
    "a Hedera ECDSA private key": re.compile(
        r"3030020100300706052b8104000a04220420[0-9a-fA-F]{64}"
    ),
}


def find_secret_shapes(text: str) -> list[str]:
    """The names of the secret shapes that appear in `text`. Never the secret itself."""
    return [name for name, shape in SECRET_SHAPES.items() if shape.search(text)]


def test_the_scanner_finds_planted_secrets() -> None:
    # The fakes are built here, piece by piece, so this file holds no secret shape itself.
    planted = {
        "a private key block": "-----BEGIN " + "PRIVATE KEY-----\nabc\n",
        "a Google refresh token": "1//0" + "a" * 50,
        "a Google access token": "ya29." + "b" * 30,
        "a Google API key": "AIza" + "c" * 35,
        "a GitHub token": "ghp_" + "d" * 40,
        "a Hedera Ed25519 private key": "302e020100300506032b657004220420" + "e" * 64,
        "a Hedera ECDSA private key": "3030020100300706052b8104000a04220420" + "f" * 64,
    }
    for name, text in planted.items():
        assert name in find_secret_shapes(f"before {text} after"), name
    assert find_secret_shapes("a normal sentence, 0.0.12346 and a short 302e0201 prefix") == []


def test_no_tracked_file_holds_something_that_looks_like_a_secret() -> None:
    """Launch gate 8: no secret is in the repository. This runs on every push."""
    listing = git("ls-files", "-z")
    assert listing.returncode == 0
    offenders: list[str] = []
    for name in filter(None, listing.stdout.split("\0")):
        path = ROOT / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        found = find_secret_shapes(path.read_bytes().decode("utf-8", errors="ignore"))
        offenders.extend(f"{name}: {kind}" for kind in found)
    assert offenders == []  # the names of files and kinds, never the secrets


def test_google_sign_in_files_are_ignored_by_git() -> None:
    names = [
        "application_default_credentials.json",
        "client_secret_1234.json",
        "my-key.json",
        "service-account-prod.json",
        "private.pem",
        "something-credentials.json",
    ]
    for name in names:
        assert git("check-ignore", "--quiet", name).returncode == 0, f"git does not ignore {name}"
