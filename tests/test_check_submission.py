"""The check of one submission (check/submission.py, design 12.1 S3): GitHub asked once with the
promises of the collectors, the IDs of the README judged by the proof rule, the life rule, and
"seen before". A real PostgreSQL, a stand-in GitHub and a stand-in mirror node. Every page,
repository, ID and date is invented."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from checkfakes import (
    CODE_FILES,
    COMMIT,
    DOWNLOAD,
    DURING,
    NOW,
    README,
    REPO,
    TOPIC,
    commits_answer,
    facts_answer,
    found_code,
    github,
    nodes,
    readme_answer,
)
from fakes import ARCHIVE_COMMIT, Reply, StandInMirror, archive, project_page
from hackathon_memory.check import submission
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.submission import EventDays
from hackathon_memory.collect.answers import Answers
from hackathon_memory.collect.github import archive_address, readme_address
from hackathon_memory.collect.github_commits import commits_address
from hackathon_memory.collect.github_facts import facts_address
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.hedera.mirror import MirrorError
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.search import seen

OTHER = "https://github.com/sample-org/cedar-post"
EVENT = EventDays("ETHGlobal Sample Event", datetime(2026, 3, 6, 16, tzinfo=UTC), date(2026, 3, 8))
COLLECTOR = "TestTool-research/0.1.0"


@pytest.fixture
def database(empty_database: str) -> str:
    """Two projects of the collection: Pebble Pay with the same repository as the submission,
    and Cedar Post with its own."""
    migrate(empty_database)
    projects = ProjectStore(empty_database)
    for name, slug, code in (
        ("Pebble Pay", "pebble-pay", REPO),
        ("Cedar Post", "cedar-post", OTHER),
    ):
        page = f"https://ethglobal.com/showcase/{slug}-x1y2z"
        html = project_page(name=name, slug=slug, code=code)
        projects.save(read_project_page(html, page), "a" * 64)
    with psycopg.connect(empty_database) as conn:
        ids = dict(conn.execute("SELECT name, id FROM projects").fetchall())
        conn.execute("UPDATE events SET ends_on = '2026-03-08'")
    RepositoryStore(empty_database).link({ids["Pebble Pay"]: REPO, ids["Cedar Post"]: OTHER})
    return empty_database


def names_the_topic(database: str, name: str, status: str = "proof_found") -> None:
    """The project `name` names the topic on the test network, and the ledger judged it."""
    with psycopg.connect(database) as conn:
        (project,) = conn.execute("SELECT id FROM projects WHERE name = %s", (name,)).fetchone()
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, %s, 'testnet', 'topic', 'page', "
            "'invented', false) RETURNING id", (project, TOPIC)).fetchone()  # fmt: skip
        conn.execute(
            "INSERT INTO id_checks (hedera_id, network, status) VALUES (%s, 'testnet', %s)",
            (hedera_id, status),
        )


def more_projects(database: str, count: int) -> None:
    """`count` more projects, each with its own repository, that name the topic."""
    projects = ProjectStore(database)
    code = {"Pebble Pay": REPO, "Cedar Post": OTHER}
    for number in range(count):
        slug = f"extra-{number}"
        code[f"Extra {number}"] = f"https://github.com/o/{slug}"
        html = project_page(name=f"Extra {number}", slug=slug, code=code[f"Extra {number}"])
        page = f"https://ethglobal.com/showcase/{slug}-x1y2z"
        projects.save(read_project_page(html, page), "b" * 64)
    with psycopg.connect(database) as conn:
        ids = dict(conn.execute("SELECT name, id FROM projects").fetchall())
    RepositoryStore(database).link({ids[name]: link for name, link in code.items()})
    for number in range(count):
        names_the_topic(database, f"Extra {number}", "not_found")


def run(database: str, tmp_path: Path, client: object, mirrors: dict | None = None, **options):  # noqa: ANN003, ANN201
    return submission.check_submission(
        database, REPO, options.pop("event", EVENT), client=client,
        store=RawStore(tmp_path / "raw"), collector=COLLECTOR,
        mirrors=nodes() if mirrors is None else mirrors, now=lambda: NOW, **options,
    )  # fmt: skip


# ---------------------------------------------------------------------------- what is pasted


@pytest.mark.parametrize(
    ("pasted", "link"),
    [
        ("github.com/Sample-Org/Pebble-Pay", REPO),
        ("https://www.github.com/sample-org/pebble-pay/tree/main/src", REPO),
        ("  https://github.com/sample-org/pebble-pay.git  ", REPO),
        ("https://gitlab.com/sample-org/pebble-pay", None),
        ("pebble-pay", None),
        ("", None),
    ],
)
def test_a_pasted_link_becomes_the_link_of_a_repository(pasted: str, link: str | None) -> None:
    assert submission.repository_link(pasted) == link


def test_typed_days_make_a_time_only_in_their_order() -> None:
    assert submission.typed_days("2026-03-06", "2026-03-08") == (date(2026, 3, 6), date(2026, 3, 8))
    assert submission.typed_days("2026-03-08", "2026-03-06") is None  # the end before the start
    assert submission.typed_days("2026-03-06", "") is None
    assert submission.typed_days("1999-01-01", "1999-01-02") is None  # before any such event
    typed = submission.event_of_days(date(2026, 3, 6), date(2026, 3, 8))
    assert (
        typed.typed and typed.window is not None and typed.window.start.day == 4
    )  # 30 days before


def test_the_words_of_a_readme_leave_out_code_images_and_addresses() -> None:
    words = submission.readme_words(README)
    assert "npm install" not in words and "cdn.example.test" not in words and "<b>" not in words
    assert "See the demo at night ." in words and words.startswith("# Pebble Pay A vendor")
    assert len(submission.readme_words("word " * 2000)) == submission.LONGEST_TEXT


# ---------------------------------------------------------------------------- the check


@pytest.mark.integration
def test_the_check_asks_github_once_and_judges_the_ids_of_the_readme(
    database: str, tmp_path: Path
) -> None:
    client, site = found_code(tmp_path)
    mirrors = nodes()
    result = run(database, tmp_path, client, mirrors)
    assert site.urls == [facts_address(REPO), readme_address(REPO), commits_address(REPO),
                         archive_address(REPO), DOWNLOAD]  # fmt: skip
    assert result.version is not None and result.version.sha == COMMIT
    assert all(request.headers["From"] == "owner@example.test" for request in site.seen)
    code = result.hedera_code
    assert code is not None and code.status == "read" and code.saved and code.scan is not None
    assert code.scan.packages == {"@hashgraph/sdk": ["package.json"]}
    assert sorted(code.scan.features) == ["Consensus Service (topics)"]
    assert result.code is not None and result.code.language == "TypeScript"
    assert result.readme is not None and "Our topic on testnet" in result.readme_text
    assert [(one.found.entity_id, one.network, one.status) for one in result.ids] == [
        (TOPIC, "testnet", "proof_found")
    ]
    assert result.proof == "proof_found" and not result.problems
    assert mirrors["mainnet"].asked == []  # the README names the test network
    # The last push and the last message fall before the line of 30 days after the event, which
    # ended more than 90 days ago.
    assert result.life is not None and result.life.status == "stopped"
    assert [one.by for one in result.seen] == ["repository"]
    asked_before = len(mirrors["testnet"].asked)
    again = run(database, tmp_path, client, mirrors)  # a second check asks nobody again
    assert len(site.seen) == 5 and again.proof == "proof_found"
    assert again.hedera_code == code  # the saved reading
    assert len(mirrors["testnet"].asked) == asked_before  # the ledger's answer is in the table


@pytest.mark.integration
def test_reading_again_asks_the_ledger_at_once_and_a_plain_second_check_does_not(
    database: str, tmp_path: Path
) -> None:
    """A message sent a moment ago, such as a registration, shows only when the ledger is asked
    again: a second check takes its answers from the table for 7 days."""
    client, _ = found_code(tmp_path)
    mirrors = nodes()
    run(database, tmp_path, client, mirrors)
    asked_before = len(mirrors["testnet"].asked)
    run(database, tmp_path, client, mirrors)
    assert len(mirrors["testnet"].asked) == asked_before
    run(database, tmp_path, client, mirrors, again=True)
    assert len(mirrors["testnet"].asked) > asked_before


def test_a_check_read_again_asks_github_at_once_though_its_answers_are_young(
    database: str, tmp_path: Path
) -> None:
    """With the answers asked again (design 7.3): younger than an hour, a plain check asks nobody;
    "Read again now" asks, and GitHub's new README shows."""
    pages = {
        facts_address(REPO): Reply(200, facts_answer()),
        readme_address(REPO): [Reply(200, readme_answer("# Pebble Pay\n\nThe first words.\n")),
                               Reply(200, readme_answer("# Pebble Pay\n\nThe new words.\n"))],
        commits_address(REPO): Reply(200, commits_answer(ARCHIVE_COMMIT)),
        archive_address(REPO): Reply(302, b"", {"Location": DOWNLOAD}),
        DOWNLOAD: Reply(200, archive(CODE_FILES)),
    }  # fmt: skip
    client, site = github(tmp_path, pages)
    answers = Answers(tmp_path / "raw")

    def check(**options: bool) -> submission.SubmissionCheck:
        client.now = lambda: NOW
        return submission.check_submission(database, REPO, EVENT, client=client, store=answers,
                                           collector=COLLECTOR, mirrors=nodes(), now=lambda: NOW,
                                           **options)  # fmt: skip

    assert "first words" in check().readme_text
    asked = len(site.seen)
    assert "first words" in check().readme_text and len(site.seen) == asked
    assert "new words" in check(again=True).readme_text and len(site.seen) > asked


