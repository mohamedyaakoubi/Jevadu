"""Public services that many projects use (db/public_services.py, migration 0022), on a real
PostgreSQL: a project that names one does not own it. Everything is invented but the services."""

from __future__ import annotations

from datetime import UTC, date, datetime

import psycopg
import pytest

from fakes import PROJECT_PAGE, project_page
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.proof import PROOF_FOUND
from hackathon_memory.db.history import story_of_project
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.public_services import NamedService, public_keys, public_services_of
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_ids import CONTRACT, TOPIC

pytestmark = pytest.mark.integration

PYTH = "0xa2aa501b19aff244d90cc15a4cf739d2725b5729"
ASKED = datetime(2026, 10, 29, 22, tzinfo=UTC)


@pytest.fixture
def database(empty_database: str) -> str:
    """One project whose page gives Pyth's price oracle, by a HashScan link, and its own topic."""
    migrate(empty_database)
    page = project_page(description=(
        "<p>Prices come from <a href=\"https://hashscan.io/testnet/contract/" + PYTH + "\">Pyth</a>"
        ", and our log is the topic 0.0.5004.</p>"))  # fmt: skip
    ProjectStore(empty_database).save(read_project_page(page, PROJECT_PAGE), "a" * 64)
    with psycopg.connect(empty_database) as conn:
        conn.execute("UPDATE events SET starts_at = %s, ends_on = %s",
                     (datetime(2026, 3, 6, tzinfo=UTC), date(2026, 3, 8)))  # fmt: skip
    ledger = LedgerStore(empty_database)
    ledger.save_facts(LedgerFacts(PYTH, "testnet", ASKED, found=True, kind=CONTRACT,
                                  ledger_id="0.0.3042133", created_at=ASKED))  # fmt: skip
    ledger.save_facts(LedgerFacts("0.0.5004", "testnet", ASKED, found=True, kind=TOPIC,
                                  ledger_id="0.0.5004", created_at=ASKED))  # fmt: skip
    with psycopg.connect(empty_database) as conn:  # both found on the test network
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                     "SELECT id, 'testnet', %s FROM hedera_ids", (PROOF_FOUND,))  # fmt: skip
    return empty_database


def test_a_public_service_is_named_but_not_owned(database: str) -> None:
    with psycopg.connect(database) as conn:
        (project,) = conn.execute("SELECT id FROM projects").fetchone()
        assert public_services_of(conn, project) == (NamedService(
            PYTH, "the price oracle of Pyth",
            "https://github.com/pyth-network/pyth-crosschain/blob/main/contract_manager/src/store/"
            "contracts/EvmPriceFeedContracts.json", date(2026, 10, 29)),)  # fmt: skip
        story = story_of_project(conn, project, words="", in_code=None)
        assert story is not None and [one.entity_id for one in story.ids] == ["0.0.5004"]
        keys = public_keys(conn)
    assert {"testnet:0.0.3042133", f"testnet:{PYTH}", f"mainnet:{PYTH}", "mainnet:0.0.4622850",
            "mainnet:0.0.456858", "testnet:0.0.429274"} == keys  # fmt: skip
