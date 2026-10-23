"""The insights of a list (design 12.1, S5, 20 October 2026): a few facts in sentences above the
charts, counted from the same tally (search/counts.py) and the same links across events
(search/seen.py). Each sentence names its numbers. Nothing predicts, scores or ranks a project,
and a share is given only when SHARE_NEEDS projects or more stand behind it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hackathon_memory.check.life import ACTIVE, QUIET, STOPPED
from hackathon_memory.search.counts import WON, Tally
from hackathon_memory.web.charts import SHARE_NEEDS
from hackathon_memory.web.data import Member

THEMES_NAMED = 3  # the categories with the most Hedera prizes that one sentence names


@dataclass(frozen=True)
class Share:
    """A part of a whole, with its share in percent when enough projects stand behind it."""

    part: int
    whole: int

    @property
    def percent(self) -> int | None:
        return round(100 * self.part / self.whole) if self.whole >= SHARE_NEEDS else None


@dataclass(frozen=True)
class WonAgain:
    """Linked projects (the same repository, or the same Hedera ID that the ledger found) that
    won a Hedera prize at more than one event: the winners of the group."""

    winners: tuple[Member, ...]

    @property
    def events(self) -> int:
        return len({member.event_id for member in self.winners})


@dataclass(frozen=True)
class Insights:
    won_again: tuple[WonAgain, ...]
    top_themes: tuple[tuple[str, Share], ...]  # a category: its Hedera prizes of its projects
    with_theme: int
    worked_on_won: Share | None  # winners still worked on, of those whose activity is known
    worked_on_other: Share | None  # the same, for the projects without a Hedera prize

    def __bool__(self) -> bool:
        return bool(self.won_again or self.top_themes or self.worked_on_won)


def won_again(groups: Sequence[Sequence[Member]], prize: Mapping[int, str]) -> tuple[WonAgain, ...]:
    """The groups whose Hedera prizes stand at two events or more, the most events first."""
    found = []
    for group in groups:
        winners = tuple(member for member in group if prize.get(member.project_id) == WON)
        if len({member.event_id for member in winners}) > 1:
            found.append(WonAgain(winners))
    return tuple(sorted(found, key=lambda one: -one.events))


def worked_on(life: Counter) -> Share | None:
    """The projects still worked on after the event (active or quiet), of those whose activity
    is known: "too early to tell" and "unknown" stand outside. None when too few are known."""
    known = sum(life.get(status, 0) for status in (ACTIVE, QUIET, STOPPED))
    alive = sum(life.get(status, 0) for status in (ACTIVE, QUIET))
    return Share(alive, known) if known >= SHARE_NEEDS else None


def build(found: Tally, groups: Sequence[Sequence[Member]], prize: Mapping[int, str]) -> Insights:
    """The insights of the projects counted in `found`. `groups` are their links across events,
    and `prize` gives the prize of every project, also of a linked one outside the list."""
    top = sorted(found.themes_won.items(), key=lambda item: (-item[1], item[0]))[:THEMES_NAMED]
    won, other = worked_on(found.life_won), worked_on(found.life - found.life_won)
    both = won is not None and other is not None
    return Insights(
        won_again(groups, prize),
        tuple((theme, Share(count, found.themes[theme])) for theme, count in top if count),
        found.with_theme,
        won if both else None,
        other if both else None,
    )