def test_a_check_asks_github_again_after_an_hour_and_finds_a_repository_made_public(
    database: str, tmp_path: Path
) -> None:
    """With the answers asked again (design 7.3, 25 October 2026): an answer younger than an hour
    is used, an older one is asked again. Before, a "not found" saved while a repository was
    private stayed for good."""
    pages = {
        facts_address(REPO): [Reply(404, b'{"message": "Not Found"}'), Reply(200, facts_answer())],
        readme_address(REPO): Reply(200, readme_answer()),
        commits_address(REPO): Reply(200, commits_answer(ARCHIVE_COMMIT)),
        archive_address(REPO): Reply(302, b"", {"Location": DOWNLOAD}),
        DOWNLOAD: Reply(200, archive(CODE_FILES)),
    }
    client, site = github(tmp_path, pages)
    answers = Answers(tmp_path / "raw")

    def check(minutes: int) -> submission.SubmissionCheck:
        at = NOW + timedelta(minutes=minutes)
        client.now = lambda: at
        return submission.check_submission(database, REPO, EVENT, client=client, store=answers,
                                           collector=COLLECTOR, mirrors=nodes(),
                                           now=lambda: at)  # fmt: skip

    private = check(0)
    assert private.code.status == "gone" and len(site.seen) == 1
    soon = check(30)
    assert soon.code.status == "gone" and len(site.seen) == 1  # younger than an hour
    public = check(120)
    assert public.code.status == "found" and public.hedera_code is not None
    assert public.version.sha == ARCHIVE_COMMIT and public.readme_text


