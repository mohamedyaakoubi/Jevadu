"""The IDs of a submission's code in its check (check/submission.py, design 7.3), on a real
PostgreSQL and a stand-in mirror node. Every repository, ID and date is invented."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fakes import StandInMirror
from hackathon_memory.check.proof import Window
from hackathon_memory.check.submission import judge_code_ids
from hackathon_memory.collect.github_code import READ, CodeRead
from hackathon_memory.db.code_ids import CodeIdStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.parse.hedera_code import CodeScan, IdInCode, Seen
from hackathon_memory.parse.hedera_ids import find_ids
from searchfakes import ids_of, three_projects

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)
DURING = "1772884800.000000001"  # 7 March 2026
LONG_BEFORE = "1736899200.000000001"  # 15 January 2025
EVENT = Window(datetime(2026, 2, 4, tzinfo=UTC), datetime(2026, 3, 22, tzinfo=UTC))
CHECKED = "https://github.com/sample-org/new-submission"


def scan_of(*ids: str) -> CodeScan:
    return CodeScan(files=4, ids={(one, None): IdInCode(one, None, Seen(1, [f"src/{one}.ts"]))
                                  for one in ids})  # fmt: skip


def test_a_check_weighs_the_own_ids_of_its_code_on_its_hackathon(empty_database: str) -> None:
    database = three_projects(empty_database)
    repositories = RepositoryStore(database)
    other = "https://github.com/sample-org/another-team"
    repositories.link({ids_of(database)["Cedar Post"]: other})
    repositories.save_code(other, CodeRead(READ, scan_of("0.0.7000003"), "2026-03-09T00:00:00Z"))
    made = {"created_timestamp": DURING}
    mirrors = {
        "testnet": StandInMirror("testnet", account={
            "0.0.7000001": {"account": "0.0.7000001", **made},
            "0.0.7000003": {"account": "0.0.7000003", **made},
        }, token={"0.0.6000002": {"token_id": "0.0.6000002", "total_supply": "5",
                                  "created_timestamp": LONG_BEFORE,
                                  "modified_timestamp": DURING}}),
        "mainnet": StandInMirror("mainnet"),
    }  # fmt: skip
    # Its own account made during the event, a public token made long before, an account that
    # another team's code names, and the topic that its README names.
    scan = scan_of("0.0.7000001", "0.0.6000002", "0.0.7000003", "0.0.4870201")
    readme = find_ids("Our log is the topic 0.0.4870201.")
    stores = (LedgerStore(database), CodeIdStore(database))
    results, not_judged = judge_code_ids(scan, readme, EVENT, mirrors, *stores, CHECKED,
                                         now=lambda: NOW)  # fmt: skip
    assert [(one.found.entity_id, one.status, one.network, one.in_code) for one in results] == [
        ("0.0.7000001", "proof_found", "testnet", "src/0.0.7000001.ts")]  # fmt: skip
    assert not_judged == 0
    asked = {question[1] for question in mirrors["testnet"].asked}
    assert "0.0.7000003" not in asked and "0.0.4870201" not in asked  # not its own, or the README's
    # Without a hackathon nothing can be weighed: the check says how many own IDs the code names.
    results, not_judged = judge_code_ids(scan, readme, None, mirrors, *stores, CHECKED,
                                         now=lambda: NOW)  # fmt: skip
    assert results == [] and not_judged == 2
    assert judge_code_ids(None, readme, EVENT, mirrors, *stores, CHECKED,
                          now=lambda: NOW) == ([], 0)  # fmt: skip
