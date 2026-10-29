"""Which setup steps are done? (design 15)

    python -m hackathon_memory.setup_check

It answers in plain words and never prints a value of .env. A secret is shown as "set" or "empty",
and a key is shown as "a valid key of a kind", never as text. It also says which proofs of Gate A
are blocked by which missing step, and what to do.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psycopg

from hackathon_memory.collect.ethglobal import data_paths
from hackathon_memory.hedera.keys import OperatorKeyError, load_operator_key
from hackathon_memory.llm.gemini import LOCATIONS
from hackathon_memory.settings import Settings, SettingsError

PROOFS = {
    "database": "database",
    "hedera-write": "Hedera write",
    "google-models": "Google models",
    "lists": "ETHGlobal lists",
}


@dataclass(frozen=True)
class Line:
    step: str  # the step number of design 15, or "-"
    what: str
    ok: bool
    note: str


def probe_database(settings: Settings) -> tuple[bool, str]:
    try:
        conninfo = settings.database_conninfo()
    except SettingsError:
        return False, "POSTGRES_PASSWORD is empty"
    try:
        with psycopg.connect(conninfo, connect_timeout=3):
            return True, "the local database answers"
    except psycopg.OperationalError as error:
        # The text of this error can hold connection details, so it is read here and never shown.
        if "password authentication failed" in str(error):
            return False, (
                "the database refuses the password in .env: it was created with another one. "
                "To start again (this deletes the local database): docker compose down -v, "
                "then docker compose up -d --wait db"
            )
        return False, "no answer: start Docker Desktop, then run: docker compose up -d --wait db"


_GIT_PLACES = (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files\Gitin\git.exe")


def ignored_by_git(root: Path, path: Path) -> bool | None:
    """True if git ignores `path`, False if it would not, None if git cannot be asked."""
    program = shutil.which("git") or next((g for g in _GIT_PLACES if Path(g).exists()), None)
    if program is None:
        return None
    try:
        done = subprocess.run(  # noqa: S603
            [program, "check-ignore", "--quiet", str(path)],
            cwd=root,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.returncode == 0 if done.returncode in (0, 1) else None


def google_sign_in_note(settings: Settings, root: Path) -> tuple[bool, str]:
    """The Google sign-in file, if one is named. Its path and content are never shown."""
    named = settings.google_application_credentials.get_secret_value().strip()
    if not named:
        return (
            True,
            "empty: the library uses the sign-in of gcloud (gcloud auth application-default login)",
        )
    path = Path(named) if Path(named).is_absolute() else root / named
    if not path.is_file():
        return False, "set, but no file is there"
    try:
        kind = json.loads(path.read_text(encoding="utf-8")).get("type")
    except (OSError, ValueError):
        return False, "set, but the file is not a valid sign-in file"
    if kind not in ("service_account", "authorized_user"):
        return False, "set, but the file is not a service account key or a user login file"
    inside = root.resolve() in path.resolve().parents
    if not inside:
        return True, f"set, a sign-in file of the kind {kind}, outside the project folder"
    ignored = ignored_by_git(root, path)
    where = f"set, a sign-in file of the kind {kind}, INSIDE the project folder"
    if ignored is False:
        return False, f"{where}, and git does NOT ignore it: move it out of the project"
    if ignored is None:
        return True, f"{where} (git could not be asked if it ignores it)"
    return True, f"{where}. Git ignores it. It is better kept outside."


def service_account_key_note(settings: Settings) -> tuple[bool, str, bool]:
    """The key of GOOGLE_SERVICE_ACCOUNT_KEY: whether it reads, and whether one is set. Neither
    the key nor its project is shown."""
    from hackathon_memory.llm.client import GoogleSetupError, service_account_key

    try:
        key = service_account_key(settings)
    except GoogleSetupError:
        return False, "set, but not a service account key in base64", True
    if key is None:
        return True, "empty: the sign-in below is used", False
    named = settings.google_cloud_project.get_secret_value().strip()
    if named and named != key["project_id"]:
        return True, "set; its own project is used, not the one of GOOGLE_CLOUD_PROJECT", True
    return True, "set, a service account key; its own project is used", True


def _hedera_key_note(settings: Settings) -> tuple[bool, str]:
    text = settings.hedera_operator_key.get_secret_value()
    if not text:
        return False, "empty"
    try:
        key = load_operator_key(text)
    except OperatorKeyError as error:
        # A raw key needs the ledger to say its type. That is checked in the proof, not here.
        if "does not say" in str(error):
            return True, "set (a short key: the proof checks its type against the ledger)"
        return False, str(error)
    return True, f"set, a valid {'ED25519' if key.is_ed25519() else 'ECDSA'} key"


def latest_result(root: Path, proof: str) -> tuple[bool, str]:
    files = sorted((root / "proofs" / "results").glob(f"*-{proof}.json"))
    if not files:
        return False, "no result file yet"
    body = json.loads(files[-1].read_text(encoding="utf-8"))
    verdict = "passed" if body.get("passed") else "FAILED"
    return bool(body.get("passed")), f"{verdict} on {body.get('ran_at')} ({files[-1].name})"


def report(
    settings: Settings,
    *,
    root: Path,
    env_file: Path,
    probe: Callable[[Settings], tuple[bool, str]] = probe_database,
) -> list[Line]:
    lines: list[Line] = []

    def add(step: str, what: str, ok: bool, note: str) -> None:
        lines.append(Line(step, what, ok, note))

    add("-", "the file .env", env_file.exists(), "found" if env_file.exists() else "MISSING")
    ok, note = probe(settings)
    add("4", "Docker and the local database", ok, note)

    # step 1: the Hedera test account
    has_id = bool(settings.hedera_operator_id.strip())
    add("1", "HEDERA_OPERATOR_ID", has_id, "set" if has_id else "empty")
    ok, note = _hedera_key_note(settings)
    add("1", "HEDERA_OPERATOR_KEY", ok, note)
    add(
        "1",
        "HEDERA_NETWORK",
        settings.hedera_network == "testnet",
        settings.hedera_network
        + ("" if settings.hedera_network == "testnet" else " (writes are refused: testnet only)"),
    )

    # step 2: the GitHub token (needed from the Check step, not for Gate A)
    has_token = bool(settings.github_token.get_secret_value())
    add("2", "GITHUB_TOKEN", has_token, "set" if has_token else "empty (needed from Phase B)")

    # step 3: Google
    key_ok, key_note, has_key = service_account_key_note(settings)
    has_project = bool(settings.google_cloud_project.get_secret_value().strip())
    add("3", "GOOGLE_CLOUD_PROJECT", has_project or has_key,
        "set" if has_project else "empty: the project of the key below is used" if has_key
        else "empty")  # fmt: skip
    location = settings.google_cloud_location.strip()
    add(
        "3",
        "GOOGLE_CLOUD_LOCATION",
        location == "global",
        location
        + ("" if location == "global" else " (use: global. Gemini 3.1 Pro is offered only there)")
        if location
        else "empty (use: global)",
    )
    add("3", "GOOGLE_SERVICE_ACCOUNT_KEY", key_ok, key_note)
    ok, note = google_sign_in_note(settings, root)
    if has_key:
        note = "not used while GOOGLE_SERVICE_ACCOUNT_KEY is set (" + note + ")"
    add("3", "GOOGLE_APPLICATION_CREDENTIALS", ok, note)
    for layer, model, level in (
        ("rewrite", settings.gemini_rewrite_model, settings.gemini_rewrite_thinking_level),
        ("search", settings.gemini_search_model, settings.gemini_search_thinking_level),
    ):
        offered = LOCATIONS.get(model)
        fits = offered is None or not location or location in offered  # empty is reported above
        add(
            "3",
            f"Gemini {layer} layer",
            fits,
            f"{model}, thinking {level}"
            + ("" if fits else f" (offered only in: {', '.join(offered or ())})"),
        )

    # steps 8 and 9: the collector
    add(
        "8",
        "COLLECTOR_NAME",
        bool(settings.collector_name.strip()),
        settings.collector_name or "empty",
    )
    has_contact = bool(settings.collector_contact_email.get_secret_value().strip())
    add("8", "COLLECTOR_CONTACT_EMAIL", has_contact, "set" if has_contact else "empty")
    page_list = data_paths(settings).page_list
    if page_list.exists():
        count = sum(
            1
            for raw in page_list.read_text(encoding="utf-8").splitlines()
            if raw.split("#", 1)[0].strip()
        )
        add("9", "your list of ETHGlobal project pages", count > 0, f"{count} address(es)")
    else:
        add("9", "your list of ETHGlobal project pages", False, f"missing: {page_list}")
    add(
        "-",
        "COLLECT_ETHGLOBAL (the stop switch)",
        True,
        "on" if settings.collect_ethglobal else "off (a live run needs it on, after your yes)",
    )
    add(
        "-",
        "COLLECT_GITHUB (the stop switch)",
        True,
        "on" if settings.collect_github else "off (reading READMEs needs it on)",
    )

    for proof, name in PROOFS.items():
        ok, note = latest_result(root, proof)
        add("-", f"proof: {name}", ok, note)
    return lines


def blockers(lines: list[Line]) -> dict[str, list[str]]:
    """For each proof, the names of the missing items that block it."""
    ok = {line.what: line.ok for line in lines}

    def missing(*names: str) -> list[str]:
        return [n for n in names if not ok.get(n)]

    return {
        "database": missing("Docker and the local database"),
        "Hedera write": missing("HEDERA_OPERATOR_ID", "HEDERA_OPERATOR_KEY"),
        "Google models": missing(
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_CLOUD_LOCATION",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "Gemini rewrite layer",
            "Gemini search layer",
        ),
        "ETHGlobal live run": missing(
            "COLLECTOR_CONTACT_EMAIL", "your list of ETHGlobal project pages"
        ),
    }


def render(lines: list[Line]) -> str:
    out = ["Setup check. No value of .env is printed.", ""]
    width = max(len(line.what) for line in lines)
    for line in lines:
        mark = "ok     " if line.ok else "TO DO  "
        step = f"step {line.step}" if line.step != "-" else "      "
        out.append(f"  {mark}{step:7} {line.what:<{width}}  {line.note}")
    out += ["", "What blocks each proof of Gate A:"]
    for proof, missing in blockers(lines).items():
        out.append(
            f"  {proof}: "
            + ("nothing is missing" if not missing else "needs " + ", ".join(missing))
        )
    out += [
        "",
        "How to get each value, one by one: README.md (its steps are numbered like these).",
        "Put values in .env, never in a chat.",
        "The ETHGlobal live run also needs the maintainer's yes for the pages on the list.",
    ]
    return "\n".join(out)


def main() -> int:
    env_file = Path(".env")
    settings = Settings()
    print(render(report(settings, root=Path("."), env_file=env_file)))
    return 0 if env_file.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
