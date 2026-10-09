"""Which setup steps are done? (design 15)

    python -m hackathon_memory.setup_check

It answers in plain words and never prints a value of .env. A secret is shown as "set" or "empty",
and a key is shown as "a valid key of a kind", never as text. It also says which proofs of Gate A
are blocked by which missing step, and what to do.
"""

from __future__ import annotations

import json
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
    except psycopg.OperationalError:
        # The text of this error can hold connection details, so it is not shown.
        return False, "no answer: start Docker Desktop, then run: docker compose up -d --wait db"


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
    has_project = bool(settings.google_cloud_project.get_secret_value().strip())
    add("3", "GOOGLE_CLOUD_PROJECT", has_project, "set" if has_project else "empty")
    location = settings.google_cloud_location.strip()
    location_ok = location in LOCATIONS
    add(
        "3",
        "GOOGLE_CLOUD_LOCATION",
        location_ok,
        location + ("" if location_ok else f" (use one of: {', '.join(LOCATIONS)})")
        if location
        else "empty (use global)",
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
    prize_list, _, _ = data_paths(settings)
    if prize_list.exists():
        count = sum(
            1
            for raw in prize_list.read_text(encoding="utf-8").splitlines()
            if raw.split("#", 1)[0].strip()
        )
        add("9", "your list of ETHGlobal prize pages", count > 0, f"{count} address(es)")
    else:
        add("9", "your list of ETHGlobal prize pages", False, f"missing: {prize_list}")
    add(
        "-",
        "COLLECT_ETHGLOBAL (the stop switch)",
        True,
        "on" if settings.collect_ethglobal else "off (a live run needs it on, after your yes)",
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
        "Google models": missing("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"),
        "ETHGlobal live run": missing(
            "COLLECTOR_CONTACT_EMAIL", "your list of ETHGlobal prize pages"
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
        "Steps are numbered as in design section 15. Put values in .env, never in a chat.",
        "The ETHGlobal live run also needs two pages saved by hand and the maintainer's yes "
        ".",
    ]
    return "\n".join(out)


def main() -> int:
    env_file = Path(".env")
    settings = Settings()
    print(render(report(settings, root=Path("."), env_file=env_file)))
    return 0 if env_file.exists() else 1


if __name__ == "__main__":
    sys.exit(main())
