"""Is a secret of .env in the git history? (launch gate 8, design rule 9)

    python -m hackathon_memory.secret_scan

Run it from the project folder. It takes the settings that are secrets (the ones held as
SecretStr: keys, tokens, the password, the project name, the contact address) and looks for each
value in three places:

* the files of every commit of every branch and tag. A secret that was deleted later is still
  there, and this is the place where it hides;
* the data of those commits: the messages and the author fields;
* the working folder, with the files that git does not track yet but would pick up. Files that
  .gitignore covers are skipped, and that is the point: .env and the sign-in file live there.

GOOGLE_APPLICATION_CREDENTIALS holds a file NAME, and the name is not a secret. The secret is
inside the file, so the scan looks for the secret fields of the file (private_key, refresh_token,
client_secret) and not for its name. The first version searched the name and reported a leak for
a name that .gitignore must contain.

The scan prints the NAME of each setting and where it was found, never a value. A value goes to
git on the standard input, so it is not in a command line that another program could see. A value
shorter than 8 characters is not searched: it would match ordinary words. A git error stops the
scan: it is never read as "not found".
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import SecretStr

from hackathon_memory.settings import Settings

MIN_LENGTH = 8
SIGN_IN_FILE_SETTING = "GOOGLE_APPLICATION_CREDENTIALS"
# The fields of a Google key file that must stay secret. A service account key has private_key.
# A user login file (gcloud auth application-default login) has refresh_token and client_secret.
SIGN_IN_SECRET_FIELDS = ("private_key", "refresh_token", "client_secret")

HISTORY = "the files of the history"
COMMIT_DATA = "the commit messages or authors"
WORKING_FOLDER = "the working folder"

_GIT_PLACES = (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files\Git\bin\git.exe")
_CHUNK = 100  # commits per call of git grep, to keep the command line short


class ScanError(Exception):
    """The scan could not run. The message never holds a secret value."""


@dataclass(frozen=True)
class ScanResult:
    commits: int
    found: dict[str, list[str]]  # setting name -> the places where its value was found


def find_git() -> str | None:
    return shutil.which("git") or next((g for g in _GIT_PLACES if Path(g).exists()), None)


def _one_line(value: str) -> str:
    """git matches line by line, so a value with line breaks is searched by its longest line.

    A private key has line breaks. Its longest line is a base64 line of 64 characters, which is
    as unique as the whole key. The key header alone would match any fake key in a test.
    """
    text = value.strip()
    return max(text.splitlines(), key=len).strip() if "\n" in text else text


def sign_in_file_values(path: str) -> dict[str, str]:
    """The secret fields of a Google key file, by field name. Empty if the file cannot be read."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    found: dict[str, str] = {}
    for field in SIGN_IN_SECRET_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and len(_one_line(value)) >= MIN_LENGTH:
            found[f"{SIGN_IN_FILE_SETTING} file, field {field}"] = _one_line(value)
    return found


def secret_values(settings: Settings) -> dict[str, str]:
    """name -> value, for the settings that are secrets and are long enough to search."""
    found: dict[str, str] = {}
    for field_name in type(settings).model_fields:
        value = getattr(settings, field_name)
        if not isinstance(value, SecretStr):
            continue
        text = value.get_secret_value().strip()
        if field_name.upper() == SIGN_IN_FILE_SETTING:
            found.update(sign_in_file_values(text) if text else {})
        elif len(_one_line(text)) >= MIN_LENGTH:
            found[field_name.upper()] = _one_line(text)
    return found


def _grep(program: str, root: Path, value: str, revisions: list[str] | None = None) -> bool:
    """Does `git grep` find the value? With no revisions it searches the working folder.

    Exit code 0 is a match, 1 is no match, and anything else is an error. The value is sent on the
    standard input (-f -). check=True is not used: its error text would show the command.
    """
    command = [program, "grep", "-q", "-F", "-f", "-"]
    command += revisions if revisions else ["--untracked"]
    command += ["--"]
    done = subprocess.run(  # noqa: S603
        command, cwd=root, input=(value + "\n").encode("utf-8"), capture_output=True, check=False
    )
    if done.returncode == 0:
        return True
    if done.returncode == 1:
        return False
    raise ScanError(f"git grep failed with exit code {done.returncode}")


def _commit_data(program: str, root: Path) -> bytes:
    """The message, author and committer of every commit, as one block of bytes."""
    done = subprocess.run(  # noqa: S603
        [program, "log", "--all", "--format=%B%n%an%n%ae%n%cn%n%ce%x00"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        raise ScanError(f"git log failed with exit code {done.returncode}")
    return done.stdout


def scan(root: Path, values: dict[str, str], git: str | None = None) -> ScanResult:
    """Where is each value? Values are never printed and never put in an error."""
    program = git or find_git()
    if program is None:
        raise ScanError("git was not found")
    listing = subprocess.run(  # noqa: S603
        [program, "rev-list", "--all"], cwd=root, capture_output=True, text=True, check=False
    )
    if listing.returncode != 0:
        raise ScanError("git cannot list the commits. Is this the project folder?")
    revisions = listing.stdout.split()
    commit_data = _commit_data(program, root) if revisions else b""

    found: dict[str, list[str]] = {}
    for name, value in values.items():
        places: list[str] = []
        chunks = (revisions[i : i + _CHUNK] for i in range(0, len(revisions), _CHUNK))
        if any(_grep(program, root, value, chunk) for chunk in chunks):
            places.append(HISTORY)
        if value.encode("utf-8") in commit_data:
            places.append(COMMIT_DATA)
        if _grep(program, root, value):
            places.append(WORKING_FOLDER)
        found[name] = places
    return ScanResult(commits=len(revisions), found=found)


def main(root: Path | None = None, settings: Settings | None = None) -> int:
    root = root or Path.cwd()
    settings = settings or Settings()
    values = secret_values(settings)
    if not values:
        print("There is no secret value to search for. Run this in the project folder, with .env.")
        return 2
    incomplete = bool(
        settings.google_application_credentials.get_secret_value().strip()
    ) and not any(name.startswith(SIGN_IN_FILE_SETTING) for name in values)
    try:
        result = scan(root, values)
    except ScanError as error:
        print(f"Cannot scan: {error}")
        return 2
    for name, places in result.found.items():
        print(f"  {name}: " + ("FOUND in " + ", ".join(places) if places else "not found"))
    if incomplete:
        print(
            f"  {SIGN_IN_FILE_SETTING}: the file cannot be read, or it holds no secret field, so "
            "its contents were NOT searched."
        )
    print(
        f"Searched {len(values)} secret value(s) in {result.commits} commit(s) of every branch "
        "and tag, in their messages and authors, and in the working folder."
    )
    leaked = [name for name, places in result.found.items() if places]
    if leaked:
        print("RESULT: FOUND " + ", ".join(leaked))
        return 1
    if incomplete:
        print("RESULT: incomplete. Nothing was found, but one check could not run.")
        return 2
    print("RESULT: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
