"""The depth of use of a project's own Hedera IDs (check/depth.py, design 7.5) and the drawing of
its strip of days (web/strips.py). Every ID, account and date is invented."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from hackathon_memory.check.depth import (
    Done,
    depth_of,
    kinds_in_words,
)
from hackathon_memory.check.history import CONSENSUS, CONTRACTS, HBAR, TOKENS, Act
from hackathon_memory.check.story import OwnId
from hackathon_memory.parse.hedera_ids import ACCOUNT, CONTRACT, TOKEN, TOPIC
from hackathon_memory.web.strips import LIGHTEST, Mark, apart, length, strip_view

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
                    in_code=options.pop("in_code", None),
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
    items.append(done(datetime(2026, 8, 1, tzinfo=UTC), TEAM, ACCOUNT, HBAR,
                      Act("CRYPTOTRANSFER", True, TEAM, ()), 6))  # fmt: skip
    result = depth(own((TOPIC_ID, TOPIC), (TEAM, ACCOUNT)), items)
    assert (result.days, result.days_during, result.days_before, result.days_after) == (4, 2, 1, 1)
    assert result.strip is not None
    # it draws the days of its topic outside the time of the table too, and not those of its
    # account there: an account is often kept for years (28 October 2026)
    drawn = {one.day for _, days in result.strip.rows for one in days}
    assert {date(2026, 4, 20), date(2026, 9, 1)} <= drawn and date(2026, 8, 1) not in drawn


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
    assert [mark.text for mark in view.marks] == ["4 Mar 2026", "the event", "5 May 2026"]
    assert [row.name for row in view.rows] == ["Consensus", "Tokens"]
    assert len(view.table) == 3
    # the days are a drawing of their own, placed from 0, with a short date for each day; at
    # most a week across the strip (28 October 2026)
    assert (view.marks[0].x, view.marks[-1].x) == (0, view.days_width)
    assert view.days == 63 and len(view.ticks) == 63
    assert (view.ticks[0].text, view.ticks[-1].text) == ("4 Mar", "5 May")
    assert view.most_zoom == 9.0 and view.names_share == 18.0
    assert view.cuts == () and view.step == round(view.days_width / 63, 4)
    assert all(0 <= square.x < view.days_width for row in view.rows for square in row.squares)
    assert strip_view(None) is None


def test_a_long_time_without_a_transaction_is_cut_out_of_the_strip() -> None:
    """A contract busy a year before the event and a topic busy 40 days after the time of the
    table: two times without a transaction are cut out, each a band with its length, and the
    days around the event keep their width (28 October 2026)."""
    long_before = datetime(2025, 3, 10, tzinfo=UTC)
    items = [done(long_before + timedelta(days=n), CONTRACT_ID, CONTRACT, CONTRACTS,
                  Act("CONTRACTCALL", True, TEAM, ()), n) for n in range(3)]  # fmt: skip
    items += [message(STARTS, n=10), message(datetime(2026, 6, 14, tzinfo=UTC), n=11)]
    view = strip_view(depth(own((TOPIC_ID, TOPIC), (CONTRACT_ID, CONTRACT)), items).strip)
    assert [cut.text for cut in view.cuts] == ["1 yr", "39 days"]
    assert view.cuts[0].note == ("No transaction for 1 year, from 13 March 2025 to 3 March "
                                 "2026: left out of the strip.")  # fmt: skip
    assert view.days == 3 + 63 + 1  # the days drawn: three, the time of the table, one
    assert view.step == round((view.days_width - 2 * 14) / 67, 4)
    first, second = view.cuts
    squares = {row.service: [square.x for square in row.squares] for row in view.rows}
    assert squares[CONTRACTS][0] == 0 and squares[CONTRACTS][-1] < first.x < view.event_x
    assert view.event_x < second.x < squares[CONSENSUS][-1] < view.days_width
    assert [mark.text for mark in view.cut_marks] == ["1 yr", "39 days"]
    assert view.height == 4 + 2 * 20 + 20 + 16  # one more line, for the lengths


def test_an_event_with_no_transaction_is_drawn_beside_the_days_after_it() -> None:
    """Its things were used only a year after its event, as when the dates do not fit: the strip
    draws the event, empty, and the days of its things after a cut (28 October 2026). Before, it
    drew no strip at all."""
    later = datetime(2027, 4, 14, tzinfo=UTC)
    items = [done(later + timedelta(days=n), CONTRACT_ID, CONTRACT, CONTRACTS,
                  Act("CONTRACTCALL", True, TEAM, ()), n) for n in range(3)]  # fmt: skip
    result = depth(own((CONTRACT_ID, CONTRACT)), items)
    assert (result.days, result.total) == (0, 0)  # nothing in the time of the table
    view = strip_view(result.strip)
    assert view is not None and [cut.text for cut in view.cuts] == ["11 mo"]
    assert 0 < view.event_x < view.cuts[0].x
    assert [mark.text for mark in view.marks][:2] == ["4 Mar 2026", "the event"]


def test_the_lengths_and_the_marks_of_the_strip() -> None:
    assert length(31) == ("31 days", "31 days")
    assert length(365) == ("1 yr", "1 year")
    assert length(437) == ("1 yr 2 mo", "1 year and 2 months")
    assert length(250) == ("8 mo", "8 months")
    # a mark that would touch one before it in the list is left out; one of the middle stays
    # inside the drawing
    marks = apart([Mark(320, "the event", "middle", event=True), Mark(0, "4 Mar 2026", "start"),
                   Mark(328, "5 May 2026", "end")], 328)  # fmt: skip
    assert [(mark.text, mark.x) for mark in marks] == [("4 Mar 2026", 0), ("the event", 295.6)]
