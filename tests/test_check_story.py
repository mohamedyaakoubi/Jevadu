"""The ledger story (check/story.py): the rules that the measure and the card share, and the
card's table, facts and time (design 7.5), on invented words and events."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from hackathon_memory.check.history import (
    CONSENSUS,
    CONTRACTS,
    FILES,
    HBAR,
    SCHEDULED,
    TOKENS,
)
from hackathon_memory.check.story import (
    CODE_SERVICES,
    Event,
    Outside,
    OwnId,
    Story,
    merged,
    name_patterns,
    named_services,
    on_its_network,
    places_in,
    services_in_code,
    set_up_in_code,
    story_of,
    words_found,
)
from hackathon_memory.parse.hedera_code import (
    CHAIN_ID,
    EVM_NETWORK,
    FEATURE,
    FEATURES,
    IMPORT,
    MENTION,
    MIRROR_NODE,
    PACKAGE,
    RELAY,
    SIGN,
    SYSTEM_CONTRACTS,
)
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, TOPIC

STARTS = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
ENDS = date(2026, 9, 16)  # the time of the table: 5 August to 16 October 2026
DURING = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
EARLY = STARTS - timedelta(days=29)  # inside the time: the window opens 30 days before
LONG_BEFORE = datetime(2026, 5, 1, tzinfo=UTC)
LONG_AFTER = datetime(2026, 11, 1, tzinfo=UTC)
LATER = datetime(2026, 12, 24, tzinfo=UTC)
JUNE = datetime(2026, 6, 2, tzinfo=UTC)
ASKED = datetime(2026, 10, 23, 2, 0, tzinfo=UTC)
NONE: frozenset[str] = frozenset()
TOPIC_ID = OwnId("0.0.4511", "testnet", TOPIC, ASKED)
ACCOUNT_ID = OwnId("0.0.4512", "testnet", ACCOUNT, ASKED)


@pytest.mark.parametrize(
    ("words", "named"),
    [
        ("It logs every step on the Hedera Consensus Service.", {CONSENSUS}),
        ("Messages go to an hcs topic; see HCS-10.", {CONSENSUS}),
        ("A loyalty point made with the Hedera Token Service (HTS).", {TOKENS}),
        ("Escrow lives in a Solidity smart contract.", {CONTRACTS}),
        ("Payouts are a scheduled transaction.", {SCHEDULED}),
        ("A JWT token and an NFT gallery.", set()),  # "token" and "NFT" alone do not count
        ("The topics of the talk; the HTTPS server.", set()),
    ],
)
def test_only_the_strict_words_name_a_service(words: str, named: set[str]) -> None:
    assert named_services(words) == named


def test_a_moment_that_an_account_and_a_topic_both_show_belongs_to_the_topic() -> None:
    seen = [("1.1", DURING, CONSENSUS, True), ("1.1", DURING, CONSENSUS, False),
            ("2.2", LONG_AFTER, HBAR, True)]  # fmt: skip
    assert merged(seen) == (Event(DURING, CONSENSUS, False), Event(LONG_AFTER, HBAR, True))


def test_an_id_counts_on_the_network_where_its_status_is_the_best() -> None:
    rows = [(1, "0.0.5001", "testnet", "proof_found", "account", False),
            (1, "0.0.5001", "mainnet", "dates_do_not_fit", "account", False),  # someone else's
            (2, "0.0.5002", "mainnet", "found_but_empty", "topic", False)]  # fmt: skip
    assert on_its_network(rows) == [rows[0], rows[2]]


def test_the_words_of_the_page_are_shown_as_it_writes_them_each_once() -> None:
    page = "We log to HCS. The hcs topic ID is in the README. Escrow in Solidity; HCS again."
    assert words_found(page) == {CONSENSUS: ("HCS", "topic ID"), CONTRACTS: ("Solidity",)}
    assert words_found("A JWT token and an NFT.") == {}


def test_each_place_where_the_page_names_a_service_is_found_in_order() -> None:
    text = "HCS first. Then hts, and the HCS topic ID."
    assert places_in(text) == [(0, 3, CONSENSUS), (16, 19, TOKENS), (29, 32, CONSENSUS),
                               (33, 41, CONSENSUS)]  # fmt: skip
    overlapping = name_patterns({"a": ("smart contract",), "b": ("contract ID",)})
    assert places_in("a smart contract ID", overlapping) == [(2, 16, "a")]  # the first one counts


def test_every_name_of_the_code_reading_that_shows_a_service_exists() -> None:
    signs = {RELAY, CHAIN_ID, EVM_NETWORK, SYSTEM_CONTRACTS}
    assert set(CODE_SERVICES) <= set(FEATURES) | signs  # a renamed class list goes red here
    assert set(CODE_SERVICES.values()) == {CONSENSUS, TOKENS, CONTRACTS, SCHEDULED, FILES, HBAR}


def test_the_code_calls_a_service_by_its_classes_and_only_sets_up_an_evm_project() -> None:
    found = [(FEATURE, "Token Service"), (SIGN, RELAY), (SIGN, MIRROR_NODE),
             (PACKAGE, "@hashgraph/sdk"), (IMPORT, "a Hedera library"),
             (MENTION, "the word Hedera"), (FEATURE, "Random numbers")]  # fmt: skip
    assert services_in_code(found) == {TOKENS}  # a package or the relay is not a call
    assert set_up_in_code(found) == {CONTRACTS}
    solidity = [(SIGN, SYSTEM_CONTRACTS), (SIGN, CHAIN_ID)]  # a contract that calls Hedera
    assert services_in_code(solidity) == {CONTRACTS}
    assert services_in_code([]) == set_up_in_code([]) == frozenset()


def test_an_evm_setup_shows_only_where_the_code_makes_no_call() -> None:
    set_up = a_story(set_up=frozenset({CONTRACTS}))
    assert [(line.service, line.in_code, line.set_up) for line in set_up.lines] == [
        (CONTRACTS, False, True)
    ]
    both = a_story(code=frozenset({CONTRACTS}), set_up=frozenset({CONTRACTS}))
    assert [(line.in_code, line.set_up) for line in both.lines] == [(True, False)]


def a_story(*events: Event, words: str = "", code: frozenset[str] | None = frozenset(),
            ids: tuple[OwnId, ...] = (TOPIC_ID, ACCOUNT_ID), starts_at: datetime | None = STARTS,
            ends_on: date | None = ENDS, set_up: frozenset[str] = NONE) -> Story:  # fmt: skip
    return story_of(ids, events, words, code, starts_at=starts_at, ends_on=ends_on, set_up=set_up)


def test_the_table_counts_every_id_in_the_time_around_the_event() -> None:
    story = a_story(
        Event(EARLY, CONSENSUS, False), Event(DURING, CONSENSUS, False),
        Event(DURING, HBAR, True), Event(LONG_BEFORE, CONSENSUS, False),
        Event(LONG_AFTER, HBAR, True), words="Messages go to HCS.",
        code=frozenset({CONSENSUS, TOKENS}),
    )  # fmt: skip
    assert (story.starts_on, story.ends_on) == (date(2026, 8, 5), date(2026, 10, 16))
    rows = [(line.service, line.words, line.in_code, line.count, line.compared)
            for line in story.lines]  # fmt: skip
    assert rows == [(CONSENSUS, ("HCS",), True, 2, True), (TOKENS, (), True, 0, True),
                    (HBAR, (), False, 1, False)]  # fmt: skip
    assert story.code_read


def test_the_table_counts_the_places_of_each_word_of_the_page() -> None:
    story = a_story(Event(DURING, CONSENSUS, False), words="HCS logs it.\nhcs again; the topic ID.")
    assert [(line.words, line.places) for line in story.lines] == [(("HCS", "topic ID"), (2, 1))]


def test_a_named_service_with_no_transaction_in_that_time_stands_out() -> None:
    words = "We use the Hedera Token Service (HTS) and the Consensus Service."
    story = a_story(Event(DURING, CONSENSUS, False), Event(LONG_AFTER, TOKENS, False),
                    words=words)  # fmt: skip
    assert story.named_not_seen == (TOKENS,)  # its one token event is later than that time
    assert not story.all_named_seen
    both = a_story(Event(DURING, CONSENSUS, False), Event(DURING, TOKENS, True), words=words)
    assert both.named_not_seen == () and both.all_named_seen
    assert not a_story(Event(DURING, CONSENSUS, False)).all_named_seen  # the page names none


def test_the_calls_of_its_contracts_count_for_the_service_they_reached() -> None:
    """A contract that reaches the Token Service uses it: the table counts its calls beside the
    transactions, and the page's Token Service is not said to show nothing (28 October 2026)."""
    from hackathon_memory.check.system_calls import ContractCalls

    span = (STARTS - timedelta(days=30), STARTS + timedelta(days=60))
    calls = (ContractCalls("0.0.4513", "testnet", *span, 100, True,
                           {"0.0.359": 34, "0.0.361": 2}),)  # fmt: skip
    words = "We use the Hedera Token Service (HTS) from Solidity."
    story = story_of((TOPIC_ID,), (Event(DURING, CONTRACTS, False),), words, frozenset(),
                     starts_at=STARTS, ends_on=ENDS, calls=calls)  # fmt: skip
    tokens = next(line for line in story.lines if line.service == TOKENS)
    assert (tokens.count, tokens.from_contracts) == (0, 34)
    assert story.named_not_seen == () and story.all_named_seen
    assert story.contract_others == ("random numbers in 2 calls",) and story.calls_cut