@pytest.mark.integration
def test_the_same_id_found_for_another_project_is_seen_before(
    database: str, tmp_path: Path
) -> None:
    names_the_topic(database, "Cedar Post")
    result = run(database, tmp_path, found_code(tmp_path)[0])
    with psycopg.connect(database) as conn:
        ids = dict(conn.execute("SELECT name, id FROM projects").fetchall())
    assert [(one.project_id, one.by) for one in result.seen] == [
        (ids["Pebble Pay"], "repository"), (ids["Cedar Post"], f"testnet:{TOPIC}")]  # fmt: skip
    # Cedar Post has other code, so the activity of the topic is no sign of life of this one.
    assert result.ids[0].named_elsewhere and not result.ids[0].shared


@pytest.mark.integration
def test_an_id_that_many_projects_with_other_code_name_links_nothing(
    database: str, tmp_path: Path
) -> None:
    names_the_topic(database, "Cedar Post")
    more_projects(database, 2)  # Cedar Post, two more, and the submission: four with other code
    result = run(database, tmp_path, found_code(tmp_path)[0])
    assert result.ids[0].shared
    assert [one.by for one in result.seen] == ["repository"]


@pytest.mark.integration
def test_an_account_of_another_project_is_the_same_account_not_the_same_project(
    database: str,
) -> None:
    """A builder's testnet account that another project names is a link by the account alone
    (design 8.4, 1 November 2026)."""
    with psycopg.connect(database) as conn:
        (cedar,) = conn.execute("SELECT id FROM projects WHERE name = 'Cedar Post'").fetchone()
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, '0.0.4729347', 'testnet', 'account', "
            "'page', 'invented', false) RETURNING id", (cedar,)).fetchone()  # fmt: skip
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                     "VALUES (%s, 'testnet', 'proof_found')", (hedera_id,))  # fmt: skip
    LedgerStore(database).save_facts(LedgerFacts("0.0.4729347", "testnet", NOW, found=True,
                                                 kind="account"))  # fmt: skip
    known = seen.submission_matches(database, "https://github.com/someone/else",
                                    [("testnet", "0.0.4729347", "0.0.4729347")])  # fmt: skip
    assert known.same_id == {"account:testnet:0.0.4729347": [cedar]}


