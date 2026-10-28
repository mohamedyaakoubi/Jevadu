"""How often the code of a repository names Hedera IDs that its page and its README do not
(design 7.1 and 7.3).

    python -m evals.ids_in_code [--repositories N]

The tool finds Hedera IDs on the project page and in the README. This measure asks whether the
code holds more. It draws N repositories of the collection whose code was read (40 when not
given, with a fixed seed), downloads the archive of each again from GitHub (two requests, with the
tool's name, its pace and its count of requests), reads every file of the project's own code by
the rules of the code reader (parse/hedera_code.py), and finds the Hedera IDs of each file by the
rules of the page (parse/hedera_ids.py). For each ID that the project's page and README do not
name, the public mirror node is asked what it is, on both networks.

An ID that the ledger knows proves little: almost every small number exists as something, and the
code also names things that many teams use, such as a public token. So the measure also counts
the IDs that the proof rule would weigh (check/proof.py): named by no other project of the
collection and by no other repository of the draw, and made on the ledger inside the window of
the event of the repository's project. A repository with such an ID and no proof today is one
that reading the IDs of the code would give a proof.

Nothing of the code is kept. It writes evals/results/<UTC time>-ids-in-code.json, in numbers
only: no ID, no name of a repository and no path.
"""

from __future__ import annotations

import io
import json
import random
import sys
import tarfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import psycopg

from hackathon_memory.check.ledger import LedgerFacts, read_facts
from hackathon_memory.check.proof import PROOF_FOUND, Window, window_of
from hackathon_memory.collect import github
from hackathon_memory.collect.github import archive_address
from hackathon_memory.hedera.mirror import MIRROR_URLS, MirrorError, MirrorNode
from hackathon_memory.parse.hedera_code import (
    EXAMPLE_ENV,
    MAX_FILE_BYTES,
    LimitedStream,
    ReadLimit,
    _own_path,
    _wanted,
)
from hackathon_memory.parse.hedera_ids import find_ids
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"
REPOSITORIES = 40
SEED = 20261023  # the day of the first draw, so that a run again reads the same repositories
MAX_BYTES = 50_000_000  # the limit of a check (design 7.3)
SECONDS = 60.0
NETWORKS = ("testnet", "mainnet")
SETTINGS_SUFFIXES = frozenset({".json", ".yaml", ".yml", ".toml"})


@dataclass(frozen=True)
class Drawn:
    """One repository of the draw: the IDs that the pages and READMEs of its projects name, the
    windows of their events (none while an end is not known), and whether one of them has a
    proof today."""

    known: frozenset[str] = frozenset()
    windows: tuple[Window, ...] = ()
    proof_now: bool = False


@dataclass
class IdsInCode:
    """The Hedera IDs that one archive names, by the kind of file they stand in."""

    files: int = 0
    ids: dict[str, set[str]] = field(default_factory=dict)  # an ID: the kinds of file


def kind_of_file(path: str) -> str:
    """Where an ID stands: an example of settings, a test, a settings file, or source code."""
    name = PurePosixPath(path).name.lower()
    parts = {part.lower() for part in PurePosixPath(path).parts[:-1]}
    if name in EXAMPLE_ENV:
        return "example_settings"
    if parts & {"test", "tests", "__tests__", "spec", "e2e"} or ".test." in name:
        return "test"
    if PurePosixPath(name).suffix in SETTINGS_SUFFIXES:
        return "settings"
    return "source"


def scan_ids(stream: LimitedStream) -> IdsInCode:
    """Read a .tar.gz archive, file after file, by the rules of the code reader, and keep the
    Hedera IDs that each file names, with the kind of the file."""
    found = IdsInCode()
    try:
        with tarfile.open(fileobj=io.BufferedReader(stream, 1 << 16), mode="r|gz") as archive:
            for member in archive:
                if not member.isfile() or member.size > MAX_FILE_BYTES:
                    continue
                path = _own_path(member.name)
                if path is None or not _wanted(path):
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                found.files += 1
                text = handle.read().decode("utf-8", errors="ignore")
                for one in find_ids(text):
                    found.ids.setdefault(one.entity_id, set()).add(kind_of_file(path))
    except (tarfile.TarError, EOFError, OSError, ReadLimit):
        pass  # what was read before the archive broke off, or its limit, still counts
    return found


