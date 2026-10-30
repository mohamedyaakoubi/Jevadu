"""The store of who made the own things (db/makers.py, migration 0021), on a real PostgreSQL.
Everything is invented."""

from __future__ import annotations

from datetime import UTC, date, datetime

import psycopg
import pytest

from fakes import PROJECT_PAGE, project_page
from hackathon_memory.check.history import CONTRACTS, Act, History
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.proof import PROOF_FOUND
from hackathon_memory.db.history import HistoryStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.makers import MakerStore, ThingToAsk
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_ids import CONTRACT, TOPIC

pytestmark = pytest.mark.integration

STARTS, ENDS = datetime(2026, 3, 6, 12, tzinfo=UTC), date(2026, 3, 8)
MADE = datetime(2026, 3, 7, 9, 30, 15, 123456, tzinfo=UTC)
ASKED = datetime(2026, 10, 29, 22, tzinfo=UTC)


@pytest.fixture
def database(empty_database: str) -> str:
    """One project whose page names the contract 0.0.5003 and the topic 0.0.5004, both made
    during its event; the history of the contract holds its creation, paid by 0.0.7001."""
    migrate(empty_database)
    page = project_page(description="<p>Our escrow is the contract 0.0.5003, and our log the "
                                    "topic 0.0.5004.</p>")  # fmt: skip
    ProjectStore(empty_database).save(read_project_page(page, PROJECT_PAGE), "a" * 64)
    with psycopg.connect(empty_database) as conn:
        conn.execute("UPDATE events SET starts_at = %s, ends_on = %s", (STARTS, ENDS))
    ledger = LedgerStore(empty_database)
    for entity, kind in (("0.0.5003", CONTRACT), ("0.0.5004", TOPIC)):
        ledger.save_facts(LedgerFacts(entity, "testnet", ASKED, found=True, kind=kind,
                                      ledger_id=entity, created_at=MADE))  # fmt: skip
    for item in ledger.ids_to_check():
        ledger.save_checks(item.project_id, {item.hedera_id: {"testnet": PROOF_FOUND}},
                           PROOF_FOUND)  # fmt: skip
    stamp = f"{MADE.timestamp():.6f}000"
    made = Act("CONTRACTCREATEINSTANCE", True, "0.0.7001", ("0.0.7001",))
    history = History({stamp: CONTRACTS}, False, {stamp: made})
    HistoryStore(empty_database).save("0.0.5003", "testnet", CONTRACT, history, ASKED)
    return empty_database


def test_each_own_thing_is_asked_once_with_the_payer_its_history_holds(database: str) -> None:
    store = MakerStore(database)
    assert store.to_ask() == [
        ThingToAsk("0.0.5003", "testnet", CONTRACT, "0.0.5003", MADE, "0.0.7001"),
        ThingToAsk("0.0.5004", "testnet", TOPIC, "0.0.5004", MADE, None),
    ]
    store.save("0.0.5003", "testnet", "0.0.7001", ASKED)
    store.save("0.0.5004", "testnet", None, ASKED)  # the node gave none: asked all the same
    assert store.to_ask() == []
    with psycopg.connect(database) as conn:
        kept = conn.execute("SELECT entity_id, made_by FROM ledger_facts ORDER BY 1").fetchall()
        assert kept == [("0.0.5003", "0.0.7001"), ("0.0.5004", None)]
        with pytest.raises(psycopg.errors.CheckViolation):  # an account, or nothing
            conn.execute("UPDATE ledger_facts SET made_by = 'Pyth' WHERE entity_id = '0.0.5003'")