def test_a_use_in_the_window_that_another_project_may_explain_proves_nothing() -> None:
    """A builder's account, made in 2024 and used until October 2026, was used during ETHDenver
    2026 for another project of the builder; checked against ETHDenver 2026, a repository that
    names it got "proof found" from that use (1 November 2026). Only its own dates count now."""
    from hackathon_memory.check.proof import window_of
    from hackathon_memory.parse.hedera_ids import FoundId

    window = window_of(datetime(2026, 2, 18, 16, tzinfo=UTC), date(2026, 2, 21))
    facts = LedgerFacts("0.0.4729347", "testnet", NOW, found=True, kind="account",
                        created_at=datetime(2024, 8, 23, tzinfo=UTC),
                        first_activity_at=datetime(2024, 8, 23, tzinfo=UTC),
                        last_activity_at=datetime(2026, 10, 5, tzinfo=UTC))  # fmt: skip
    found = FoundId("0.0.4729347", "testnet", "account", "the account of the README")
    shared = submission.IdResult(found, "proof_found", "testnet", facts, named_elsewhere=True)
    judged = submission.own_dates_only(shared, window)
    assert judged.status == "dates_do_not_fit" and judged.use_not_counted
    own = submission.IdResult(found, "proof_found", "testnet", facts)  # nobody else names it
    assert submission.own_dates_only(own, window) == own
    made_then = submission.IdResult(found, "proof_found", "testnet",
                                    replace(facts, created_at=datetime(2026, 2, 19, tzinfo=UTC)),
                                    named_elsewhere=True)  # fmt: skip
    assert submission.own_dates_only(made_then, window) == made_then  # its own date proves


ADDRESS, CONTRACT = "0x8004a818bfb912233c491871b3d84c89a494bd9e", "0.0.7919997"


def names_the_contract(database: str, name: str, entity: str) -> None:
    """The project `name` names the invented contract on the test network as `entity`, and the
    ledger found it there as CONTRACT."""
    with psycopg.connect(database) as conn:
        (project,) = conn.execute("SELECT id FROM projects WHERE name = %s", (name,)).fetchone()
        (hedera_id,) = conn.execute(
            "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
            "words_around, in_hashscan_link) VALUES (%s, %s, 'testnet', 'contract', 'page', "
            "'invented', false) RETURNING id", (project, entity)).fetchone()  # fmt: skip
        conn.execute("INSERT INTO id_checks (hedera_id, network, status) "
                     "VALUES (%s, 'testnet', 'proof_found')", (hedera_id,))  # fmt: skip
    LedgerStore(database).save_facts(LedgerFacts(entity, "testnet", NOW, found=True,
                                                 kind="contract", ledger_id=CONTRACT))  # fmt: skip


def knows_the_contract(entity: str) -> dict[str, StandInMirror]:
    mirrors = nodes()
    mirrors["testnet"].things["contract"] = {
        entity: {"contract_id": CONTRACT, "created_timestamp": DURING, "evm_address": ADDRESS}
    }
    return mirrors


