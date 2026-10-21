"""What the readings of the code found, counted (evals/code_findings.py). Every project,
repository and reading here is invented."""

from __future__ import annotations

import json
from pathlib import Path

import psycopg
import pytest

from evals import code_findings
from fakes import ARCHIVE_COMMIT, project_page
from hackathon_memory.collect.github_code import CodeRead
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_code import CodeScan, Seen
from hackathon_memory.settings import Settings

PEBBLE = "https://github.com/sample-org/pebble-pay"
CEDAR = "https://github.com/sample-org/cedar-lens"
FERN = "https://github.com/sample-org/fern-vote"
DAY = "2026-10-21T20:00:00Z"


def test_the_state_of_one_project_in_one_word() -> None:
    state = code_findings.state
    assert state(False, None, []) == "no_repository_on_github"
    assert state(True, None, []) == "not_read"
    assert state(True, "gone", []) == "gone_or_blocked"
    assert state(True, "read", ["mention", "sign"]) == "use"
    assert state(True, "partial", ["mention"]) == "mention_only"
    assert state(True, "read", []) == "nothing"


@pytest.mark.integration
def test_the_counts_hold_numbers_and_no_name(
    empty_database: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrate(empty_database)
    projects = ProjectStore(empty_database)
    for name, code in (("pebble-pay", PEBBLE), ("cedar-lens", CEDAR), ("fern-vote", FERN),
                       ("dune-notes", None)):  # fmt: skip
        html = project_page(name=name.replace("-", " ").title(), slug=name, code=code)
        projects.save(read_project_page(html, f"https://ethglobal.com/showcase/{name}-x1y2z"),
                      "a" * 64)  # fmt: skip
    store = RepositoryStore(empty_database)
    store.link({project_id: link for project_id, link in store.code_links().items()})
    used = CodeScan(files=9, commit=ARCHIVE_COMMIT, features={"Token Service": Seen(2, ["a.ts"])},
                    mentions=Seen(3, ["a.ts"]))  # fmt: skip
    store.save_code(PEBBLE, CodeRead("read", used, DAY))
    store.save_code(CEDAR, CodeRead("read", CodeScan(files=4, mentions=Seen(1, ["b.ts"])), DAY))
    with psycopg.connect(empty_database) as conn:  # as the check on the ledger leaves them
        conn.execute("UPDATE projects SET proof_status = 'no_id_given'")
        conn.execute("UPDATE projects SET proof_status = 'proof_found' WHERE name = 'Cedar Lens'")
    found = code_findings.counts(empty_database)
    assert found["projects"]["all"] == {"use": 1, "mention_only": 1, "not_read": 1,
                                        "no_repository_on_github": 1}  # fmt: skip
    assert found["projects"]["no_prize"] == found["projects"]["all"]
    assert found["projects_with_no_hedera_id"]["all"] == {"use": 1, "not_read": 1,
                                                          "no_repository_on_github": 1}  # fmt: skip
    assert found["repositories_per_name"] == {"feature": {"Token Service": 1}}
    assert found["repositories_read"] == {"read": 2}

    settings = Settings(_env_file=None, database_url=empty_database)
    monkeypatch.setattr(code_findings, "RESULTS", tmp_path)
    assert code_findings.main([], settings) == 0
    (written,) = tmp_path.iterdir()
    text = written.read_text(encoding="utf-8")
    assert "pebble" not in text.lower() and "sample-org" not in text
    assert json.loads(text)["test"] == "code-findings"
