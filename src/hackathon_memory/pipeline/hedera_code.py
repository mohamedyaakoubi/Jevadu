"""The step that reads where Hedera stands in the code of each repository (design 7.3).

In order:

1. It links each project to its repository, as the README step does.
2. When it may, it reads the archive of every repository that has no saved reading yet
   (collect/github_code.py): two requests for each, to GitHub's API and to its archive host,
   one after the other. A repository that GitHub already said is gone or blocked is not asked
   for again. This is the only part of the step that sends requests.
3. It reads every saved reading and writes what was found for each repository.

Every file of the project's own code is read, with no order of importance and no limit. It is
safe to run again: the archive of a repository is never read twice.
"""

from __future__ import annotations

from collections.abc import Callable

from hackathon_memory.collect.github_code import BLOCKED, GONE, PARTIAL, READ, saved_code
from hackathon_memory.collect.github_facts import FOUND, saved_facts
from hackathon_memory.collect.github_once import AnswersRun
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import Run
from hackathon_memory.parse.hedera_code import (
    FEATURE,
    FORMAT,
    IMPORT,
    MENTION,
    PACKAGE,
    SIGN,
    UNUSED,
)
from hackathon_memory.pipeline.readmes import count_the_fetch, link_repositories

STEP = "hedera_code"
WORDS = {READ: "read whole", PARTIAL: "read in part", GONE: "gone or private",
         BLOCKED: "blocked by GitHub"}  # fmt: skip
KIND_WORDS = {
    PACKAGE: "a Hedera package in a package file",
    IMPORT: "a file that imports a Hedera library",
    FEATURE: "a call to a Hedera service",
    UNUSED: "a Hedera service named only in files that nothing uses",
    SIGN: "a sign of Hedera (its relay, a chain ID, a network of an EVM tool, a system contract "
    "or the mirror node)",
    MENTION: "a file that names Hedera, Hashgraph or Hiero",
}


def read_hedera_code(
    repositories: RepositoryStore,
    raw: RawStore,
    run: Run,
    *,
    fetch: Callable[[list[str]], AnswersRun] | None = None,
    only: set[str] | None = None,
) -> None:
    """Read the missing archives when `fetch` is given, and write what every saved reading
    found; with `only`, of these repositories only. Counts what was done in `run`."""
    wanted = sorted(set(link_repositories(repositories, run).values()))
    if only is not None:
        wanted = [one for one in wanted if one in only]
    if fetch is not None:
        gone = {one for one in wanted if _gone(raw, one)}
        if gone:
            run.counts["archives_not_asked_code_gone"] += len(gone)
        count_the_fetch(fetch([one for one in wanted if one not in gone]), run, "archives")
    for repository in wanted:
        read = saved_code(raw, repository)
        if read is None:
            run.counts["archives_not_read_yet"] += 1
            continue
        repositories.save_code(repository, read)
        run.counts[f"archive_{read.status}"] += 1
        if read.scan is None:
            continue
        if read.scan.files:
            run.counts["files_read"] += read.scan.files
        if read.scan.format < FORMAT:
            run.counts["archives_of_an_older_reader"] += 1
        kinds = {one.kind for one in read.scan.found()}
        for kind in kinds:
            run.counts[f"repositories_with_{kind}"] += 1
        if not kinds:
            run.counts["repositories_with_nothing_found"] += 1
        elif kinds == {MENTION}:
            run.counts["repositories_with_only_a_mention"] += 1


def _gone(raw: RawStore, repository: str) -> bool:
    """GitHub's answer about the repository, saved by the step of the code, says that it is
    gone or blocked."""
    facts = saved_facts(raw, repository)
    return facts is not None and facts.status != FOUND


def hedera_code_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = [
        f"Projects with their code on GitHub: {counts['projects_with_code_on_github']}, in "
        f"{counts['repositories']} repositories."
    ]
    if counts["archives_asked"] or counts["archives_left_for_later"] or counts["archives_failed"]:
        lines.append(
            f"Archives read in this run: {counts['archives_asked']}, of which "
            f"{counts['archives_failed']} failed and are read again by a later run. Left for a "
            f"later run: {counts['archives_left_for_later']}."
        )
    if counts["archives_not_asked_code_gone"]:
        lines.append(
            f"Not asked for, because GitHub said that the repository is gone or blocked: "
            f"{counts['archives_not_asked_code_gone']}."
        )
    lines.append(
        "Repositories: "
        + ", ".join(f"{counts['archive_' + status]} {WORDS[status]}" for status in WORDS)
        + f". Not read yet: {counts['archives_not_read_yet']}. Files of their own code read: "
        f"{counts['files_read']}."
    )
    lines.append("Repositories whose code has:")
    lines.extend(
        f"  {counts['repositories_with_' + kind]:5}  {words}" for kind, words in KIND_WORDS.items()
    )
    lines.append(f"  {counts['repositories_with_only_a_mention']:5}  a mention and nothing else")
    lines.append(f"  {counts['repositories_with_nothing_found']:5}  none of these")
    if counts["archives_of_an_older_reader"]:
        lines.append(
            f"Read by an older version of the reader, so without its newer signs: "
            f"{counts['archives_of_an_older_reader']}."
        )
    return lines
