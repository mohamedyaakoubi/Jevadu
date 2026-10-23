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

from hackathon_memory.check.ledger import read_facts
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


def drawn(conninfo: str, count: int, seed: int = SEED) -> dict[str, set[str]]:
    """`count` repositories whose code was read, drawn with `seed`, each with the IDs that the
    pages and READMEs of its projects name."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT r.url, coalesce(array_agg(DISTINCT h.entity_id) "
            "FILTER (WHERE h.entity_id IS NOT NULL), '{}') "
            "FROM repositories r JOIN projects p ON p.repository_id = r.id "
            "LEFT JOIN hedera_ids h ON h.project_id = p.id "
            "WHERE r.archive_status = 'read' GROUP BY r.url ORDER BY r.url"
        ).fetchall()
    chance = random.Random(seed)  # noqa: S311 - a draw that must be repeatable, not a secret
    chosen = chance.sample(rows, min(count, len(rows)))
    return {url: set(known) for url, known in chosen}


def named_in_collection(conninfo: str) -> set[str]:
    """Every ID that a page or a README of the collection names."""
    with psycopg.connect(conninfo) as conn:
        return {entity for (entity,) in conn.execute("SELECT DISTINCT entity_id FROM hedera_ids")}


def on_the_ledger(entity: str, mirrors: Mapping[str, MirrorNode]) -> set[str]:
    """The networks whose mirror node knows the ID."""
    known = set()
    for network in NETWORKS:
        try:
            if read_facts(mirrors[network], entity).found:
                known.add(network)
        except MirrorError:
            continue
    return known


def measure(
    repositories: Mapping[str, set[str]],
    read: Mapping[str, IdsInCode | None],
    in_collection: set[str],
    ledger: Mapping[str, set[str]],
) -> dict:
    """The numbers of the result file, from what was read."""
    counts: Counter[str] = Counter()
    where: Counter[str] = Counter()
    for url, known in repositories.items():
        found = read.get(url)
        if found is None:
            counts["archives_not_read"] += 1
            continue
        counts["repositories_read"] += 1
        counts["files_read"] += found.files
        new = {entity: kinds for entity, kinds in found.ids.items() if entity not in known}
        counts["repositories_with_an_id_in_code"] += bool(found.ids)
        counts["repositories_with_a_new_id_in_code"] += bool(new)
        real = {entity for entity in new if ledger.get(entity)}
        counts["repositories_with_a_new_id_on_the_ledger"] += bool(real)
        own = {entity for entity in real if entity not in in_collection}
        counts["repositories_with_a_new_own_id_on_the_ledger"] += bool(own)
        counts["ids_in_code"] += len(found.ids)
        counts["new_ids_in_code"] += len(new)
        counts["new_ids_on_the_ledger"] += len(real)
        counts["new_ids_named_elsewhere_in_the_collection"] += len(real - own)
        for kinds in new.values():
            for kind in kinds:
                where[kind] += 1
    return {**dict(sorted(counts.items())), "new_ids_by_kind_of_file": dict(sorted(where.items()))}


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
           for entity in found.ids if entity not in repositories[url]}  # fmt: skip
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
