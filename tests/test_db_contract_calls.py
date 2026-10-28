"""The store of the calls of the own contracts (db/contract_calls.py, migration 0020), on a real
PostgreSQL. Everything is invented."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import psycopg
import pytest

from fakes import PROJECT_PAGE, project_page
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.proof import PROOF_FOUND
from hackathon_memory.check.story import time_of
from hackathon_memory.check.system_calls import ContractCalls
from hackathon_memory.db.contract_calls import ContractCallStore, ContractToRead
from hackathon_memory.db.history import calls_of
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_ids import CONTRACT

pytestmark = pytest.mark.integration

STARTS, ENDS = datetime(2026, 3, 6, 12, tzinfo=UTC), date(2026, 3, 8)
SPAN = time_of(STARTS, ENDS)
MADE = datetime(2026, 3, 7, tzinfo=UTC)


@pytest.fixture
def database(empty_database: str) -> str:
    """One project whose page names the contract 0.0.5003, made during its event."""
    migrate(empty_database)
    page = project_page(description="<p>Our escrow is the contract 0.0.5003.</p>")
    ProjectStore(empty_database).save(read_project_page(page, PROJECT_PAGE), "a" * 64)
    with psycopg.connect(empty_database) as conn:
        conn.execute("UPDATE events SET starts_at = %s, ends_on = %s", (STARTS, ENDS))
    ledger = LedgerStore(empty_database)
    ledger.save_facts(LedgerFacts("0.0.5003", "testnet", MADE, found=True, kind=CONTRACT,
                                  ledger_id="0.0.5003", created_at=MADE))  # fmt: skip
    for item in ledger.ids_to_check():
        ledger.save_checks(item.project_id, {item.hedera_id: {"testnet": PROOF_FOUND}},
                           PROOF_FOUND)  # fmt: skip
    return empty_database


def test_an_own_contract_is_read_in_the_time_of_its_story(database: str) -> None:
    store = ContractCallStore(database)
    assert SPAN is not None
    assert store.to_read() == [ContractToRead("0.0.5003", "testnet", "0.0.5003", *SPAN)]
    calls = ContractCalls("0.0.5003", "testnet", *SPAN, 2, False, {"0.0.359": 1})
    store.save(calls, SPAN[1] + timedelta(days=1))  # read when that time was over
    assert store.to_read() == []
    with psycopg.connect(database) as conn:
        assert calls_of(conn, [("0.0.5003", "testnet")], SPAN) == [calls]
        assert calls_of(conn, [("0.0.5003", "mainnet")], SPAN) == []


def test_a_contract_read_before_its_time_was_over_is_read_again(database: str) -> None:
    store = ContractCallStore(database)
    assert SPAN is not None
    early = ContractCalls("0.0.5003", "testnet", *SPAN, 1, False, {})
    store.save(early, SPAN[1] - timedelta(days=2))
    assert [one.entity_id for one in store.to_read()] == ["0.0.5003"]


def test_a_reading_again_waits_for_the_age_while_the_time_is_open(database: str) -> None:
    """The step `refresh` and the rounds of the website read again a contract read while its time
    was open only when that reading is older than their age (design 7.5, 28 October 2026)."""
    store = ContractCallStore(database)
    assert SPAN is not None
    asked = SPAN[1] - timedelta(days=2)
    store.save(ContractCalls("0.0.5003", "testnet", *SPAN, 1, False, {}), asked)
    day = timedelta(days=1)
    assert store.to_read(older_than=day, now=asked + timedelta(hours=2)) == []
    assert len(store.to_read(older_than=day, now=asked + timedelta(days=2))) == 1
