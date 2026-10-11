"""The robots.txt reader follows RFC 9309, with the wildcards that the Python reader misses."""

from __future__ import annotations

from fakes import sample
from hackathon_memory.collect.robots import RobotsRules

AGENT = "HackathonMemory-research"
SITE = "https://ethglobal.com"


def test_the_invented_sample_file() -> None:
    rules = RobotsRules(sample("robots.txt").decode("utf-8"))
    assert rules.allows(AGENT, f"{SITE}/showcase/zed-widget-a1b2c")
    assert not rules.allows(AGENT, f"{SITE}/private/x")
    assert not rules.allows(AGENT, f"{SITE}/showcase/x?draft=1")  # the wildcard rule
    assert not rules.allows("BadBot/1.0", f"{SITE}/showcase/x")  # its own group


def test_no_rules_means_everything_is_allowed() -> None:
    assert RobotsRules("").allows(AGENT, f"{SITE}/anything")


def test_an_empty_disallow_allows_everything() -> None:
    assert RobotsRules("User-agent: *\nDisallow:\n").allows(AGENT, f"{SITE}/x")


def test_the_longest_rule_wins_and_allow_wins_a_tie() -> None:
    text = "User-agent: *\nDisallow: /a\nAllow: /a/b\nDisallow: /c\nAllow: /c\n"
    rules = RobotsRules(text)
    assert not rules.allows(AGENT, f"{SITE}/a/x")
    assert rules.allows(AGENT, f"{SITE}/a/b/x")  # the longer Allow wins
    assert rules.allows(AGENT, f"{SITE}/c")  # same length: Allow wins


def test_the_end_marker_and_the_star() -> None:
    rules = RobotsRules("User-agent: *\nDisallow: /*.pdf$\nDisallow: /scratch*cache\n")
    assert not rules.allows(AGENT, f"{SITE}/files/report.pdf")
    assert rules.allows(AGENT, f"{SITE}/files/report.pdf.html")
    assert not rules.allows(AGENT, f"{SITE}/scratch/x/cache")
    assert rules.allows(AGENT, f"{SITE}/scratch/x/other")


def test_the_most_specific_agent_group_is_used() -> None:
    text = "User-agent: *\nDisallow: /\n\nUser-agent: HackathonMemory\nAllow: /\n"
    rules = RobotsRules(text)
    assert rules.allows(AGENT, f"{SITE}/x")  # our name contains "HackathonMemory"
    assert not rules.allows("SomeoneElse", f"{SITE}/x")


def test_two_agents_can_share_one_group() -> None:
    rules = RobotsRules("User-agent: A\nUser-agent: B\nDisallow: /x\n")
    assert not rules.allows("A", f"{SITE}/x")
    assert not rules.allows("B", f"{SITE}/x")
    assert rules.allows("C", f"{SITE}/x")


def test_comments_and_case_are_ignored() -> None:
    rules = RobotsRules("# hello\nUSER-AGENT: *   # all\nDISALLOW: /secret # no\n")
    assert not rules.allows(AGENT, f"{SITE}/secret")


def test_crawl_delay_is_read() -> None:
    rules = RobotsRules("User-agent: *\nCrawl-delay: 7\n")
    assert rules.crawl_delay(AGENT) == 7.0
    assert RobotsRules("User-agent: *\n").crawl_delay(AGENT) is None
