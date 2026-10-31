"""The step `timeline` (design 8.7, 31 October 2026): how the code of a team that came back
changed between its hackathons.

    python -m hackathon_memory.pipeline timeline

For each group of projects linked across events with one repository (search/timeline.py), GitHub
is asked once for the newest commit on or before the last day of each event, then for the
comparison of each two that follow (collect/github_history.py). A saved answer is never asked for
again, so a run asks only what a new group, or a new event of a group, needs.

The step runs in "all", and the same asking runs in "refresh" (the daily reading, the rounds of the
website and the button "Read again now" of a card), so a team that a new list of projects brings
back gets its timeline without anybody asking for it.
"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise

from hackathon_memory.collect import github_history
from hackathon_memory.collect.github import GitHubClient
from hackathon_memory.collect.github_once import AnswersRun
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.runs import Run
from hackathon_memory.search.timeline import groups_with_one_repository

STEP = "timeline"


def _counted(run: Run, kind: str, asked: AnswersRun) -> None:
    run.counts[f"{kind}_asked"] += asked.asked
    run.counts[f"{kind}_saved_before"] += asked.already_saved
    run.counts[f"{kind}_failed"] += asked.failed
    run.counts[f"{kind}_left_for_later"] += asked.left_for_later
    if asked.stopped:
        run.problem("GitHub", asked.stopped)


def ask_timelines(client: GitHubClient | None, store: RawStore, conninfo: str, run: Run, *,
                  collector: str, projects: Iterable[int] | None = None,
                  limit: int | None = None) -> None:  # fmt: skip
    """Ask GitHub for what the timelines lack, for every group or for the groups of `projects`.
    With no client, nothing is asked."""
    groups = groups_with_one_repository(conninfo, projects)
    run.counts["timeline_groups"] += len(groups)
    if client is None or not groups:
        return
    wanted = [(group.repository, day) for group in groups for day in group.last_days]
    _counted(run, "timeline_commits", github_history.fetch_untils(
        client, store, wanted, collector=collector, limit=limit))  # fmt: skip
    pairs = []
    for group in groups:
        versions = [github_history.saved_until(store, group.repository, day)
                    for day in group.last_days]  # fmt: skip
        for one, two in pairwise(versions):
            if one and two and one.sha and two.sha and one.sha != two.sha:
                pairs.append((group.repository, one.sha, two.sha))
    _counted(run, "timeline_changes", github_history.fetch_changes(
        client, store, pairs, collector=collector, limit=limit))  # fmt: skip


def timeline_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    return [
        f"Teams that came back with one repository: {counts['timeline_groups']}.",
        f"GitHub, commits at the end of an event: {counts['timeline_commits_asked']} asked, "
        f"{counts['timeline_commits_saved_before']} saved before, "
        f"{counts['timeline_commits_failed']} failed, "
        f"{counts['timeline_commits_left_for_later']} left for a later run.",
        f"GitHub, comparisons of two commits: {counts['timeline_changes_asked']} asked, "
        f"{counts['timeline_changes_saved_before']} saved before, "
        f"{counts['timeline_changes_failed']} failed, "
        f"{counts['timeline_changes_left_for_later']} left for a later run.",
    ]