def test_a_service_of_three_transactions_that_the_page_does_not_name_stands_out() -> None:
    calls = [Event(DURING, CONTRACTS, True)] * 3
    assert a_story(*calls).seen_not_named == ((CONTRACTS, 3),)
    assert a_story(*calls[:2]).seen_not_named == ()
    assert a_story(*calls, words="A smart contract holds it.").seen_not_named == ()
    assert a_story(*[Event(DURING, HBAR, True)] * 5).seen_not_named == ()  # HBAR: not compared
    old = [Event(LONG_BEFORE, CONTRACTS, False)] * 3
    assert a_story(*old).seen_not_named == ()  # outside that time


def test_before_and_after_count_only_the_own_things_with_their_first_and_last_day() -> None:
    story = a_story(
        Event(LONG_BEFORE, CONTRACTS, False), Event(JUNE, TOKENS, False),
        Event(datetime(2026, 1, 1, tzinfo=UTC), HBAR, True),  # an old account: not counted
        Event(DURING, CONSENSUS, False), Event(LONG_AFTER, CONSENSUS, False),
        Event(LATER, CONSENSUS, False), Event(LATER, HBAR, True),
    )  # fmt: skip
    # no payer given here, so who paid is not known for any of them
    assert story.before == Outside(2, date(2026, 5, 1), ((TOKENS, 1), (CONTRACTS, 1)), 0, 0, 2)
    assert story.after == Outside(2, date(2026, 12, 24), ((CONSENSUS, 2),), 0, 0, 2)
    quiet = a_story(Event(DURING, CONSENSUS, False))
    assert quiet.before == quiet.after == Outside(0, None, ())