def drawn(conninfo: str, count: int, seed: int = SEED) -> dict[str, Drawn]:
    """`count` repositories whose code was read, drawn with `seed`, each with the IDs that the
    pages and READMEs of its projects name, the windows of their events and their proof."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT r.url, coalesce(array_agg(DISTINCT h.entity_id) "
            "FILTER (WHERE h.entity_id IS NOT NULL), '{}') "
            "FROM repositories r JOIN projects p ON p.repository_id = r.id "
            "LEFT JOIN hedera_ids h ON h.project_id = p.id "
            "WHERE r.archive_status = 'read' GROUP BY r.url ORDER BY r.url"
        ).fetchall()
        chance = random.Random(seed)  # noqa: S311 - a draw that must be repeatable, not a secret
        chosen = dict(chance.sample(rows, min(count, len(rows))))
        events: dict[str, list] = {}
        for url, starts_at, ends_on, proof in conn.execute(
            "SELECT r.url, e.starts_at, e.ends_on, p.proof_status FROM repositories r "
            "JOIN projects p ON p.repository_id = r.id JOIN events e ON e.id = p.event_id "
            "WHERE r.url = ANY(%s)", (list(chosen),)
        ).fetchall():  # fmt: skip
            events.setdefault(url, []).append((window_of(starts_at, ends_on), proof))
    return {url: Drawn(frozenset(known),
                       tuple(window for window, _ in events.get(url, []) if window is not None),
                       any(proof == PROOF_FOUND for _, proof in events.get(url, [])))
            for url, known in chosen.items()}  # fmt: skip


def named_in_collection(conninfo: str) -> set[str]:
    """Every ID that a page or a README of the collection names."""
    with psycopg.connect(conninfo) as conn:
        return {entity for (entity,) in conn.execute("SELECT DISTINCT entity_id FROM hedera_ids")}


def on_the_ledger(entity: str, mirrors: Mapping[str, MirrorNode]) -> dict[str, LedgerFacts]:
    """What the mirror node of each network that knows the ID says about it."""
    known = {}
    for network in NETWORKS:
        try:
            facts = read_facts(mirrors[network], entity)
        except MirrorError:
            continue
        if facts.found:
            known[network] = facts
    return known


def made_inside(facts: Mapping[str, LedgerFacts], windows: Sequence[Window]) -> bool:
    """True if the thing was made on a network inside one of the windows."""
    return any(window.holds(one.created_at) for one in facts.values() for window in windows)


def measure(
    repositories: Mapping[str, Drawn],
    read: Mapping[str, IdsInCode | None],
    in_collection: set[str],
    ledger: Mapping[str, Mapping[str, LedgerFacts]],
) -> dict:
    """The numbers of the result file, from what was read."""
    counts: Counter[str] = Counter()
    where: Counter[str] = Counter()
    what: Counter[str] = Counter()
    codes = Counter(entity for found in read.values() if found is not None for entity in found.ids)
    for url, repository in repositories.items():
        found = read.get(url)
        if found is None:
            counts["archives_not_read"] += 1
            continue
        counts["repositories_read"] += 1
        counts["repositories_with_a_proof_now"] += repository.proof_now
        counts["repositories_with_no_event_window"] += not repository.windows
        counts["files_read"] += found.files
        new = {entity: kinds for entity, kinds in found.ids.items()
               if entity not in repository.known}  # fmt: skip
        counts["repositories_with_an_id_in_code"] += bool(found.ids)
        counts["repositories_with_a_new_id_in_code"] += bool(new)
        real = {entity for entity in new if ledger.get(entity)}
        counts["repositories_with_a_new_id_on_the_ledger"] += bool(real)
        own = {entity for entity in real if entity not in in_collection}
        counts["repositories_with_a_new_own_id_on_the_ledger"] += bool(own)
        alone = {entity for entity in own if codes[entity] == 1}
        inside = {entity for entity in alone if made_inside(ledger[entity], repository.windows)}
        counts["repositories_with_a_new_id_made_in_the_window"] += bool(inside)
        counts["repositories_that_would_gain_a_proof"] += bool(inside) and not repository.proof_now
        counts["ids_in_code"] += len(found.ids)
        counts["new_ids_in_code"] += len(new)
        counts["new_ids_on_the_ledger"] += len(real)
        counts["new_ids_named_elsewhere_in_the_collection"] += len(real - own)
        counts["new_ids_in_the_code_of_two_drawn_repositories"] += len(own - alone)
        counts["new_ids_made_in_the_window"] += len(inside)
        for kinds in new.values():
            for kind in kinds:
                where[kind] += 1
        for entity in real:
            for kind in sorted({facts.kind or "unknown" for facts in ledger[entity].values()}):
                what[kind] += 1
    return {**dict(sorted(counts.items())), "new_ids_by_kind_of_file": dict(sorted(where.items())),
            "new_ids_on_the_ledger_by_kind": dict(sorted(what.items()))}  # fmt: skip


def main(argv: Sequence[str], settings: Settings | None = None) -> int:
    count = REPOSITORIES
    if len(argv) == 2 and argv[0] == "--repositories" and argv[1].isdigit() and int(argv[1]) > 0:
        count = int(argv[1])
    elif argv:
        print("usage: python -m evals.ids_in_code [--repositories N]")
        return 2
    settings = settings or Settings()
    conninfo = settings.database_conninfo()
    repositories = drawn(conninfo, count)
    client = github.github_client(settings)
    read: dict[str, IdsInCode | None] = {}
    for url in repositories:
        _, found = client.read_archive(archive_address(url), scan_ids, max_bytes=MAX_BYTES,
                                       seconds=SECONDS)  # fmt: skip
        read[url] = found
    mirrors = {name: MirrorNode(name) for name in MIRROR_URLS if name in NETWORKS}
    new = {entity for url, found in read.items() if found is not None
           for entity in found.ids if entity not in repositories[url].known}  # fmt: skip
    ledger = {entity: on_the_ledger(entity, mirrors) for entity in sorted(new)}
    numbers = measure(repositories, read, named_in_collection(conninfo), ledger)
    now = datetime.now(UTC)
    result = {"test": "ids-in-code", "made_on": now.date().isoformat(),
              "made_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "seed": SEED,
              "repositories_drawn": len(repositories), **numbers}  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-ids-in-code.json"
    path.write_bytes((json.dumps(result, indent=1) + "\n").encode("utf-8"))
    print(json.dumps(result, indent=1))
    print(f"Written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
