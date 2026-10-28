"""The depth of use of a project's own Hedera IDs (check/depth.py, design 7.5) and the drawing of
its strip of days (web/strips.py). Every ID, account and date is invented."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from hackathon_memory.check.depth import (
    LONGEST_SAID,
    Done,
    depth_of,
    kinds_in_words,
    page_said,
)
from hackathon_memory.check.history import CONSENSUS, CONTRACTS, HBAR, TOKENS, Act
from hackathon_memory.check.story import OwnId
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, TOKEN, TOPIC
from hackathon_memory.web.strips import LIGHTEST, strip_view

STARTS = datetime(2026, 4, 3, 9, tzinfo=UTC)  # an invented event of three days
ENDS = date(2026, 4, 5)
ASKED = datetime(2026, 10, 25, tzinfo=UTC)
TOPIC_ID, TOKEN_ID, CONTRACT_ID, TEAM = "0.0.6001", "0.0.6002", "0.0.6003", "0.0.7001"
NAMED = {TOPIC_ID, TOKEN_ID, CONTRACT_ID, TEAM}


def own(*kinds: tuple[str, str]) -> tuple[OwnId, ...]:
    return tuple(OwnId(entity, "testnet", kind, ASKED) for entity, kind in kinds)


def done(at: datetime, entity: str, kind: str, service: str, act: Act, n: int = 0) -> Done:
    stamp = f"{at.timestamp():.0f}.{n:09d}"
    return Done(stamp, at, service, entity, kind, "testnet", act)


def message(at: datetime, payer: str = TEAM, n: int = 0) -> Done:
    return done(at, TOPIC_ID, TOPIC, CONSENSUS,
                Act("CONSENSUSSUBMITMESSAGE", True, payer, (payer,)), n)  # fmt: skip


def depth(ids: tuple[OwnId, ...], items: list[Done], **options: object):  # noqa: ANN201
    holders = options.pop("holders", {})
    return depth_of(ids, items, holders, NAMED, starts_at=STARTS, ends_on=ENDS,
                    words=options.pop("words", ""), in_code=options.pop("in_code", None),
                    **options)  # fmt: skip


def test_what_its_ids_did_is_counted_in_plain_words_with_the_failures_apart() -> None:
    day = STARTS + timedelta(hours=2)
    items = [message(day, n=n) for n in range(3)]
    items.append(done(day, TOKEN_ID, TOKEN, TOKENS, Act("TOKENMINT", True, None, ()), 9))
    items.append(done(day, TEAM, ACCOUNT, HBAR, Act("CRYPTOTRANSFER", False, TEAM, ()), 10))
    result = depth(own((TOPIC_ID, TOPIC), (TOKEN_ID, TOKEN), (TEAM, ACCOUNT)), items)
    assert result.did == (("messages to a topic", 3), ("mint of tokens or NFTs", 1))
    assert result.failed == 1 and result.more_kinds == 0


def test_more_kinds_than_are_named_are_counted_together() -> None:
    day = STARTS
    names = ["CRYPTOTRANSFER", "TOKENMINT", "TOKENBURN", "CONTRACTCALL", "CRYPTOCREATEACCOUNT",
             "TOKENASSOCIATE", "SCHEDULECREATE", "UTILPRNG"]  # fmt: skip
    items = [done(day, TEAM, ACCOUNT, HBAR, Act(name, True, TEAM, ()), n)
             for n, name in enumerate(names)]  # fmt: skip
    did, more, _ = kinds_in_words(items)
    assert len(did) == 6 and more == 2 and ("other transaction", 1) not in did
    every = depth(own((TEAM, ACCOUNT)), items)
    assert (every.total, every.more_count) == (8, 2)  # all of them, and those of the 2 kinds
    unread = [done(day, TEAM, ACCOUNT, HBAR, Act(None, None, None), n) for n in range(2)]
    assert kinds_in_words(unread)[0] == (("transactions not read in detail yet", 2),)


def test_who_took_part_leaves_out_the_ids_that_the_project_names() -> None:
    day = STARTS
    items = [message(day, payer=TEAM), message(day, payer="0.0.8001", n=1),
             message(day, payer="0.0.8002", n=2), message(day, payer="0.0.8002", n=3)]  # fmt: skip
    # the network's treasury paid for one: it makes the accounts of Hedera's portal, and it is no
    # one who took part (found by the second counting of evals/depth.py, 25 October 2026)
    items.append(message(day, payer="0.0.2", n=4))
    holders = {(TOKEN_ID, "testnet"): (TEAM, "0.0.8003", "0.0.8004")}
    result = depth(own((TOPIC_ID, TOPIC), (TOKEN_ID, TOKEN)), items, holders=holders)
    assert (result.others, result.held_by_others) == (2, 2)
    unknown = depth(own((TOPIC_ID, TOPIC)), [done(day, TOPIC_ID, TOPIC, CONSENSUS,
                                                 Act(None, None, None))])  # fmt: skip
    assert unknown.others is None and unknown.held_by_others is None


def test_the_days_are_counted_during_before_and_after_the_event() -> None:
    items = [message(STARTS - timedelta(days=5)), message(STARTS, n=1),
             message(STARTS + timedelta(days=1), n=2), message(STARTS + timedelta(hours=1), n=3),
             message(datetime(2026, 4, 20, tzinfo=UTC), n=4),
             message(datetime(2026, 9, 1, tzinfo=UTC), n=5)]  # fmt: skip
    result = depth(own((TOPIC_ID, TOPIC)), items)
    assert (result.days, result.days_during, result.days_before, result.days_after) == (4, 2, 1, 1)
    assert result.strip is not None and (result.strip.before, result.strip.after) == (0, 1)


def test_the_signs_that_stay_on_paper_are_facts() -> None:
    ids = own((TOPIC_ID, TOPIC), (TOKEN_ID, TOKEN), (CONTRACT_ID, CONTRACT))
    deployed = done(STARTS, CONTRACT_ID, CONTRACT, CONTRACTS,
                    Act("CONTRACTCREATEINSTANCE", True, TEAM, (TEAM,)))  # fmt: skip
    result = depth(ids, [deployed], holders={(TOKEN_ID, "testnet"): (TEAM,)},
                   has_package=True, in_code=frozenset())  # fmt: skip
    assert result.on_paper == (
        f"Its topic {TOPIC_ID} has no message.",
        f"Its token {TOKEN_ID} is held only by accounts that the project names.",
        f"Its contract {CONTRACT_ID} was never called after its deployment.",
        "Its code names a Hedera package, and calls no Hedera service.",
    )  # in the order of its own IDs, then the code
    nobody = depth(own((TOKEN_ID, TOKEN)), [], holders={(TOKEN_ID, "testnet"): ()})
    assert nobody.on_paper == (f"No account holds its token {TOKEN_ID} now.",)
    hbar = depth(own((TEAM, ACCOUNT)), [done(STARTS, TEAM, ACCOUNT, HBAR,
                                             Act("CRYPTOTRANSFER", True, TEAM, ()))])  # fmt: skip
    assert "Its own accounts only moved HBAR" in hbar.on_paper[0]
    shared = depth((), [], shared_only=True)
    assert shared.on_paper == ("Every Hedera ID that it names is named by other projects too: it "
                               "has no ID of its own.",)  # fmt: skip


def test_an_evm_project_set_up_for_hedera_is_not_said_to_call_nothing() -> None:
    result = depth((), [], has_package=True, in_code=frozenset(), set_up=frozenset({CONTRACTS}))
    assert result.on_paper == ()


def test_the_page_own_words_about_hedera_are_quoted_as_written() -> None:
    words = ("A booking app. We log each booking on the Hedera Consensus Service.\n"
             "Payments use HTS tokens! Nothing else here. " + "Hedera " + "x" * 400)  # fmt: skip
    said = page_said(words)
    assert said[:2] == ("We log each booking on the Hedera Consensus Service.",
                        "Payments use HTS tokens!")  # fmt: skip
    assert len(said) == 3 and said[2].endswith("…") and len(said[2]) == LONGEST_SAID + 1


def test_the_strip_draws_each_service_on_its_row_with_its_shade() -> None:
    items = [message(STARTS, n=n) for n in range(9)]
    items.append(message(STARTS + timedelta(days=1), n=20))
    items.append(done(STARTS, TOKEN_ID, TOKEN, TOKENS, Act("TOKENMINT", True, None, ()), 30))
    result = depth(own((TOPIC_ID, TOPIC), (TOKEN_ID, TOKEN)), items)
    view = strip_view(result.strip)
    assert [row.service for row in view.rows] == [CONSENSUS, TOKENS]
    busiest, quiet = view.rows[0].squares
    assert (busiest.ink, quiet.ink) == (1.0, LIGHTEST)
    assert busiest.note == "3 April 2026: 9 Consensus Service transactions"
    assert view.rows[1].squares[0].note == "3 April 2026: 1 Token Service transaction"
    assert [mark.text for mark in view.marks] == ["4 March 2026", "the event", "5 May 2026"]
    assert [row.name for row in view.rows] == ["Consensus", "Tokens"]
    assert len(view.table) == 3 and view.outside == "Before that time: none. After it: none."
    assert strip_view(None) is None
