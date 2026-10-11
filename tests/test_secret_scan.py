"""The scan for the secrets of .env finds a planted secret, in every place, and nothing else.

Every secret in this file is built from parts, so that the file itself holds no secret shape.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hackathon_memory import secret_scan
from hackathon_memory.secret_scan import (
    COMMIT_DATA,
    HISTORY,
    WORKING_FOLDER,
    ScanError,
    find_git,
    main,
    scan,
    secret_values,
    sign_in_file_values,
)
from hackathon_memory.settings import Settings

PLANTED = "planted-" + "x" * 24
OTHER = "another-" + "z" * 24
ADDRESS = "someone-test" + "@" + "example.test"
KEY_BODY = "planted-key-body-" + "y" * 40  # one line of a private key
REFRESH = "planted-refresh-" + "r" * 30
CLIENT_SECRET = "planted-client-" + "c" * 20


def git_in(folder: Path, *args: str) -> None:
    program = find_git()
    if program is None:
        pytest.fail("git was not found, so the scan cannot be tested")  # not a skip
    subprocess.run(  # noqa: S603
        [program, "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        cwd=folder,
        capture_output=True,
        check=True,
    )


def repo_with(tmp_path: Path, text: str, later: str | None = None) -> Path:
    git_in(tmp_path, "init", "-q")
    (tmp_path / "file.txt").write_text(text, encoding="utf-8")
    git_in(tmp_path, "add", "file.txt")
    git_in(tmp_path, "commit", "-q", "-m", "first")
    if later is not None:
        (tmp_path / "file.txt").write_text(later, encoding="utf-8")
        git_in(tmp_path, "commit", "-q", "-am", "second")
    return tmp_path


def sign_in_file(folder: Path, name: str = "login.json") -> Path:
    path = folder / name
    path.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "a-public-client-id",
                "client_secret": CLIENT_SECRET,
                "refresh_token": REFRESH,
            }
        ),
        encoding="utf-8",
    )
    return path


# --- where a value is found


def test_a_planted_secret_is_found_in_the_history_and_in_the_folder(tmp_path: Path) -> None:
    root = repo_with(tmp_path, f"password = {PLANTED}\n")
    result = scan(root, {"POSTGRES_PASSWORD": PLANTED})
    assert result.found == {"POSTGRES_PASSWORD": [HISTORY, WORKING_FOLDER]}
    assert result.commits == 1


def test_a_secret_that_was_deleted_later_is_still_in_the_history(tmp_path: Path) -> None:
    # Removing a secret from a file does not remove it from the history. That is the point.
    root = repo_with(tmp_path, f"token = {PLANTED}\n", later="token = removed\n")
    assert scan(root, {"GITHUB_TOKEN": PLANTED}).found == {"GITHUB_TOKEN": [HISTORY]}


def test_a_clean_history_is_clean(tmp_path: Path) -> None:
    root = repo_with(tmp_path, "nothing secret here\n")
    assert scan(root, {"POSTGRES_PASSWORD": PLANTED}).found == {"POSTGRES_PASSWORD": []}


def test_each_value_is_judged_on_its_own(tmp_path: Path) -> None:
    root = repo_with(tmp_path, f"a = {PLANTED}\n")
    found = scan(root, {"ONE": PLANTED, "TWO": OTHER}).found
    assert found["ONE"] and not found["TWO"]


def test_a_secret_in_a_commit_message_is_found(tmp_path: Path) -> None:
    root = repo_with(tmp_path, "clean\n")
    git_in(root, "commit", "--allow-empty", "-q", "-m", f"a note with {PLANTED} in it")
    assert scan(root, {"X": PLANTED}).found == {"X": [COMMIT_DATA]}


def test_an_address_in_an_author_field_is_found(tmp_path: Path) -> None:
    # The contact address of the collector may also be the address of the git author.
    root = repo_with(tmp_path, "clean\n")
    git_in(root, "commit", "--allow-empty", "-q", "-m", "m", f"--author=Someone <{ADDRESS}>")
    assert scan(root, {"COLLECTOR_CONTACT_EMAIL": ADDRESS}).found == {
        "COLLECTOR_CONTACT_EMAIL": [COMMIT_DATA]
    }


def test_a_file_git_would_pick_up_is_found_and_an_ignored_file_is_not(tmp_path: Path) -> None:
    root = repo_with(tmp_path, "clean\n")
    (root / ".gitignore").write_text("ignored.env\n", encoding="utf-8")
    (root / "ignored.env").write_text(f"KEY={PLANTED}\n", encoding="utf-8")  # like .env
    (root / "loose.txt").write_text(f"KEY={OTHER}\n", encoding="utf-8")  # not yet tracked
    found = scan(root, {"IGNORED": PLANTED, "LOOSE": OTHER}).found
    assert found == {"IGNORED": [], "LOOSE": [WORKING_FOLDER]}


def test_an_empty_repository_has_nothing_to_find(tmp_path: Path) -> None:
    git_in(tmp_path, "init", "-q")
    result = scan(tmp_path, {"X": PLANTED})
    assert (result.commits, result.found) == (0, {"X": []})


# --- an error is never "not found"


@pytest.mark.parametrize("failing", ["rev-list", "log", "grep"])
def test_a_git_error_is_never_read_as_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    root = repo_with(tmp_path, f"x = {PLANTED}\n")
    real = subprocess.run

    def run(command: list[str], *args: object, **kwargs: object) -> object:
        if failing in command:
            return subprocess.CompletedProcess(command, 128, b"", b"fatal: invented failure")
        return real(command, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ScanError) as error:
        scan(root, {"X": PLANTED})
    assert PLANTED not in str(error.value)


# --- which settings, and the sign-in file


def test_only_the_settings_that_are_secrets_are_searched() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password=PLANTED,
        hedera_operator_id="0.0.10941897",  # public on the ledger: not searched
        gemini_rewrite_model="gemini-3.1-pro-preview",  # a model name: not searched
        github_token="short",  # too short to search without matching ordinary words
        collector_contact_email=ADDRESS,
        google_application_credentials="no-such-file-for-this-test.json",  # a name, not a secret
    )
    values = secret_values(settings)
    assert values == {"POSTGRES_PASSWORD": PLANTED, "COLLECTOR_CONTACT_EMAIL": ADDRESS}


def test_the_secret_fields_of_a_login_file_are_searched_and_not_its_name(tmp_path: Path) -> None:
    path = sign_in_file(tmp_path)
    assert sign_in_file_values(str(path)) == {
        "GOOGLE_APPLICATION_CREDENTIALS file, field client_secret": CLIENT_SECRET,
        "GOOGLE_APPLICATION_CREDENTIALS file, field refresh_token": REFRESH,
    }
    settings = Settings(_env_file=None, google_application_credentials=str(path))
    assert secret_values(settings) == sign_in_file_values(str(path))


def test_a_private_key_is_searched_by_its_longest_line(tmp_path: Path) -> None:
    # The header is built from parts: a whole one in this file would trip the secret-shape test
    # of tests/test_promises.py, which reads every tracked file.
    pem = "-----BEGIN " + "PRIVATE KEY-----\n" + KEY_BODY + "\n-----END " + "PRIVATE KEY-----\n"
    path = tmp_path / "service.json"
    path.write_text(json.dumps({"type": "service_account", "private_key": pem}), encoding="utf-8")
    assert sign_in_file_values(str(path)) == {
        "GOOGLE_APPLICATION_CREDENTIALS file, field private_key": KEY_BODY
    }


@pytest.mark.parametrize("content", ["not json at all", "[1, 2, 3]", '{"type": "authorized_user"}'])
def test_a_file_without_secret_fields_gives_no_values(tmp_path: Path, content: str) -> None:
    path = tmp_path / "odd.json"
    path.write_text(content, encoding="utf-8")
    assert sign_in_file_values(str(path)) == {}


def test_a_missing_sign_in_file_gives_no_values(tmp_path: Path) -> None:
    assert sign_in_file_values(str(tmp_path / "missing.json")) == {}


def test_a_sign_in_file_that_was_committed_is_found(tmp_path: Path) -> None:
    root = tmp_path
    git_in(root, "init", "-q")
    path = sign_in_file(root)
    git_in(root, "add", path.name)
    git_in(root, "commit", "-q", "-m", "oops")
    found = scan(root, sign_in_file_values(str(path))).found
    assert all(places == [HISTORY, WORKING_FOLDER] for places in found.values())
    assert len(found) == 2


def test_a_sign_in_file_that_git_ignores_is_not_found(tmp_path: Path) -> None:
    root = repo_with(tmp_path, "clean\n")
    (root / ".gitignore").write_text("login.json\n", encoding="utf-8")
    path = sign_in_file(root)
    found = scan(root, sign_in_file_values(str(path))).found
    assert all(places == [] for places in found.values())
    assert len(found) == 2


# --- the command prints names, never values


def test_the_command_prints_a_name_and_never_a_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo_with(tmp_path, f"password = {PLANTED}\n")
    code = main(root=root, settings=Settings(_env_file=None, postgres_password=PLANTED))
    out = capsys.readouterr().out
    assert code == 1
    assert "POSTGRES_PASSWORD: FOUND in" in out
    assert "RESULT: FOUND POSTGRES_PASSWORD" in out
    assert PLANTED not in out  # the control: the value is in the repository, and it is not shown


def test_the_command_says_clean_when_nothing_is_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo_with(tmp_path, "clean\n")
    code = main(root=root, settings=Settings(_env_file=None, postgres_password=PLANTED))
    out = capsys.readouterr().out
    assert code == 0
    assert "RESULT: clean" in out
    assert "1 commit(s)" in out
    assert PLANTED not in out


def test_the_command_does_not_pass_when_there_is_nothing_to_search(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo_with(tmp_path, "clean\n")
    assert main(root=root, settings=Settings(_env_file=None)) == 2
    assert "RESULT" not in capsys.readouterr().out


def test_an_unreadable_sign_in_file_makes_the_result_incomplete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo_with(tmp_path, "clean\n")
    settings = Settings(
        _env_file=None,
        postgres_password=PLANTED,
        google_application_credentials="no-such-file-for-this-test.json",
    )
    code = main(root=root, settings=settings)
    out = capsys.readouterr().out
    assert code == 2
    assert "NOT searched" in out
    assert "RESULT: incomplete" in out
    assert "RESULT: clean" not in out


def test_the_command_stops_when_git_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo_with(tmp_path, f"x = {PLANTED}\n")

    def broken(*_args: object, **_kwargs: object) -> object:
        raise ScanError("invented failure")

    monkeypatch.setattr(secret_scan, "scan", broken)
    code = main(root=root, settings=Settings(_env_file=None, postgres_password=PLANTED))
    assert code == 2
    assert "Cannot scan: invented failure" in capsys.readouterr().out


def test_the_real_history_of_this_project_holds_no_planted_value() -> None:
    root = Path(__file__).resolve().parents[1]
    assert scan(root, {"PLANTED": PLANTED}).found == {"PLANTED": []}
