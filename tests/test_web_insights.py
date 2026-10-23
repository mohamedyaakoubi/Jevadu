"""The insights of a list (web/insights.py): facts in sentences, where the data carries them."""

from __future__ import annotations

from collections import Counter

from hackathon_memory.search.counts import Tally
from hackathon_memory.web.data import Member
from hackathon_memory.web.insights import Share, build, won_again, worked_on

WON = "hedera_prize"


def test_linked_projects_won_again_only_with_prizes_at_two_events() -> None:
    twice = [Member(1, "Turn", "Cannes", 10), Member(2, "Turn 2", "New York", 11)]
    one_event = [Member(3, "Frog", "Lisbon", 12), Member(4, "Frog 2", "Lisbon", 12)]
    one_winner = [Member(5, "Hands", "Lisbon", 12), Member(6, "Froggy", "Online", 13)]
    thrice = [Member(7, "A", "X", 1), Member(8, "B", "Y", 2), Member(9, "C", "Z", 3)]
    prize = {1: WON, 2: WON, 3: WON, 4: WON, 5: "other_prize", 6: "no_prize", 7: WON, 8: WON,
             9: WON}  # fmt: skip
    found = won_again([twice, one_event, one_winner, thrice], prize)
    assert [one.events for one in found] == [3, 2]  # the most events first
    assert [member.name for member in found[1].winners] == ["Turn", "Turn 2"]
    partly = [Member(1, "Turn", "Cannes", 10), Member(6, "Froggy", "Online", 13)]
    assert won_again([partly], prize) == ()  # only one of the two won


def test_still_worked_on_counts_only_known_activity_with_enough_projects() -> None:
    life = Counter({"active": 10, "quiet": 9, "stopped": 45, "too early to tell": 18,
                    "unknown": 10})  # fmt: skip
    assert worked_on(life) == Share(19, 64) and Share(19, 64).percent == 30
    assert worked_on(Counter({"active": 3, "stopped": 10})) is None  # 13 known: too few
    assert Share(4, 16).percent is None


def test_the_insights_of_a_tally() -> None:
    found = Tally(
        projects=300, with_theme=200,
        themes=Counter({"Agents": 95, "Lending": 55, "Tools": 224, "Games": 31}),
        themes_won=Counter({"Agents": 21, "Lending": 16, "Tools": 13, "Games": 0}),
        life=Counter({"active": 24, "quiet": 25, "stopped": 196}),
        life_won=Counter({"active": 10, "quiet": 9, "stopped": 45}),
    )  # fmt: skip
    insights = build(found, [], {})
    assert [(theme, share.part, share.whole, share.percent)
            for theme, share in insights.top_themes] == [
        ("Agents", 21, 95, 22), ("Lending", 16, 55, 29), ("Tools", 13, 224, 6)]  # fmt: skip
    assert insights.worked_on_won == Share(19, 64)
    assert insights.worked_on_other == Share(30, 181)  # the others: all minus the winners
    assert insights and not insights.won_again
    few = build(Tally(projects=3, life=Counter({"active": 1}), life_won=Counter({"active": 1})),
                [], {})  # fmt: skip
    assert not few  # nothing to say about three projects
