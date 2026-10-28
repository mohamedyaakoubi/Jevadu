"""The step that reads the facts of the code of each project (design 7.3).

In order:

1. It links each project to its repository, as the README step does.
2. When it may, it asks GitHub for the facts of every repository that has none saved yet
   (collect/github_facts.py). This is the only part of the step that sends requests.
3. It reads every saved answer and writes the facts of each repository: when it was made, when
   code was last pushed to it, whether it is archived or a fork, and its main language. The
   life rule reads them (design 7.4).

It is safe to run again. The facts of a repository are never asked for twice.
"""

from __future__ import annotations

from collections.abc import Callable

from hackathon_memory.collect.github_facts import STATUSES, saved_facts
from hackathon_memory.collect.github_once import AnswersRun
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import Run
from hackathon_memory.pipeline.readmes import count_the_fetch, link_repositories

STEP = "code"
WORDS = {"found": "found", "gone": "gone or private", "blocked": "blocked by GitHub"}


def read_code(
    repositories: RepositoryStore,
    raw: RawStore,
    run: Run,
    *,
    fetch: Callable[[list[str]], AnswersRun] | None = None,
    only: set[str] | None = None,
) -> None:
    """Ask for the missing facts when `fetch` is given, and write the facts of every repository
    whose answer is saved; with `only`, of these repositories only. Counts what was done in
    `run`."""
    wanted = sorted(set(link_repositories(repositories, run).values()))
    if only is not None:
        wanted = [one for one in wanted if one in only]
    if fetch is not None:
        count_the_fetch(fetch(wanted), run, "facts")
    for repository in wanted:
        facts = saved_facts(raw, repository)
        if facts is None:
            run.counts["facts_not_asked_yet"] += 1
            continue
        repositories.save_facts(repository, facts)
        run.counts[f"repository_{facts.status}"] += 1
        if facts.archived:
            run.counts["archived"] += 1
        if facts.fork:
            run.counts["forks"] += 1
        if facts.current_url and facts.current_url != repository:
            run.counts["moved_or_renamed"] += 1


def code_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = [
        f"Projects with their code on GitHub: {counts['projects_with_code_on_github']}, in "
        f"{counts['repositories']} repositories."
    ]
    if counts["facts_asked"] or counts["facts_left_for_later"] or counts["facts_failed"]:
        lines.append(
            f"Asked of GitHub in this run: {counts['facts_asked']}, of which "
            f"{counts['facts_failed']} failed. Left for a later run: "
            f"{counts['facts_left_for_later']}."
        )
    lines.append(
        "Repositories: "
        + ", ".join(f"{counts['repository_' + status]} {WORDS[status]}" for status in STATUSES)
        + f". Not asked for yet: {counts['facts_not_asked_yet']}."
    )
    lines.append(
        f"Archived: {counts['archived']}. Forks of another repository: {counts['forks']}. "
        f"Moved or renamed since the page named them: {counts['moved_or_renamed']}."
    )
    return lines
