"""An invented repository on a stand-in GitHub, and an invented topic on a stand-in mirror node,
for the tests of the check of a submission (design 12.1, S3)."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import SecretStr

from fakes import FakeSite, FakeTime, Reply, StandInMirror, session_for
from hackathon_memory.collect.github import GitHubClient, allowed, readme_address
from hackathon_memory.collect.github_facts import facts_address
from hackathon_memory.collect.polite import CollectorIdentity, RequestCount

REPO = "https://github.com/sample-org/pebble-pay"
NOW = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)
DURING = "1772884800.000000001"  # 7 March 2026, inside the window of the invented event
TOPIC = "0.0.3456789"
README = (
    "# Pebble Pay\n\nA vendor takes a coin. Our topic on testnet: 0.0.3456789.\n\n"
    "![logo](https://cdn.example.test/logo.png)\n\n```\nnpm install\n```\n"
    "See [the demo](https://demo.example.test) at <b>night</b>.\n"
)


def facts_answer(**changes: object) -> bytes:
    answer = {
        "html_url": REPO,
        "created_at": "2026-03-06T17:00:00Z",
        "pushed_at": "2026-03-08T10:00:00Z",
        "fork": False,
        "archived": False,
        "language": "TypeScript",
        "owner": {"login": "invented-owner"},
    }
    answer.update(changes)
    return json.dumps(answer).encode()


def readme_answer(text: str = README) -> bytes:
    raw = text.encode("utf-8")
    content = base64.encodebytes(raw).decode()
    answer = {"encoding": "base64", "name": "README.md", "size": len(raw), "content": content}
    return json.dumps(answer).encode()


def github(tmp_path: Path, pages: dict[str, Reply]) -> tuple[GitHubClient, FakeSite]:
    """The polite client of GitHub, with its real headers, over a stand-in site."""
    site = FakeSite(pages)
    clock = FakeTime()
    client = GitHubClient(
        token=SecretStr("github_pat_INVENTED"),
        site="api.github.com",
        identity=CollectorIdentity(name="TestTool-research", contact="owner@example.test"),
        allow=allowed,
        is_enabled=lambda: True,
        session=session_for(site),
        count=RequestCount(tmp_path / "count.json", "api.github.com", limit=50),
        pause_seconds=1.0,
        clock=clock.clock,
        sleep=clock.sleep,
        now=lambda: NOW,
    )
    return client, site


def found_code(tmp_path: Path, text: str = README) -> tuple[GitHubClient, FakeSite]:
    """GitHub knows the repository REPO, with a README that names the topic."""
    return github(tmp_path, {facts_address(REPO): Reply(200, facts_answer()),
                             readme_address(REPO): Reply(200, readme_answer(text))})  # fmt: skip


def nodes() -> dict[str, StandInMirror]:
    """The test network knows the topic, made and used during the invented event."""
    test = StandInMirror("testnet", topic={TOPIC: {"topic_id": TOPIC, "created_timestamp": DURING}})
    test.lists[("messages", TOPIC)] = [
        {"sequence_number": 1, "consensus_timestamp": DURING},
        {"sequence_number": 7, "consensus_timestamp": DURING},
    ]
    return {"testnet": test, "mainnet": StandInMirror("mainnet")}
