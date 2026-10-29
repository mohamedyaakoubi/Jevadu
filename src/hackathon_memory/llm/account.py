"""Switch the Google account that the models use, in one command (29 October 2026).

    python -m hackathon_memory.llm.account switch               sign in once in a browser, for
                                                                gcloud and for the models of this
                                                                computer together
    python -m hackathon_memory.llm.account switch --project ID  when the account sees more than
                                                                one project
    python -m hackathon_memory.llm.account switch --no-login    when gcloud and its sign-in for
                                                                programs already use the account

In the project of the account, it:

1. turns on the APIs it needs, IAM, IAM Credentials, Security Token Service and Vertex AI (free);
2. makes the service account `jevadu-gemini` once, with one role, Vertex AI User: it may call the
   models, and nothing else;
3. for the public copy on Vercel (--vercel-team): makes once the workload identity pool `vercel`
   and its provider, which trust the tokens of that Vercel team, and lets the production of the
   Vercel project `jevadu` act as `jevadu-gemini`. No key is made: the organizations that Google
   makes today forbid keys of service accounts, and a token of Vercel lives two hours;
4. writes the project into .env, and, after the sign-in, an empty GOOGLE_APPLICATION_CREDENTIALS,
   so that the models of this computer use the sign-in that gcloud has just made;
5. asks Google for the size of a short text in tokens with that sign-in: a free call that proves
   it works before anything depends on it.

No model is asked to write, so nothing is paid.

gcloud's commands, as its own help gives them (Google Cloud SDK 2026.05.29, read 29 October
2026): auth login --update-adc; projects list and describe; services enable; iam
service-accounts describe, create and add-iam-policy-binding; projects add-iam-policy-binding
with --condition=None; iam workload-identity-pools create and describe, and their providers
create-oidc, update-oidc and describe. The values of the federation come from Vercel's own guide
(vercel.com/docs/oidc/gcp, read 29 October 2026).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # the project folder
NAME = "jevadu-gemini"
ROLE = "roles/aiplatform.user"
APIS = ("iam.googleapis.com", "iamcredentials.googleapis.com", "sts.googleapis.com",
        "aiplatform.googleapis.com")  # fmt: skip
POOL = PROVIDER = "vercel"
VERCEL_PROJECT = "jevadu"
PROJECT_SETTING = "GOOGLE_CLOUD_PROJECT"
SIGN_IN_SETTING = "GOOGLE_APPLICATION_CREDENTIALS"
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


def exists(run: Run, args: Sequence[str]) -> bool:
    """Whether gcloud describes the thing: a refusal is taken as "not there", and the command
    that makes it then says what is wrong."""
    try:
        run(args)
    except AccountError:
        return False
    return True


def make_account(run: Run, project: str, *, sleep: Callable[[float], None] = time.sleep) -> str:
    """The service account that may only call Vertex AI in `project`, made once; its address."""
    email = f"{NAME}@{project}.iam.gserviceaccount.com"
    run(["config", "set", "project", project])
    run(["services", "enable", *APIS, f"--project={project}"])
    if not exists(run, ["iam", "service-accounts", "describe", email, f"--project={project}"]):
        run(["iam", "service-accounts", "create", NAME, "--display-name=Jevadu: Gemini only",
             f"--project={project}"])  # fmt: skip
    for attempt in range(TRIES):
        try:
            run(["projects", "add-iam-policy-binding", project,
                 f"--member=serviceAccount:{email}", f"--role={ROLE}", "--condition=None",
                 "--format=none"])  # fmt: skip
            return email
        except AccountError:
            if attempt == TRIES - 1:
                raise
            sleep(PAUSE_SECONDS)
    return email


def trust_vercel(run: Run, project: str, team: str, email: str) -> str:
    """The pool and provider that trust the tokens of the Vercel `team`, made once, and the right
    of the production of the Vercel project `jevadu` to act as `email`. Returns the audience that
    the host signs in with (GOOGLE_FEDERATION_AUDIENCE)."""
    number = run(["projects", "describe", project, "--format=value(projectNumber)"]).strip()
    where = ["--location=global", f"--project={project}"]
    if not exists(run, ["iam", "workload-identity-pools", "describe", POOL, *where]):
        run(["iam", "workload-identity-pools", "create", POOL, "--display-name=Vercel", *where])
    issuer, audience = f"https://oidc.vercel.com/{team}", f"https://vercel.com/{team}"
    trust = [f"--workload-identity-pool={POOL}", f"--issuer-uri={issuer}",
             f"--allowed-audiences={audience}", "--attribute-mapping=google.subject=assertion.sub",
             *where]  # fmt: skip
    provider = ["iam", "workload-identity-pools", "providers"]
    if exists(run, [*provider, "describe", PROVIDER, f"--workload-identity-pool={POOL}", *where]):
        run([*provider, "update-oidc", PROVIDER, *trust])  # the team may have changed
    else:
        run([*provider, "create-oidc", PROVIDER, "--display-name=Vercel", *trust])
    subject = f"owner:{team}:project:{VERCEL_PROJECT}:environment:production"
    member = (f"principal://iam.googleapis.com/projects/{number}/locations/global/"
              f"workloadIdentityPools/{POOL}/subject/{subject}")  # fmt: skip
    run(["iam", "service-accounts", "add-iam-policy-binding", email,
         "--role=roles/iam.workloadIdentityUser", f"--member={member}", "--condition=None",
         f"--project={project}", "--format=none"])  # fmt: skip
    return (f"//iam.googleapis.com/projects/{number}/locations/global/workloadIdentityPools/"
            f"{POOL}/providers/{PROVIDER}")  # fmt: skip


def proven(settings_of: Callable[[], object], *, tries: int = TRIES,
           sleep: Callable[[float], None] = time.sleep) -> bool:  # fmt: skip
    """Whether Vertex AI accepts the sign-in of the settings: the count of tokens of a short
    text, which costs nothing (finops/meter.py lets it pass uncounted). A new role may take a
    minute before Google applies it."""
    from hackathon_memory.finops.meter import metered_client

    for attempt in range(tries):
        try:
            settings = settings_of()
            counted = metered_client(settings, "account_check")
            counted.models.count_tokens(model=settings.gemini_search_model, contents="Jevadu")  # type: ignore[attr-defined]
            return True
        except Exception:  # noqa: BLE001  (any refusal: the sign-in is not accepted yet)
            if attempt < tries - 1:
                sleep(PAUSE_SECONDS)
    return False


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m hackathon_memory.llm.account")
    parser.add_argument("command", choices=["switch"])
    parser.add_argument("--project")
    parser.add_argument("--no-login", action="store_true")
    parser.add_argument("--vercel-team")
    arguments = parser.parse_args(argv)
    env = ROOT / ".env"
    try:
        program = gcloud_program()
        if not arguments.no_login:  # a browser opens; gcloud and the models sign in together
            subprocess.run([program, "auth", "login", "--update-adc"], check=False)  # noqa: S603
        run = gcloud_runner(program)
        project = choose_project(run, arguments.project)
        print(f"Project: {project}. Making the service account that may only call Vertex AI...")
        email = make_account(run, project)
        if arguments.vercel_team:
            audience = trust_vercel(run, project, arguments.vercel_team, email)
            print("Vercel may now act as it, with no key. On the host:")
            print(f"  GOOGLE_FEDERATION_AUDIENCE={audience}")
            print(f"  GOOGLE_FEDERATION_ACCOUNT={email}")
        keep_line(env, PROJECT_SETTING, project)
        if not arguments.no_login:
            keep_line(env, SIGN_IN_SETTING, "")  # gcloud's own sign-in, just made
    except AccountError as error:
        print(error)
        return 1
    from hackathon_memory.settings import Settings

    print(f"Written into .env: {PROJECT_SETTING}. Checking the sign-in with a free call...")
    if not proven(Settings):
        print("Google does not accept the sign-in yet. Wait a few minutes, then run: "
              "python -m hackathon_memory.setup_check")  # fmt: skip
        return 1
    print("The models of this computer now use this account.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
