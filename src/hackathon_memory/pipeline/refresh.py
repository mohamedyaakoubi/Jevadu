"""The step `refresh`: read again what changes after an event (design 7.3, 25 October 2026).

    python -m hackathon_memory.pipeline refresh              ask again for what is a day old
    python -m hackathon_memory.pipeline refresh --hours 6    ... six hours old
    python -m hackathon_memory.pipeline refresh --repos 50   at most 50 requests of each kind

A repository lives on after its event, and so do the Hedera IDs of a project. In order:

1. GitHub, for every repository of the collection: what was never asked, then the facts, the
   README and the newest commit whose newest answer is older than the age, each with the ETag of
   that answer, so that GitHub answers 304 when nothing changed (collect/answers.py).
2. The code of every repository whose newest commit is not the commit of its newest reading,
   read again whole (collect/github_code.py).
3. With no request: the READMEs and their Hedera IDs, the facts of the code, and what the code
   says about Hedera are written again from the newest answers of the repositories answered.
4. The ledger: the IDs of the code, then every ID, from the table when its answer is younger than
   the age, else from the mirror node; the proof rule judges them again.
5. The histories of the own IDs: those never read or read before the depth of use (design 7.5),
   whole, and the new transactions of the others, from their newest event on.
6. What the calls of the own contracts reached among Hedera's system contracts (design 7.5): a
   contract never read, or read while its time was open and longer ago than the age; with a
   limit of requests (a round of the website), CONTRACTS_A_ROUND at most.
7. What changed for each project, compared with what the tool held before the reading, is kept
   (db/readings.py): always for a reading by the button of a card, else only when something did.

GitHub is asked only when the switch COLLECT_GITHUB is on; without it, steps 3 to 6 run on what
is saved. The pages of the sites that were asked for permission are never read again (design
5.7). It is safe to stop and to run again: an answer is saved as it comes, and a later run asks
only for what is older than the age. The website runs the same work in the background, and for
one project at the press of "Read again now" (web/refresher.py).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from hackathon_memory.check.readings import changes_of
from hackathon_memory.collect.answers import AgainRun, Answers
from hackathon_memory.collect.github import GitHubClient
from hackathon_memory.collect.github_code import fetch_code, read_new_commits
from hackathon_memory.collect.github_commits import fetch_versions, versions_again
from hackathon_memory.collect.github_facts import FOUND, facts_again, fetch_facts, saved_facts
from hackathon_memory.collect.github_once import AnswersRun
from hackathon_memory.collect.github_readmes import fetch_readmes, readmes_again
from hackathon_memory.db.code_ids import CodeIdStore
from hackathon_memory.db.contract_calls import ContractCallStore
from hackathon_memory.db.history import HistoryStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.readings import BUTTON, REFRESH, ReadingStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorNode
from hackathon_memory.pipeline import (
    check_ids,
    code,
    code_ids,
    contract_calls,
    hedera_code,
    history,
    readmes,
)

STEP = "refresh"
AGE = timedelta(hours=24)  # REFRESH_AFTER_HOURS in .env (design 7.3)
KINDS = ("facts", "readmes", "versions", "archives")
# The steps of a reading, said as each starts (web/refresher.py shows them on the card).
GITHUB, CODE, LEDGER, HISTORIES = "github", "code", "ledger", "histories"
CONTRACTS = "contracts"
STEPS = (GITHUB, CODE, LEDGER, HISTORIES, CONTRACTS)
# The contracts read in one round of the website: up to a hundred requests each, so about five
# hundred requests, two minutes at the mirror node's pace.
CONTRACTS_A_ROUND = 5
Step = Callable[[str], None]


def _now() -> datetime:
    return datetime.now(UTC)


def _quiet(_step: str) -> None:
    """A reading that says nothing of its steps: the step `refresh` and the rounds."""


def _count_first(run: Run, kind: str, done: AnswersRun) -> None:
    if done.asked:
        run.counts[f"{kind}_asked_first"] += done.asked
    if done.stopped:
        run.problem("GitHub", done.stopped)


def _count(run: Run, kind: str, done: AgainRun) -> None:
    numbers = {"asked": done.asked, "unchanged": done.unchanged, "changed": len(done.changed),
               "fresh": done.fresh, "failed": done.failed,
               "left_for_later": done.left_for_later}  # fmt: skip
    for name, value in numbers.items():
        if value:
            run.counts[f"{kind}_{name}"] += value
    if done.stopped:
        run.problem("GitHub", done.stopped)


def _found(answers: Answers, repository: str) -> bool:
    facts = saved_facts(answers, repository)
    return facts is not None and facts.status == FOUND


def ask_github(
    client: GitHubClient,
    answers: Answers,
    wanted: list[str],
    run: Run,
    *,
    collector: str,
    older_than: timedelta,
    now: Callable[[], datetime],
    limit: int | None,
    step: Step = _quiet,
) -> set[str]:
    """Steps 1 and 2: ask for what is missing and for what is old. Returns the repositories that
    GitHub answered about, whose answers the steps of step 3 write again."""
    answered: set[str] = set()
    for kind, first in (("facts", fetch_facts), ("readmes", fetch_readmes),
                        ("versions", fetch_versions)):  # fmt: skip
        if kind != "facts":  # a README and a commit only for code that is there
            wanted = [one for one in wanted if _found(answers, one)]
        done = first(client, answers, wanted, collector=collector, limit=limit)
        _count_first(run, kind, done)
        if done.asked:
            answered.update(wanted)  # which ones is not said: the steps read all of them
        again = {"facts": facts_again, "readmes": readmes_again, "versions": versions_again}[kind]
        later = again(client, answers, wanted, collector=collector, older_than=older_than,
                      now=now, limit=limit)  # fmt: skip
        _count(run, kind, later)
        answered.update(later.answered)
    step(CODE)
    new_code = read_new_commits(client, answers, wanted, collector=collector, limit=limit)
    _count(run, "archives", new_code)
    answered.update(new_code.changed)
    missing = fetch_code(client, answers, wanted, collector=collector, limit=limit)
    _count_first(run, "archives", missing)
    if missing.asked:
        answered.update(wanted)
    return answered


def refresh(
    conninfo: str,
    answers: Answers,
    client: GitHubClient | None,
    mirrors: Mapping[str, MirrorNode],
    run: Run,
    *,
    collector: str,
    older_than: timedelta = AGE,
    limit: int | None = None,
    projects: set[int] | None = None,
    now: Callable[[], datetime] = _now,
    source: str = REFRESH,
    step: Step = _quiet,
) -> None:
    """Read again what is older than `older_than`, for the whole collection or for `projects`
    only, and count what was done in `run`. With no client, GitHub is not asked. `source` names
    who reads (db/readings.py), and `step` hears each step as it starts."""
    readings = ReadingStore(conninfo)
    before = readings.states(projects)
    step(GITHUB)
    repositories = RepositoryStore(conninfo)
    of_project = readmes.link_repositories(repositories, run)
    wanted = sorted({one for pid, one in of_project.items() if projects is None or pid in projects})
    answered: set[str] = set()
    if client is not None:
        answered = ask_github(client, answers, wanted, run, collector=collector,
                              older_than=older_than, now=now, limit=limit, step=step)  # fmt: skip
    if answered:
        readmes.read_readmes(repositories, ProjectStore(conninfo), answers, run, only=answered)
        code.read_code(repositories, answers, run, only=answered)
        hedera_code.read_hedera_code(repositories, answers, run, only=answered)
    step(LEDGER)
    ledger = LedgerStore(conninfo)
    code_ids.give_code_ids(CodeIdStore(conninfo), ledger, mirrors, run, max_age=older_than,
                           now=now, projects=projects)  # fmt: skip
    check_ids.check_ids(ledger, mirrors, run, max_age=older_than, now=now, projects=projects)
    step(HISTORIES)
    histories = HistoryStore(conninfo)
    history.read_histories(histories, mirrors, run, now=now, again=True, limit=limit,
                           projects=projects)  # fmt: skip
    history.read_histories_on(histories, mirrors, run, older_than=older_than, limit=limit,
                              now=now, projects=projects)  # fmt: skip
    step(CONTRACTS)
    contract_calls.read_contract_calls(
        ContractCallStore(conninfo), mirrors, run, now=now, projects=projects,
        older_than=older_than, limit=min(limit, CONTRACTS_A_ROUND) if limit is not None else None,
    )  # fmt: skip
    run.counts["repositories_answered"] = len(answered)
    after = readings.states(projects)
    moment = now()
    kept = []
    for project_id, state in after.items():
        changes = changes_of(before.get(project_id, state), state)
        if changes or source == BUTTON:
            kept.append((project_id, moment, source, changes))
    readings.save(kept)
    run.counts["projects_changed"] = sum(bool(changes) for *_, changes in kept)


def refresh_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = []
    words = {"facts": "facts", "readmes": "READMEs", "versions": "newest commits",
             "archives": "readings of the code"}  # fmt: skip
    for kind in KINDS:
        asked = counts[f"{kind}_asked"] + counts[f"{kind}_asked_first"]
        if not (asked or counts[f"{kind}_fresh"] or counts[f"{kind}_left_for_later"]):
            continue
        lines.append(
            f"GitHub, {words[kind]}: {asked} asked ({counts[f'{kind}_asked_first']} for the first "
            f"time), {counts[f'{kind}_unchanged']} the same, {counts[f'{kind}_changed']} changed, "
            f"{counts[f'{kind}_failed']} failed; {counts[f'{kind}_fresh']} young enough, "
            f"{counts[f'{kind}_left_for_later']} left for a later run."
        )
    lines.append(f"Repositories written again from GitHub's answers: "
                 f"{counts['repositories_answered']}.")  # fmt: skip
    lines.append(
        f"Ledger: {counts['answers_from_the_node']} answers of the mirror node, "
        f"{counts['answers_from_the_table']} from the table. Histories read whole: "
        f"{counts['ids_read']}, with {counts['events']:,} events; read on: "
        f"{counts['histories_read_on']}, with {counts['events_new']:,} new events."
    )
    lines.append(f"Contracts whose calls were read: {counts['contracts_read']}, with "
                 f"{counts['calls_read']:,} calls.")  # fmt: skip
    return lines
