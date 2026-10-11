"""The step that checks the ids on the ledger, on a real PostgreSQL and a stand-in mirror node.

Every page, id and date is invented.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from fakes import PROJECT_PAGE, StandInMirror, project_page
from hackathon_memory.db.ledger import LedgerStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import Run, last_runs, recorded_run
from hackathon_memory.hedera.mirror import MirrorError
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.pipeline.__main__ import main
from hackathon_memory.pipeline.check_ids import (
    MAX_ERRORS_IN_A_ROW,
    STEP,
    NodeIsAway,
    check_ids,
)
from hackathon_memory.settings import Settings

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)
# The event starts on 6 March 2026 (the invented page says so). Its end is typed in: 8 March.
DURING = "1772884800.000000001"  # 7 March 2026
LONG_BEFORE = "1736899200.000000001"  # 15 January 2025
LONG_AFTER = "1785542400.000000001"  # 1 August 2026
SECOND_PAGE = "https://ethglobal.com/showcase/quartz-notes-q3w4e"
THIRD_PAGE = "https://ethglobal.com/showcase/cedar-lens-k9l8m"


@pytest.fixture
def database(empty_database: str) -> str:
    """Three projects. The first names a topic with no network and a token on the test
    network. The second names nothing. The third links to an account on HashScan."""
    migrate(empty_database)
    projects = ProjectStore(empty_database)
    first = project_page(
        description="<p>The log is the topic 0.0.3456789.</p>",
        made="<p>The coin is the token 0.0.2345678 on the test network.</p>",
    )
    projects.save(read_project_page(first, PROJECT_PAGE), "a" * 64)
    second = project_page(name="Quartz Notes", slug="quartz-notes", short_id="q3w4e")
    projects.save(read_project_page(second, SECOND_PAGE), "b" * 64)
    third = project_page(
        name="Cedar Lens",
        slug="cedar-lens",
        short_id="k9l8m",
        made='<p><a href="https://hashscan.io/testnet/account/0.0.5678901">Our account</a></p>',
    )
    projects.save(read_project_page(third, THIRD_PAGE), "c" * 64)
    with psycopg.connect(empty_database) as conn:
        conn.execute("UPDATE events SET ends_on = '2026-03-08'")
    return empty_database


def nodes() -> dict[str, StandInMirror]:
    """The test network holds what the pages name. On the main network the number of the topic
    is an old account, as it happens with real numbers."""
    test = StandInMirror(
        "testnet",
        topic={"0.0.3456789": {"topic_id": "0.0.3456789", "created_timestamp": DURING}},
        token={
            "0.0.2345678": {
                "token_id": "0.0.2345678",
                "total_supply": "1000",
                "created_timestamp": DURING,
                "modified_timestamp": DURING,
            }
        },
        account={"0.0.5678901": {"account": "0.0.5678901", "created_timestamp": LONG_BEFORE}},
    )
    test.lists[("messages", "0.0.3456789")] = [
        {"sequence_number": 1, "consensus_timestamp": DURING},
        {"sequence_number": 49, "consensus_timestamp": DURING},
    ]
    test.lists[("transactions", "0.0.5678901")] = [
        {"consensus_timestamp": LONG_BEFORE},
        {"consensus_timestamp": DURING},
        {"consensus_timestamp": LONG_AFTER},
    ]
    main_network = StandInMirror(
        "mainnet",
        account={"0.0.3456789": {"account": "0.0.3456789", "created_timestamp": LONG_BEFORE}},
    )
    return {"testnet": test, "mainnet": main_network}


def run_step(database: str, mirrors: dict, at: datetime = NOW, **options: object) -> Run:
    with recorded_run(database, STEP) as run:
        check_ids(LedgerStore(database), mirrors, run, now=lambda: at, **options)  # type: ignore[arg-type]
    return run


def results(database: str) -> list[tuple]:
    with psycopg.connect(database) as conn:
        return conn.execute(
            "SELECT p.site_key, h.entity_id, c.network, c.status FROM id_checks c "
            "JOIN hedera_ids h ON h.id = c.hedera_id JOIN projects p ON p.id = h.project_id "
            "ORDER BY 1, 2, 3"
        ).fetchall()


def project_statuses(database: str) -> dict[str, str | None]:
    with psycopg.connect(database) as conn:
        return dict(conn.execute("SELECT site_key, proof_status FROM projects").fetchall())


# --------------------------------------------------------------------- the step


def test_each_id_is_judged_on_the_network_of_its_page_or_on_both(database: str) -> None:
    mirrors = nodes()
    run = run_step(database, mirrors)
    assert results(database) == [
        # The account was made long before, and used before, inside and after the window.
        ("cedar-lens-k9l8m", "0.0.5678901", "testnet", "proof_found"),
        ("pebble-pay-x1y2z", "0.0.2345678", "testnet", "proof_found"),
        # The page names no network for the topic, so both are asked. The same number is an
        # old account on the main network.
        ("pebble-pay-x1y2z", "0.0.3456789", "mainnet", "another_kind"),
        ("pebble-pay-x1y2z", "0.0.3456789", "testnet", "proof_found"),
    ]
    assert project_statuses(database) == {
        "pebble-pay-x1y2z": "proof_found",
        "quartz-notes-q3w4e": "no_id_given",
        "cedar-lens-k9l8m": "proof_found",
    }
    counts = dict(run.counts)
    assert counts["answers_from_the_node"] == 4
    assert counts["id_proof_found"] == 3 and counts["id_another_kind"] == 1
    assert counts["project_proof_found"] == 2 and counts["projects_with_no_id"] == 1
    assert counts["looks_inside_a_window"] == 1  # the account
    assert counts["requests"] == sum(mirror.requests_made for mirror in mirrors.values()) > 0
    # The token names the test network, so the main network was never asked about it.
    assert all("0.0.2345678" not in asked for asked in mirrors["mainnet"].asked)


def test_a_second_run_asks_the_node_nothing(database: str) -> None:
    run_step(database, nodes())
    fresh = nodes()
    again = run_step(database, fresh, at=NOW + timedelta(days=3))
    assert fresh["testnet"].asked == [] and fresh["mainnet"].asked == []
    assert again.counts["answers_from_the_table"] == 4
    assert again.counts["answers_from_the_node"] == 0
    assert again.counts["looks_inside_a_window"] == 0
    assert len(results(database)) == 4  # and the results are all there again


def test_an_answer_older_than_a_week_is_asked_again(database: str) -> None:
    run_step(database, nodes())
    later = run_step(database, nodes(), at=NOW + timedelta(days=8))
    assert later.counts["answers_from_the_node"] == 4
    with psycopg.connect(database) as conn:
        (asked_at,) = conn.execute("SELECT DISTINCT asked_at FROM ledger_facts").fetchone()
    assert asked_at == NOW + timedelta(days=8)


def test_without_the_end_of_the_event_the_dates_wait_and_nothing_is_asked_twice(
    database: str,
) -> None:
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE events SET ends_on = NULL")
    run_step(database, nodes())
    assert project_statuses(database)["pebble-pay-x1y2z"] == "window_not_known"
    assert ("pebble-pay-x1y2z", "0.0.3456789", "mainnet", "another_kind") in results(database)

    with psycopg.connect(database) as conn:
        conn.execute("UPDATE events SET ends_on = '2026-03-08'")  # the end is typed in
    fresh = nodes()
    run_step(database, fresh, at=NOW + timedelta(hours=1))
    assert project_statuses(database)["pebble-pay-x1y2z"] == "proof_found"
    # The facts were in the table. Only the look inside the window of the account is new.
    asked = fresh["testnet"].asked
    assert [what for what, *_ in asked] == ["transactions"]
    assert fresh["mainnet"].asked == []


def test_an_old_account_that_was_not_used_at_the_event_is_not_proof(database: str) -> None:
    mirrors = nodes()
    mirrors["testnet"].lists[("transactions", "0.0.5678901")] = [
        {"consensus_timestamp": LONG_BEFORE},
        {"consensus_timestamp": LONG_AFTER},
    ]
    run_step(database, mirrors)
    assert project_statuses(database)["cedar-lens-k9l8m"] == "dates_do_not_fit"


def test_an_id_that_is_nothing_on_any_network_is_not_found(database: str) -> None:
    mirrors = nodes()
    del mirrors["testnet"].things["topic"]["0.0.3456789"]
    del mirrors["mainnet"].things["account"]["0.0.3456789"]
    run_step(database, mirrors)
    assert ("pebble-pay-x1y2z", "0.0.3456789", "testnet", "not_found") in results(database)
    assert project_statuses(database)["pebble-pay-x1y2z"] == "proof_found"  # the token still is
    again = run_step(database, nodes(), at=NOW + timedelta(days=1))
    assert again.counts["answers_from_the_node"] == 0  # "not found" was kept as an answer


# --------------------------------------------------------------------- when the node fails


class FailsOn(StandInMirror):
    """A node that fails for some ids."""

    def __init__(self, *bad: str, **things: dict) -> None:
        super().__init__("testnet", **things)
        self.bad = bad

    def _one(self, kind: str, entity: str) -> dict | None:
        if entity in self.bad or "*" in self.bad:
            self.asked.append((kind, entity))
            raise MirrorError(f"mirror node answered 503 for /{kind}s/{entity}")
        return super()._one(kind, entity)


def test_an_error_of_the_node_is_named_and_the_other_projects_are_checked(database: str) -> None:
    good = nodes()
    failing = FailsOn("0.0.2345678", **good["testnet"].things)
    failing.lists = good["testnet"].lists
    run = run_step(database, {"testnet": failing, "mainnet": good["mainnet"]})
    assert run.problems == [
        {
            "what": "0.0.2345678 on testnet",
            "rule": "mirror node answered 503 for /tokens/0.0.2345678",
        }
    ]
    assert run.counts["projects_not_finished"] == 1
    statuses = project_statuses(database)
    assert statuses["pebble-pay-x1y2z"] is None  # not judged on half of its ids
    assert statuses["cedar-lens-k9l8m"] == "proof_found"
    assert statuses["quartz-notes-q3w4e"] == "no_id_given"


def more_projects(database: str, count: int) -> None:
    """Add `count` projects, each naming one topic on the test network."""
    projects = ProjectStore(database)
    for number in range(count):
        page = f"https://ethglobal.com/showcase/dune-{number}-d{number}d{number}d"
        html = project_page(
            name=f"Dune {number}",
            slug=f"dune-{number}",
            short_id=f"d{number}d{number}d",
            made=f"<p>The topic 0.0.777770{number} on testnet.</p>",
        )
        projects.save(read_project_page(html, page), f"{number}" * 64)


def away() -> dict[str, FailsOn]:
    return {"testnet": FailsOn("*"), "mainnet": FailsOn("*")}  # both nodes fail every time


def test_several_errors_in_a_row_stop_the_step(database: str) -> None:
    more_projects(database, MAX_ERRORS_IN_A_ROW)
    nodes_away = away()
    with pytest.raises(NodeIsAway, match=f"{MAX_ERRORS_IN_A_ROW} times in a row"):
        run_step(database, nodes_away)
    asked = sum(len(node.asked) for node in nodes_away.values())
    assert asked == MAX_ERRORS_IN_A_ROW  # nothing more was asked, of nine questions
    (row,) = last_runs(database, STEP)
    assert row["ok"] is False
    assert row["problems"][-1] == {"what": "the step itself", "rule": "NodeIsAway"}


# --------------------------------------------------------------------- the command


def settings_for(database: str) -> Settings:
    return Settings(_env_file=None, database_url=database)


def test_the_command_checks_and_says_what_the_rule_found(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check"], settings_for(database), nodes()) == 0  # type: ignore[arg-type]
    said = capsys.readouterr().out
    assert "Answers of the mirror node: 4 new, 0 from the table." in said
    assert "Ids, on each network that was asked:" in said
    assert "      3  proof found" in said
    assert "      1  found, but as another kind of thing than the page says" in said
    assert "Projects:" in said
    assert "      2  proof found" in said
    assert "      1  no id given" in said
    (row,) = last_runs(database, STEP)
    assert row["ok"] is True
    assert f"This is run {row['id']} in the table of runs." in said


def test_the_command_can_ask_about_every_id_again(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["check"], settings_for(database), nodes())  # type: ignore[arg-type]
    capsys.readouterr()
    main(["check"], settings_for(database), nodes())  # type: ignore[arg-type]
    assert "Answers of the mirror node: 0 new, 4 from the table." in capsys.readouterr().out
    main(["check", "--max-age-days", "0"], settings_for(database), nodes())  # type: ignore[arg-type]
    assert "Answers of the mirror node: 4 new, 0 from the table." in capsys.readouterr().out


def test_the_command_names_each_id_it_could_not_check_and_ends_with_an_error(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # Four questions fail, one fewer than the number that stops the step.
    assert main(["check"], settings_for(database), away()) == 1  # type: ignore[arg-type]
    said = capsys.readouterr().out
    assert "Not checked, with what went wrong:" in said
    assert "  0.0.3456789 on testnet: mirror node answered 503 for /topics/0.0.3456789" in said
    assert "  0.0.3456789 on mainnet: mirror node answered 503 for /topics/0.0.3456789" in said
    assert "  0.0.2345678 on testnet: mirror node answered 503 for /tokens/0.0.2345678" in said
    assert "  0.0.5678901 on testnet: mirror node answered 503 for /contracts/0.0.5678901" in said
    assert "      2  not finished: see below" in said
    assert "      1  no id given" in said
    (row,) = last_runs(database, STEP)
    assert row["ok"] is True  # the step ran to its end, and said what it could not do


def test_the_command_stops_when_the_node_is_away(
    database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    more_projects(database, MAX_ERRORS_IN_A_ROW)
    assert main(["check"], settings_for(database), away()) == 1  # type: ignore[arg-type]
    said = capsys.readouterr().out
    assert said.strip() == (
        f"Stopped: the mirror node failed {MAX_ERRORS_IN_A_ROW} times in a row. "
        "Nothing more was asked. Try again later."
    )
    (row,) = last_runs(database, STEP)
    assert row["ok"] is False


@pytest.mark.parametrize(
    "argv",
    [
        ["check", "--limit", "5"],
        ["parse", "--max-age-days", "1"],
        ["check", "--max-age-days", "-1"],
    ],
)
def test_the_command_refuses_an_option_of_the_other_step(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 2
    assert "usage: python -m hackathon_memory.pipeline parse" in capsys.readouterr().out
