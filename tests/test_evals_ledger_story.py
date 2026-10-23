"""The first measure of the ledger story (evals/ledger_story): the words that name a service and
the five signals of the guideline, on invented projects."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from evals.ledger_story.run import Project, measure, signals
from hackathon_memory.check.history import CONSENSUS, CONTRACTS, HBAR, TOKENS
from hackathon_memory.check.story import Event

STARTS = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
ENDS = date(2026, 9, 16)
DURING = STARTS + timedelta(days=2)
LONG_BEFORE = STARTS - timedelta(days=90)  # before the window, which opens 30 days before
LONG_AFTER = datetime(2026, 11, 1, tzinfo=UTC)  # later than 30 days after the end


def a_project(*events: Event, words: str = "", proof_found: bool = True) -> Project:
    return Project(1, STARTS, ENDS, proof_found, words, tuple(events))


def test_s1_needs_a_proof_and_an_own_thing_active_before_the_window() -> None:
    old_topic = Event(LONG_BEFORE, CONSENSUS, of_an_account=False)
    assert signals(a_project(old_topic))["S1"]
    assert not signals(a_project(old_topic, proof_found=False))["S1"]
    old_account = Event(LONG_BEFORE, HBAR, of_an_account=True)  # a builder's old account
    assert not signals(a_project(old_account))["S1"]


def test_s2_counts_more_than_half_of_the_own_things_before_the_window() -> None:
    before, during = Event(LONG_BEFORE, CONSENSUS, False), Event(DURING, CONSENSUS, False)
    assert signals(a_project(before, before, during))["S2"]
    assert not signals(a_project(before, during))["S2"]  # half is not more than half


def test_s3_is_a_named_service_with_no_event_at_any_time() -> None:
    words = "We use the Hedera Token Service and the Consensus Service."
    assert signals(a_project(Event(DURING, CONSENSUS, True), words=words))["S3"]  # no token
    both = (Event(DURING, CONSENSUS, True), Event(LONG_BEFORE, TOKENS, True))
    assert not signals(a_project(*both, words=words))["S3"]  # any time, any own ID


def test_s4_needs_three_events_from_the_window_on_of_a_service_not_named() -> None:
    calls = [Event(DURING, CONTRACTS, True)] * 3
    assert signals(a_project(*calls))["S4"]
    assert not signals(a_project(*calls, words="A smart contract holds it."))["S4"]
    assert not signals(a_project(*calls[:2]))["S4"]
    old_calls = [Event(LONG_BEFORE, CONTRACTS, True)] * 3  # before the window: not counted
    assert not signals(a_project(*old_calls))["S4"]
    payments = [Event(DURING, HBAR, True)] * 5  # HBAR is not compared
    assert not signals(a_project(*payments))["S4"]


def test_s5_is_an_own_thing_active_later_than_the_line_of_life() -> None:
    assert signals(a_project(Event(LONG_AFTER, CONSENSUS, False)))["S5"]
    assert not signals(a_project(Event(LONG_AFTER, HBAR, True)))["S5"]  # an account only


def test_the_decision_counts_a_project_once_with_any_of_s1_s3_s4() -> None:
    quiet = a_project(Event(DURING, CONSENSUS, False), words="Built on the Consensus Service.")
    flagged = a_project(*[Event(DURING, CONTRACTS, True)] * 3)  # S4 only
    result = measure([quiet, flagged, flagged, quiet, quiet])
    assert result["any_of_S1_S3_S4"]["count"] == 2 and result["any_of_S1_S3_S4"]["of"] == 5
    assert result["worth_building"]  # 40% is at least 20%
    assert not measure([quiet] * 9 + [flagged])["worth_building"]  # 10% is under 20%


def test_the_check_with_loose_words_is_reported_beside_the_rule() -> None:
    page = "Our contract mints an NFT."  # names nothing by the strict words
    calls = [Event(DURING, CONTRACTS, True)] * 3
    result = measure([a_project(*calls, words=page)])
    assert result["signals"]["S4"]["count"] == 1  # by the rule: done but not named
    assert result["check_loose_words"]["S4"] == 0  # by the loose words, "contract" names it
    assert result["check_loose_words"]["S3"] == 1  # and "NFT" names tokens, never done
