"""The step that reads the README of each project's code (design 7.3).

In order:

1. It takes the link to the code of each project from the database, and keeps the links to a
   repository on GitHub, each in one spelling. Projects with the same code share its README.
2. When it may, it asks GitHub for every README that is not saved yet (collect/github_readmes.py).
   This is the only part of the step that sends requests.
3. It reads every saved README: what GitHub answered, and the Hedera ids in the text. The ids are
   kept for each project of the repository, marked as found in the README. The check step then
   judges them like the ids of a page.

It is safe to run again. A README is never asked for twice. The ids of a project are written
again only when they changed.
"""

from __future__ import annotations

from collections.abc import Callable

from hackathon_memory.collect.github import repository_of
from hackathon_memory.collect.github_once import AnswersRun
from hackathon_memory.collect.github_readmes import FOUND, STATUSES, saved_readme
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import Run
from hackathon_memory.parse.hedera_ids import find_ids

STEP = "readmes"


def link_repositories(repositories: RepositoryStore, run: Run) -> dict[int, str]:
    """Link each project to the repository on GitHub that its link to the code names, and give
    the link of the repository of each project."""
    of_project: dict[int, str] = {}
    for project_id, link in repositories.code_links().items():
        repository = repository_of(link)
        if repository is None:
            run.counts["code_not_on_github"] += 1
        else:
            of_project[project_id] = repository
    run.counts["projects_with_code_on_github"] += len(of_project)
    run.counts["repositories"] += len(set(of_project.values()))
    repositories.link(of_project)
    return of_project


def count_the_fetch(done: AnswersRun, run: Run, what: str) -> None:
    """Count in `run` what a run that asked GitHub did. A stop is named as a problem."""
    for key, value in (
        (f"{what}_asked", done.asked),
        (f"{what}_failed", done.failed),
        (f"{what}_left_for_later", done.left_for_later),
    ):
        if value:
            run.counts[key] += value
    if done.stopped:
        run.problem("GitHub", done.stopped)


def read_readmes(
    repositories: RepositoryStore,
    projects: ProjectStore,
    raw: RawStore,
    run: Run,
    *,
    fetch: Callable[[list[str]], AnswersRun] | None = None,
) -> None:
    """Link each project to its repository, ask for the READMEs that are missing when `fetch` is
    given, and keep the ids of every saved README. Counts what was done in `run`."""
    of_project = link_repositories(repositories, run)
    wanted = sorted(set(of_project.values()))
    if fetch is not None:
        count_the_fetch(fetch(wanted), run, "readmes")

    readmes = {}
    for repository in wanted:
        readme = saved_readme(raw, repository)
        if readme is None:
            run.counts["readmes_not_asked_yet"] += 1
            continue
        readmes[repository] = readme
        repositories.save_readme(repository, readme)
        run.counts[f"readme_{readme.status}"] += 1
        for key in ("words_hidden", "team_parts_cut", "team_lines_cut", "ids_in_the_cut"):
            if readme.taken_out.get(key):
                run.counts[f"taken_out_{key}"] += int(readme.taken_out[key])

    for project_id, repository in sorted(of_project.items()):
        readme = readmes.get(repository)
        if readme is None:
            continue  # not asked yet: nothing is known, and nothing is changed
        ids = find_ids(readme.text) if readme.status == FOUND else []
        if projects.save_readme_ids(project_id, ids):
            run.counts["projects_whose_readme_ids_changed"] += 1
        if ids:
            run.counts["projects_with_an_id_in_the_readme"] += 1
            run.counts["ids_in_readmes"] += len(ids)


def readme_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = [
        f"Projects with their code on GitHub: {counts['projects_with_code_on_github']}, in "
        f"{counts['repositories']} repositories. Code somewhere else: "
        f"{counts['code_not_on_github']}."
    ]
    if counts["readmes_asked"] or counts["readmes_left_for_later"] or counts["readmes_failed"]:
        lines.append(
            f"Asked of GitHub in this run: {counts['readmes_asked']} README(s), of which "
            f"{counts['readmes_failed']} failed. Left for a later run: "
            f"{counts['readmes_left_for_later']}."
        )
    words = {
        "found": "found",
        "none": "no README",
        "blocked": "blocked by GitHub",
        "not_text": "not text",
    }
    lines.append(
        "READMEs: "
        + ", ".join(f"{counts['readme_' + status]} {words[status]}" for status in STATUSES)
        + f". Not asked for yet: {counts['readmes_not_asked_yet']}."
    )
    lines.append(
        f"Taken out before saving: {counts['taken_out_words_hidden']} handles, addresses and "
        f"links of people, and {counts['taken_out_team_parts_cut']} parts about the team "
        f"({counts['taken_out_team_lines_cut']} lines, with "
        f"{counts['taken_out_ids_in_the_cut']} Hedera ids in them)."
    )
    lines.append(
        f"Projects with a Hedera id in their README: "
        f"{counts['projects_with_an_id_in_the_readme']} ({counts['ids_in_readmes']} ids). "
        f"Projects whose README ids changed in this run: "
        f"{counts['projects_whose_readme_ids_changed']}."
    )
    return lines