def test_the_time_before_and_after_says_who_paid() -> None:
    """Anyone can send a transaction to a contract or a topic, so the time before and after
    counts the accounts that paid: those the project names, and the others, who may be strangers
    (29 October 2026). The network's own accounts and a transaction with no payer count for
    neither."""
    hour = timedelta(hours=1)
    events = (
        Event(LONG_BEFORE, CONTRACTS, False, "0.0.9001"),
        Event(LONG_BEFORE + hour, CONTRACTS, False, "0.0.9002"),
        Event(LONG_BEFORE + 2 * hour, CONTRACTS, False, "0.0.9002"),
        Event(LATER, CONSENSUS, False, "0.0.7001"),
        Event(LATER + hour, CONSENSUS, False, "0.0.2"),  # the treasury of the network
        Event(LATER + 2 * hour, TOKENS, False, None),  # a mint: no payer known
    )
    told = story_of((TOPIC_ID, ACCOUNT_ID), events, "", frozenset(), starts_at=STARTS,
                    ends_on=ENDS, named_ids=frozenset({"0.0.7001"}))  # fmt: skip
    assert (told.before.count, told.before.paid_by_named, told.before.paid_by_others) == (3, 0, 2)
    assert (told.after.count, told.after.paid_by_named, told.after.paid_by_others) == (3, 1, 0)
    assert (told.before.payer_unknown, told.after.payer_unknown) == (0, 1)
    # the payer comes through the merging of the moments
    assert merged([("1.000000001", DURING, CONSENSUS, False, "0.0.7001")]) == (
        Event(DURING, CONSENSUS, False, "0.0.7001"),
    )


def test_with_accounts_only_the_time_before_and_after_is_not_counted() -> None:
    story = a_story(Event(LONG_BEFORE, HBAR, True), Event(DURING, HBAR, True), ids=(ACCOUNT_ID,))
    assert story.before is None and story.after is None
    assert [(line.service, line.count) for line in story.lines] == [(HBAR, 1)]


def test_without_the_days_of_the_event_every_transaction_counts_and_no_time_is_told() -> None:
    story = a_story(Event(LONG_BEFORE, CONSENSUS, False), Event(LATER, CONSENSUS, False),
                    starts_at=None)  # fmt: skip
    assert story.starts_on is None and story.before is None and story.after is None
    assert [(line.service, line.count) for line in story.lines] == [(CONSENSUS, 2)]


def test_code_that_was_not_read_is_left_out_of_the_table() -> None:
    story = a_story(Event(DURING, CONSENSUS, False), words="On HCS.", code=None)
    assert not story.code_read and not story.lines[0].in_code


def test_the_story_says_what_was_read_and_when() -> None:
    later = OwnId("0.0.4513", "mainnet", CONTRACT, ASKED + timedelta(days=2), cut=True)
    waiting = OwnId("0.0.4514", "testnet", TOPIC, None)
    story = a_story(ids=(TOPIC_ID, later, waiting))
    assert [one.entity_id for one in story.read] == ["0.0.4511", "0.0.4513"]
    assert (story.not_read, story.cut) == (1, 1)
    assert story.read_on == (date(2026, 10, 23), date(2026, 10, 25))
    assert a_story(ids=(waiting,)).read_on is None
