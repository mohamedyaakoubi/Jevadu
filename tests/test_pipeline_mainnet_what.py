"""The step `mainnet_what` (pipeline/mainnet_what.py), with a stand-in store and mirror node: one
invented project with a topic, a contract, a scheduled transaction and an account on the main
network, and the accounts that made them. Everything is invented."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from test_check_mainnet_what import SOURCE, scheduled

from fakes import StandInMirror
from hackathon_memory.check.mainnet_what import (
    DEPLOYED,
    SCHEDULE_RAN,
    Thing,
    long_zero,
    selector,
)
from hackathon_memory.db.mainnet import OwnThing
from hackathon_memory.db.runs import Run
from hackathon_memory.hedera.mirror import MirrorError, stamp_of
from hackathon_memory.pipeline.check_ids import NodeIsAway
from hackathon_memory.pipeline.mainnet_what import (
    MAX_ACCOUNTS,
    STEP,
    explain_mainnet,
    mainnet_what_lines,
)

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
MADE = datetime(2026, 5, 28, tzinfo=UTC)
SINCE = MADE - timedelta(days=30)
REPOSITORY = "https://github.com/someone/shop"


def at(seconds: int) -> str:
    return f"{int(MADE.timestamp()) + seconds}.000000001"


S1, S2, S3, C0, C1, C2, SC, E1, A1 = (at(n) for n in range(10, 100, 10))
TOPIC, CONTRACT, SCHEDULE, ACCOUNT = "0.0.5001", "0.0.5002", "0.0.5003", "0.0.5004"


class StandInStore:
    def __init__(self, *things: OwnThing) -> None:
        self.things = list(things)
        self.explained: dict[str, tuple[str | None, tuple[str, ...]]] = {}
        self.saved: dict[str, Thing] = {}
        self.followed: dict[str, str] = {}

    def own_things(self, *, projects: set[int] | None = None) -> list[OwnThing]:
        del projects  # the stand-in holds one project
        return [replace(one, todo=tuple(s for s in one.todo if s not in self.explained))
                for one in self.things]  # fmt: skip

    def makers(self) -> dict[str, str | None]:
        return {key: thing.made_by for key, thing in self.saved.items()}

    def explain(self, stamp: str, what: str | None, networks: tuple, asked_at: datetime) -> None:
        self.explained.setdefault(stamp, (what, tuple(networks)))

    def save_thing(self, thing: Thing, asked_at: datetime) -> None:
        self.saved[thing.entity_id] = thing

    def mark_followed(self, account: str, how: str, asked_at: datetime) -> None:
        self.followed[account] = how


def message(stamp: str, number: int, content: dict) -> dict:
    return {"consensus_timestamp": stamp, "sequence_number": number,
            "message": base64.b64encode(json.dumps(content).encode()).decode()}  # fmt: skip


def paid(account: str, stamp: str, name: str, entity: str | None = None) -> dict:
    return {"consensus_timestamp": stamp, "name": name, "result": "SUCCESS", "entity_id": entity,
            "transaction_id": f"{account}-{stamp.split('.')[0]}-1"}  # fmt: skip


def project() -> tuple[StandInStore, StandInMirror]:
    store = StandInStore(
        OwnThing(TOPIC, TOPIC, "topic", MADE, "0.0.7001", REPOSITORY, SINCE, (S1, S2, S3)),
        OwnThing("0x" + "cd" * 20, CONTRACT, "contract", MADE, "0.0.7002", REPOSITORY, SINCE,
                 (C0, C1, C2)),
        OwnThing(SCHEDULE, SCHEDULE, "schedule", MADE, "0.0.7001", REPOSITORY, SINCE, (SC,)),
        OwnThing(ACCOUNT, ACCOUNT, "account", MADE, None, REPOSITORY, SINCE, (E1, A1)),
    )  # fmt: skip
    mirror = StandInMirror(
        "mainnet",
        topic={TOPIC: {"memo": "shop receipts"}},
        contract={CONTRACT: {"memo": ""}},
        schedule={SCHEDULE: scheduled("payout", E1, -200_000_000, 200_000_000)},
        token={"0.0.6001": {"symbol": "INV"},
               "0.0.6100": {"name": "Side Token", "symbol": "SIDE",
                            "treasury_account_id": "0.0.7001"}},
        account={"0.0.7002": {"evm_address": "0x" + "ab" * 20}},
    )  # fmt: skip
    mirror.lists[("messages", TOPIC)] = [
        message(S1, 1, {"event": "Paid", "chainId": 8453}),
        message(S2, 2, {"event": "Paid", "chainId": 8453}),
        message(S3, 3, {"event": "Refused"}),
    ]
    launch = selector("launch((string,string,address,uint256),address)")
    mirror.lists[("calls", CONTRACT)] = [
        {"timestamp": C0, "created_contract_ids": [CONTRACT], "function_parameters": "0x6080"},
        {"timestamp": C1, "function_parameters": launch + "00" * 64},
        {"timestamp": C2, "function_parameters": "0xdeadbeef"},
    ]  # fmt: skip
    moved = [{"token_id": "0.0.6001", "amount": 5}]
    mirror.at_moment = {A1: {"consensus_timestamp": A1, "token_transfers": moved}}
    mirror.made = [paid("0.0.7003", stamp_of(MADE), "CRYPTOCREATEACCOUNT", ACCOUNT)]
    mirror.lists[("transactions", "0.0.7001")] = [
        paid("0.0.7001", at(200), "TOKENCREATION", "0.0.6100"),
        paid("0.0.7001", at(210), "CONSENSUSCREATETOPIC", TOPIC),  # its own: not kept again
    ]
    mirror.lists[("holders", "0.0.6100")] = ["0.0.7001", "0.0.8001"]
    mirror.lists[("from", long_zero("0.0.7002"))] = [
        {"timestamp": at(300), "created_contract_ids": [CONTRACT, "0.0.6200"]},
    ]
    mirror.lists[("transactions", "0.0.7003")] = [
        paid("0.0.7003", at(400 + n), "CRYPTOCREATEACCOUNT", f"0.0.{90000 + n}")
        for n in range(MAX_ACCOUNTS + 1)
    ]  # a service that makes accounts for many people
    return store, mirror


def run_once(store: StandInStore, mirror: StandInMirror, code_of=None) -> Run:  # noqa: ANN001
    run = Run(id=1, step=STEP)
    explain_mainnet(store, {"mainnet": mirror}, code_of, run, now=lambda: NOW)  # type: ignore[arg-type]
    return run


def test_each_transaction_is_explained_in_the_words_of_the_ledger_and_the_code() -> None:
    store, mirror = project()
    asked: list[str] = []
    run = run_once(store, mirror, lambda repository: asked.append(repository)
                   or [("contracts/Shop.sol", SOURCE)])  # fmt: skip
    assert store.explained[S1] == ("Paid", ("eip155:8453",))
    assert store.explained[S3] == ("Refused", ())
    assert store.explained[C0] == (DEPLOYED, ())
    assert store.explained[C1] == ("launch", ())
    assert store.explained[C2] == ("call 0xdeadbeef", ())
    assert store.explained[SC] == (None, ())  # the creation of the schedule: its kind says it
    assert store.explained[E1] == (SCHEDULE_RAN, ())  # the account's moment, named by its schedule
    assert store.explained[A1] == ("moved INV", ())
    assert asked == [REPOSITORY]
    assert run.counts["mainnet_explained"] == 9  # S1 to A1, each moment once


def test_the_things_are_kept_with_their_facts_and_their_makers() -> None:
    store, mirror = project()
    run_once(store, mirror, lambda repository: [("contracts/Shop.sol", SOURCE)])
    topic, contract = store.saved[TOPIC], store.saved[CONTRACT]
    assert (topic.name, topic.fields, topic.messages) == ("shop receipts", ("chainId", "event"), 3)
    assert contract.names_from == "its own code (contracts/Shop.sol)"
    schedule = store.saved[SCHEDULE]
    assert (schedule.name, schedule.scheduled, schedule.executed) == (
        "payout", "a transfer of 2 HBAR", E1)  # fmt: skip
    assert store.saved[ACCOUNT].made_by == "0.0.7003"  # asked: the payer of its creation


def test_the_accounts_that_made_the_ids_are_followed_but_not_a_service() -> None:
    store, mirror = project()
    run = run_once(store, mirror)
    side = store.saved["0.0.6100"]
    assert (side.kind, side.name, side.made_by, side.held_by_others) == (
        "token", "Side Token (SIDE)", "0.0.7001", 1)  # fmt: skip
    assert store.saved["0.0.6200"].kind == "contract"  # deployed from its EVM address
    assert store.saved["0.0.6200"].made_by == "0.0.7002"
    assert ("from", "0x" + "ab" * 20) in mirror.asked  # its alias is asked too
    assert store.followed == {"0.0.7001": "read", "0.0.7002": "read", "0.0.7003": "service",
                              ACCOUNT: "read"}  # fmt: skip
    assert not any(key.startswith("0.0.900") for key in store.saved)
    assert run.counts["mainnet_things_followed"] == 2
    assert run.counts["mainnet_services_not_followed"] == 1
    assert mainnet_what_lines(run)[1:] == [
        "Things that the same accounts made there, read: 2.",
        f"Accounts not followed, because they made more than {MAX_ACCOUNTS} accounts: 1.",
    ]


def test_a_second_run_explains_nothing_again_and_asks_github_nothing() -> None:
    store, mirror = project()
    run_once(store, mirror, lambda repository: [("contracts/Shop.sol", SOURCE)])
    asked: list[str] = []
    again = run_once(store, mirror, lambda repository: asked.append(repository) or [])
    assert again.counts["mainnet_explained"] == 0 and asked == []
    assert len(store.explained) == 9


def test_github_failing_leaves_the_names_of_the_common_library() -> None:
    store, mirror = project()

    def refused(repository: str) -> list:
        raise RuntimeError(f"GitHub refused {repository}")

    run = run_once(store, mirror, refused)
    assert store.explained[C1][0].startswith("call 0x")
    assert any("Solidity" in problem["what"] for problem in run.problems)


def test_five_errors_of_the_node_in_a_row_stop_the_step() -> None:
    store, mirror = project()

    class Away(StandInMirror):
        def schedule(self, entity: str) -> dict | None:
            raise MirrorError("mirror node unreachable (ConnectionError)")

        def topic_history(self, *args: object, **kwargs: object) -> tuple:
            raise MirrorError("mirror node unreachable (ConnectionError)")

        def contract_history(self, *args: object, **kwargs: object) -> tuple:
            raise MirrorError("mirror node unreachable (ConnectionError)")

        def transaction_at(self, stamp: str) -> dict | None:
            raise MirrorError("mirror node unreachable (ConnectionError)")

        def account_history(self, *args: object, **kwargs: object) -> tuple:
            raise MirrorError("mirror node unreachable (ConnectionError)")

    fifth = OwnThing("0.0.5009", "0.0.5009", "topic", MADE, None, None, SINCE, (at(5),))
    store.things.append(fifth)
    away = Away("mainnet")
    with pytest.raises(NodeIsAway):
        run_once(store, away)
    assert store.explained == {}