@pytest.mark.integration
@pytest.mark.parametrize(
    ("in_the_readme", "on_the_page"),
    [(ADDRESS, CONTRACT), (CONTRACT, ADDRESS)],
    ids=["readme-address", "page-address"],
)
def test_a_contract_named_in_its_other_form_is_seen_before(
    database: str, tmp_path: Path, in_the_readme: str, on_the_page: str
) -> None:
    """A README and a page that name one contract, one by its EVM address and one by its 0.0
    ID, name one thing of the ledger (28 October 2026: they were two IDs)."""
    names_the_contract(database, "Cedar Post", on_the_page)
    readme = (
        f"# Pebble Pay\n\nOur [contract](https://hashscan.io/testnet/contract/{in_the_readme}).\n"
    )
    result = run(
        database, tmp_path, found_code(tmp_path, readme)[0], knows_the_contract(in_the_readme)
    )
    with psycopg.connect(database) as conn:
        ids = dict(conn.execute("SELECT name, id FROM projects").fetchall())
    assert [(one.found.entity_id, one.network) for one in result.ids] == [
        (in_the_readme, "testnet")
    ]
    assert [(one.project_id, one.by) for one in result.seen] == [
        (ids["Pebble Pay"], "repository"), (ids["Cedar Post"], f"testnet:{CONTRACT}")]  # fmt: skip
    assert result.ids[0].named_elsewhere and not result.ids[0].shared


@pytest.mark.integration
def test_a_repository_that_github_does_not_have_is_said_and_no_readme_is_asked(
    database: str, tmp_path: Path
) -> None:
    gone = json.dumps({"message": "Not Found", "status": "404"}).encode()
    client, site = github(tmp_path, {facts_address(REPO): Reply(404, gone)})
    result = run(database, tmp_path, client)
    assert site.urls == [facts_address(REPO)]  # no README, no version and no code are asked
    assert result.problems == [submission.NO_SUCH_CODE] and result.hedera_code is None
    assert result.ids == [] and result.proof == "no_id_given" and result.life.status == "unknown"


@pytest.mark.integration
def test_an_id_that_no_node_answers_for_is_not_judged(database: str, tmp_path: Path) -> None:
    class Away(StandInMirror):
        def _one(self, kind: str, entity: str) -> dict | None:
            raise MirrorError("the node went away")

    result = run(database, tmp_path, found_code(tmp_path)[0],
                 {"testnet": Away("testnet"), "mainnet": Away("mainnet")})  # fmt: skip
    assert [one.status for one in result.ids] == [submission.NOT_ASKED]
    assert result.proof == submission.NOT_ASKED
    assert any("mirror node" in problem for problem in result.problems)


@pytest.mark.integration
def test_without_github_only_what_was_saved_is_read(database: str, tmp_path: Path) -> None:
    client, _ = found_code(tmp_path)
    run(database, tmp_path, client)  # saves the two answers
    result = run(database, tmp_path, None, problems=["GitHub may not be asked now."])
    assert (
        result.code is not None
        and result.ids
        and result.problems == ["GitHub may not be asked now."]
    )
    empty = submission.check_submission(
        database, OTHER, EVENT, client=None, store=RawStore(tmp_path / "raw"),
        collector=COLLECTOR, mirrors=nodes(), now=lambda: NOW,
    )  # fmt: skip
    assert empty.code is None and empty.ids == [] and empty.proof == "no_id_given"


@pytest.mark.integration
def test_without_a_hackathon_the_dates_are_shown_and_not_judged(
    database: str, tmp_path: Path
) -> None:
    result = run(database, tmp_path, found_code(tmp_path)[0], event=None)
    assert result.event is None
    assert [(one.status, one.facts.kind) for one in result.ids] == [("window_not_known", "topic")]
    assert result.ids[0].facts.created_at is not None  # the date is there, for a person to read
    assert result.life.status == "unknown"  # no end of a hackathon: life is not judged
    assert [one.by for one in result.seen] == ["repository"]  # the rest of the check is the same
