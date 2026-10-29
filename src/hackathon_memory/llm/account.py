"""Switch the Google account that the models use, in one command (29 October 2026).

    python -m hackathon_memory.llm.account switch               sign in with gcloud (a browser
                                                                opens), then make the key
    python -m hackathon_memory.llm.account switch --project ID  when the account sees more than
                                                                one project
    python -m hackathon_memory.llm.account switch --no-login    with the account gcloud already
                                                                uses

In the project of the account, it:

1. turns on the two APIs it needs, IAM and Vertex AI (free);
2. makes the service account `jevadu-gemini` once, with one role, Vertex AI User: it may call the
   models, and nothing else;
3. makes a new key for it, deletes its older keys, and writes the new key on one line into .env:
   GOOGLE_SERVICE_ACCOUNT_KEY, its JSON in base64, which llm/client.py reads with its project;
4. asks Google for the size of a short text in tokens with the new key: a free call that proves
   the key works before anything else depends on it.

No model is asked to write, so nothing is paid. The key is never printed.

gcloud's commands, as its own help gives them (Google Cloud SDK, 29 October 2026): auth login;
projects list; services enable; iam service-accounts describe and create; projects
add-iam-policy-binding with --condition=None; iam service-accounts keys create, list and delete.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # the project folder
NAME = "jevadu-gemini"
ROLE = "roles/aiplatform.user"
APIS = ("iam.googleapis.com", "aiplatform.googleapis.com")
KEY_SETTING = "GOOGLE_SERVICE_ACCOUNT_KEY"
PROJECT_SETTING = "GOOGLE_CLOUD_PROJECT"
# A new service account takes a moment to be known everywhere in Google; its first role waits.
TRIES, PAUSE_SECONDS = 6, 10.0

Run = Callable[[Sequence[str]], str]


class AccountError(Exception):
    """What stopped the switch, in plain words, with no secret in them."""


def gcloud_program() -> str:
    """The gcloud of this computer: on the PATH, or where the Windows installer puts it."""
    found = shutil.which("gcloud")
    if found:
        return found
    windows = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Cloud SDK" / (
        "google-cloud-sdk") / "bin" / "gcloud.cmd"  # fmt: skip
    if windows.is_file():
        return str(windows)
    raise AccountError("gcloud was not found. Install the Google Cloud CLI first.")


def gcloud_runner(program: str) -> Run:
    """Run one gcloud command with no question asked; its output, or AccountError with the last
    line of what gcloud said."""

    def run(args: Sequence[str]) -> str:
        done = subprocess.run([program, *args, "--quiet"], capture_output=True, text=True,  # noqa: S603
                              check=False)  # fmt: skip
        if done.returncode != 0:
            said = [line.strip() for line in done.stderr.splitlines() if line.strip()]
            last = said[-1] if said else f"exit {done.returncode}"
            raise AccountError(f"gcloud {' '.join(args[:3])} failed: {last}")
        return done.stdout

    return run


def keep_line(env: Path, name: str, value: str) -> None:
    """Write `name=value` into .env, in place of an older line of that name; the rest is kept."""
    lines = env.read_text(encoding="utf-8").splitlines() if env.is_file() else []
    kept: list[str] = []
    for line in lines:
        if line.startswith(f"{name}="):
            if f"{name}={value}" not in kept:
                kept.append(f"{name}={value}")  # where the first one was; any other is dropped
            continue
        kept.append(line)
    if f"{name}={value}" not in kept:
        kept.append(f"{name}={value}")
    env.write_text("\n".join(kept) + "\n", encoding="utf-8")


def choose_project(run: Run, asked: str | None) -> str:
    """The project to use: the one asked for, or the only one that the account sees."""
    seen = run(["projects", "list", "--format=value(projectId)"]).split()
    if asked:
        if asked not in seen:
            raise AccountError("This account does not see the project that was named.")
        return asked
    if len(seen) == 1:
        return seen[0]
    if not seen:
        raise AccountError("This account sees no Google Cloud project: make one in the console.")
    raise AccountError(f"This account sees {len(seen)} projects: name one with --project ID "
                       f"({', '.join(seen)}).")  # fmt: skip


def make_key(run: Run, project: str, *, sleep: Callable[[float], None] = time.sleep) -> dict:
    """The service account that may only call Vertex AI in `project`, made once, and a new key of
    it; its older keys are deleted. Returns the key."""
    email = f"{NAME}@{project}.iam.gserviceaccount.com"
    run(["config", "set", "project", project])
    run(["services", "enable", *APIS, f"--project={project}"])
    try:
        run(["iam", "service-accounts", "describe", email, f"--project={project}"])
    except AccountError:
        run(["iam", "service-accounts", "create", NAME, "--display-name=Jevadu: Gemini only",
             f"--project={project}"])  # fmt: skip
    for attempt in range(TRIES):
        try:
            run(["projects", "add-iam-policy-binding", project,
                 f"--member=serviceAccount:{email}", f"--role={ROLE}", "--condition=None",
                 "--format=none"])  # fmt: skip
            break
        except AccountError:
            if attempt == TRIES - 1:
                raise
            sleep(PAUSE_SECONDS)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "key.json"
        run(["iam", "service-accounts", "keys", "create", str(path), f"--iam-account={email}",
             f"--project={project}"])  # fmt: skip
        key = json.loads(path.read_text(encoding="utf-8"))
    older = run(["iam", "service-accounts", "keys", "list", f"--iam-account={email}",
                 "--managed-by=user", "--format=value(name)", f"--project={project}"])  # fmt: skip
    for name in older.split():
        key_id = name.rsplit("/", 1)[-1]
        if key_id != key["private_key_id"]:
            run(["iam", "service-accounts", "keys", "delete", key_id, f"--iam-account={email}",
                 f"--project={project}"])  # fmt: skip
    return key


def line_of(key: dict) -> str:
    """The key on one line, as GOOGLE_SERVICE_ACCOUNT_KEY holds it."""
    return base64.b64encode(json.dumps(key).encode("utf-8")).decode("ascii")


def proven(settings_of: Callable[[], object], *, tries: int = TRIES,
           sleep: Callable[[float], None] = time.sleep) -> bool:  # fmt: skip
    """Whether the key of the settings is accepted by Vertex AI: the count of tokens of a short
    text, which costs nothing (finops/meter.py lets it pass uncounted). A new key may take a
    minute before Google accepts it."""
    from hackathon_memory.finops.meter import metered_client

    for attempt in range(tries):
        try:
            settings = settings_of()
            counted = metered_client(settings, "account_check")
            counted.models.count_tokens(model=settings.gemini_search_model, contents="Jevadu")  # type: ignore[attr-defined]
            return True
        except Exception:  # noqa: BLE001  (any refusal: the key is not accepted yet)
            if attempt < tries - 1:
                sleep(PAUSE_SECONDS)
    return False


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m hackathon_memory.llm.account")
    parser.add_argument("command", choices=["switch"])
    parser.add_argument("--project")
    parser.add_argument("--no-login", action="store_true")
    arguments = parser.parse_args(argv)
    env = ROOT / ".env"
    try:
        program = gcloud_program()
        if not arguments.no_login:
            subprocess.run([program, "auth", "login"], check=False)  # noqa: S603  (a browser opens)
        run = gcloud_runner(program)
        project = choose_project(run, arguments.project)
        print(f"Project: {project}. Making the key that may only call Vertex AI...")
        key = make_key(run, project)
        keep_line(env, KEY_SETTING, line_of(key))
        keep_line(env, PROJECT_SETTING, project)
    except AccountError as error:
        print(error)
        return 1
    from hackathon_memory.settings import Settings

    print(f"Written into .env: {KEY_SETTING} (not shown) and {PROJECT_SETTING}. Checking it...")
    if not proven(Settings):
        print("Google does not accept the new key yet. Wait a few minutes, then run: "
              "python -m hackathon_memory.setup_check")  # fmt: skip
        return 1
    print("The models now use this account, through a key that may only call Vertex AI.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
