"""An invented repository on a stand-in GitHub, and an invented topic on a stand-in mirror node,
for the tests of the check of a submission (design 12.1, S3)."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import SecretStr

from fakes import FakeSite, FakeTime, Reply, StandInMirror, archive, session_for
from hackathon_memory.collect.github import (
    GitHubClient,
    allowed,
    archive_address,
    readme_address,
)
from hackathon_memory.collect.github_commits import commits_address
from hackathon_memory.collect.github_facts import facts_address
from hackathon_memory.collect.polite import CollectorIdentity, RequestCount
from hackathon_memory.hedera.register import MessageSubmitted

REPO = "https://github.com/sample-org/pebble-pay"
REGISTER = "0.0.7654329"  # the invented topic of the register
NOW = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)
DURING = "1772884800.000000001"  # 7 March 2026, inside the window of the invented event
TOPIC = "0.0.3456781"
COMMIT = "7260ea7290637399c6ac181ed893a567144d96eb"  # an invented commit ID
README = (
    "# Pebble Pay\n\nA vendor takes a coin. Our topic on testnet: 0.0.3456781.\n\n"
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
        "default_branch": "main",
        "owner": {"login": "invented-owner"},
    }
    answer.update(changes)
    return json.dumps(answer).encode()


def readme_answer(text: str = README) -> bytes:
    raw = text.encode("utf-8")
    content = base64.encodebytes(raw).decode()
    answer = {"encoding": "base64", "name": "README.md", "size": len(raw), "content": content}
    return json.dumps(answer).encode()


def commits_answer(sha: str = COMMIT) -> bytes:
    """The newest commit, in the shape GitHub gave on 18 October 2026, with invented people."""
    person = {"name": "Invented Person", "email": "invented@example.test",
              "date": "2026-03-08T09:30:00Z"}  # fmt: skip
    commit = {"author": person, "committer": person, "message": "Invented message",
              "tree": {"sha": "f" * 40}, "comment_count": 0}  # fmt: skip
    return json.dumps([{"sha": sha, "commit": commit, "author": {"login": "invented"},
                        "committer": {"login": "invented"}, "parents": []}]).encode()  # fmt: skip


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


DOWNLOAD = "https://codeload.github.com/sample-org/pebble-pay/legacy.tar.gz/refs/heads/main"
CODE_FILES = {
    "package.json": b'{"dependencies": {"@hashgraph/sdk": "^2"}}',
    "src/topic.ts": b'import { TopicMessageSubmitTransaction } from "@hashgraph/sdk";\n',
}


def found_code(tmp_path: Path, text: str = README) -> tuple[GitHubClient, FakeSite]:
    """GitHub knows the repository REPO, with a README that names the topic, and code that
    calls the Consensus Service."""
    return github(tmp_path, {facts_address(REPO): Reply(200, facts_answer()),
                             readme_address(REPO): Reply(200, readme_answer(text)),
                             commits_address(REPO): Reply(200, commits_answer()),
                             archive_address(REPO): Reply(302, b"", {"Location": DOWNLOAD}),
                             DOWNLOAD: Reply(200, archive(CODE_FILES))})  # fmt: skip


def nodes() -> dict[str, StandInMirror]:
    """The test network knows the topic, made and used during the invented event."""
    test = StandInMirror("testnet", topic={TOPIC: {"topic_id": TOPIC, "created_timestamp": DURING}})
    test.lists[("messages", TOPIC)] = [
        {"sequence_number": 1, "consensus_timestamp": DURING},
        {"sequence_number": 7, "consensus_timestamp": DURING},
    ]
    return {"testnet": test, "mainnet": StandInMirror("mainnet")}


@dataclass
class RegisterWrites:
    """Stands in for the writes to the register: each record lands on the stand-in test network,
    where the mirror node returns it, with a number and a time."""

    mirror: StandInMirror
    written: list[bytes] = field(default_factory=list)

    def __call__(self, payload: bytes) -> MessageSubmitted:
        messages = self.mirror.lists.setdefault(("register", REGISTER), [])
        number = len(messages) + 1
        messages.append(
            {
                "sequence_number": number,
                "consensus_timestamp": f"179158560{number}.000000001",
                "message": base64.b64encode(payload).decode(),
                "payer_account_id": "0.0.1001",
            }
        )
        self.written.append(payload)
        return MessageSubmitted(REGISTER, number, f"0.0.1001@179158560{number}.0", "ab")
