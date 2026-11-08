"""The repositories of the projects' code, the ids of their READMEs, and what their code says
about Hedera. All data is invented."""

from __future__ import annotations

import re

import psycopg
import pytest

from fakes import ARCHIVE_COMMIT, PROJECT_PAGE, project_page
from hackathon_memory.collect import github_code
from hackathon_memory.collect.github_code import CodeRead
from hackathon_memory.collect.github_readmes import BLOCKED, FOUND, NONE, Readme
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import IN_THE_README, ON_THE_PAGE, ProjectStore
from hackathon_memory.db.repositories import RepositoryStore
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.hedera_code import (
    IMPORT_NAME,
    MENTION_NAME,
    MIRROR_NODE,
    UNREADABLE,
    CodeScan,
    Seen,
)
from hackathon_memory.parse.hedera_ids import FoundId

pytestmark = pytest.mark.integration

PEBBLE = "https://github.com/sample-org/pebble-pay"
QUARTZ = "https://github.com/sample-org/quartz-notes"
SECOND_PAGE = "https://ethglobal.com/showcase/quartz-notes-q3w4e"
THIRD_PAGE = "https://ethglobal.com/showcase/reed-radio-r5t6y"
SHA = "c" * 64


@pytest.fixture
def database(empty_database: str) -> str:
    migrate(empty_database)
    return empty_database


def rows(database: str, query: str, *values: object) -> list[tuple]:
    with psycopg.connect(database) as conn:
        return conn.execute(query, values).fetchall()


def three_projects(database: str) -> dict[str, int]:
    """Pebble links its code, Quartz links the same code in another spelling, Reed has none."""
    store = ProjectStore(database)
    store.save(read_project_page(project_page(), PROJECT_PAGE), "a" * 64)
    quartz = project_page(
        name="Quartz Notes",
        slug="quartz-notes",
        short_id="q3w4e",
        code="https://GitHub.com/Sample-Org/Pebble-Pay.git",
    )
    store.save(read_project_page(quartz, SECOND_PAGE), "b" * 64)
    reed = project_page(name="Reed Radio", slug="reed-radio", short_id="r5t6y", code=None)
    store.save(read_project_page(reed, THIRD_PAGE), "d" * 64)
    return dict(rows(database, "SELECT page_url, id FROM projects"))


def readme(status: str = FOUND, **taken_out: int) -> Readme:
    return Readme(
        status=status,
        text="# Pebble\n" if status == FOUND else "",
        name="README.md" if status == FOUND else None,
        sha256=SHA,
        fetched_at="2026-10-11T18:00:00Z",
        taken_out=dict(taken_out),
    )


def an_id(entity: str = "0.0.3456781", network: str | None = "testnet") -> FoundId:
    return FoundId(entity, network, "topic", f"our topic {entity} on {network}", False)


# --------------------------------------------------------------------- repositories


def test_the_first_link_to_the_code_of_each_project_is_found(database: str) -> None:
    ids = three_projects(database)
    links = RepositoryStore(database).code_links()
    assert links == {
        ids[PROJECT_PAGE]: "https://github.com/sample-org/pebble-pay",
        ids[SECOND_PAGE]: "https://GitHub.com/Sample-Org/Pebble-Pay.git",
    }


def test_projects_that_name_one_repository_share_its_row(database: str) -> None:
    ids = three_projects(database)
    store = RepositoryStore(database)
    made = store.link({ids[PROJECT_PAGE]: PEBBLE, ids[SECOND_PAGE]: PEBBLE})
    assert list(made) == [PEBBLE]
    assert rows(database, "SELECT url, readme_status FROM repositories") == [(PEBBLE, None)]
    assert sorted(rows(database, "SELECT id, repository_id FROM projects")) == sorted(
        [
            (ids[PROJECT_PAGE], made[PEBBLE]),
            (ids[SECOND_PAGE], made[PEBBLE]),
            (ids[THIRD_PAGE], None),
        ]
    )
    assert store.link({ids[PROJECT_PAGE]: PEBBLE, ids[SECOND_PAGE]: PEBBLE}) == made  # again


def test_a_project_that_no_longer_names_a_repository_loses_it_and_its_readme_ids(
    database: str,
) -> None:
    ids = three_projects(database)
    store = RepositoryStore(database)
    store.link({ids[PROJECT_PAGE]: PEBBLE, ids[SECOND_PAGE]: QUARTZ})
    ProjectStore(database).save_readme_ids(ids[SECOND_PAGE], [an_id()])
    store.link({ids[PROJECT_PAGE]: PEBBLE})
    assert rows(database, "SELECT repository_id FROM projects WHERE id = %s", ids[SECOND_PAGE]) == [
        (None,)
    ]
    readme_ids = "SELECT count(*) FROM hedera_ids WHERE found_in = 'readme'"
    assert rows(database, readme_ids) == [(0,)]


def test_what_github_answered_about_a_readme_is_written(database: str) -> None:
    ids = three_projects(database)
    store = RepositoryStore(database)
    store.link({ids[PROJECT_PAGE]: PEBBLE, ids[SECOND_PAGE]: QUARTZ})
    store.save_readme(PEBBLE, readme(words_hidden=2, team_lines_cut=5, ids_in_the_cut=1))
    store.save_readme(QUARTZ, readme(NONE))
    assert rows(
        database,
        "SELECT url, readme_status, readme_name, readme_sha256, people_words_hidden, "
        "team_lines_cut, ids_in_the_cut FROM repositories ORDER BY url",
    ) == [
        (PEBBLE, FOUND, "README.md", SHA, 2, 5, 1),
        (QUARTZ, NONE, None, SHA, 0, 0, 0),
    ]
    assert store.counts() == {
        "repositories": 2,
        "projects_with_a_repository": 2,
        "readme_found": 1,
        "readme_none": 1,
    }


@pytest.mark.parametrize(
    "change",
    [
        "INSERT INTO repositories (url) VALUES ('https://github.com/Sample-Org/pebble')",
        "INSERT INTO repositories (url) VALUES ('https://gitlab.com/sample-org/pebble')",
        "INSERT INTO repositories (url) VALUES ('https://github.com/sample-org')",
        "INSERT INTO repositories (url, readme_status) VALUES ('https://github.com/a/b', 'found')",
        "INSERT INTO repositories (url, readme_status, readme_fetched_at, readme_sha256) "
        "VALUES ('https://github.com/a/b', 'lost', now(), repeat('c', 64))",
        "INSERT INTO repositories (url, team_lines_cut) VALUES ('https://github.com/a/b', -1)",
        "INSERT INTO repositories (url, archive_status) VALUES ('https://github.com/a/b', 'read')",
        "INSERT INTO repositories (url, archive_status, archive_read_at) "
        "VALUES ('https://github.com/a/b', 'partial', now())",
        "INSERT INTO repositories (url, archive_status, archive_read_at, archive_partial) "
        "VALUES ('https://github.com/a/b', 'read', now(), 'cut')",
        "INSERT INTO repositories (url, archive_commit) VALUES ('https://github.com/a/b', 'main')",
        "INSERT INTO hedera_in_code VALUES (1, 'guess', 'x', 1, ARRAY['a.ts'])",
        "INSERT INTO hedera_in_code VALUES (1, 'package', 'x', 0, ARRAY['a.ts'])",
        "INSERT INTO hedera_in_code VALUES (1, 'package', 'x', 1, ARRAY[]::text[])",
    ],
)
def test_the_table_refuses_a_value_that_makes_no_sense(database: str, change: str) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), psycopg.connect(database) as conn:
        conn.execute(change)


def test_a_blocked_readme_is_written_with_no_name(database: str) -> None:
    ids = three_projects(database)
    store = RepositoryStore(database)
    store.link({ids[PROJECT_PAGE]: PEBBLE})
    store.save_readme(PEBBLE, readme(BLOCKED))
    assert rows(database, "SELECT readme_status, readme_name FROM repositories") == [
        (BLOCKED, None)
    ]


# --------------------------------------------------------------------- the ids of a README


def test_the_ids_of_a_readme_are_kept_next_to_those_of_the_page(database: str) -> None:
    ids = three_projects(database)
    projects = ProjectStore(database)
    pebble = ids[PROJECT_PAGE]
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET proof_status = 'no_id_given' WHERE id = %s", (pebble,))
    assert projects.save_readme_ids(pebble, [an_id(), an_id("0.0.4567891", None)]) is True
    assert rows(
        database,
        "SELECT entity_id, network, said_kind, found_in FROM hedera_ids "
        "WHERE project_id = %s ORDER BY id",
        pebble,
    ) == [
        ("0.0.3456781", "testnet", "topic", IN_THE_README),
        ("0.0.4567891", None, "topic", IN_THE_README),
    ]
    assert rows(database, "SELECT proof_status FROM projects WHERE id = %s", pebble) == [(None,)]


def test_the_same_ids_again_change_nothing(database: str) -> None:
    ids = three_projects(database)
    projects = ProjectStore(database)
    pebble = ids[PROJECT_PAGE]
    projects.save_readme_ids(pebble, [an_id()])
    before = rows(database, "SELECT id FROM hedera_ids")
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE projects SET proof_status = 'proof_found' WHERE id = %s", (pebble,))
    assert projects.save_readme_ids(pebble, [an_id()]) is False
    assert rows(database, "SELECT id FROM hedera_ids") == before
    assert rows(database, "SELECT proof_status FROM projects WHERE id = %s", pebble) == [
        ("proof_found",)
    ]


def test_new_ids_replace_the_old_ones_and_the_ids_of_the_page_stay(database: str) -> None:
    ids = three_projects(database)
    projects = ProjectStore(database)
    page = read_project_page(
        project_page(made="<p>The topic 0.0.2345671 on testnet.</p>"), PROJECT_PAGE
    )
    projects.save(page, "e" * 64)
    pebble = ids[PROJECT_PAGE]
    projects.save_readme_ids(pebble, [an_id()])
    assert projects.save_readme_ids(pebble, [an_id("0.0.5678902")]) is True
    assert projects.save_readme_ids(pebble, []) is True
    assert rows(
        database, "SELECT entity_id, found_in FROM hedera_ids WHERE project_id = %s", pebble
    ) == [("0.0.2345671", ON_THE_PAGE)]


def test_the_table_of_repositories_has_no_column_for_a_person(database: str) -> None:
    # Design rule 11. The account that holds a repository is named in its link only, in "url".
    columns = rows(
        database,
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'repositories'",
    )
    person = re.compile(r"member|author|email|team|person|user|owner|avatar|photo|handle|profile")
    # A count of what was taken out names nobody: it is a number.
    about_people = {name: kind for name, kind in columns if person.search(name)}
    assert about_people == {"team_lines_cut": "integer"}
    assert len(columns) == 22
    found = rows(
        database,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'hedera_in_code'",
    )
    assert sorted(name for (name,) in found) == [
        "examples", "files", "kind", "name", "repository_id"]  # fmt: skip


# --------------------------------------------------------------------- what the code says


def code_read(status: str = github_code.READ, **changes: object) -> CodeRead:
    """An INVENTED reading of the archive of a repository."""
    scan = CodeScan(
        files=40, commit=ARCHIVE_COMMIT,
        packages={"@hashgraph/sdk": ["package.json", "web/package.json"]},
        features={"Consensus Service (topics)": Seen(3, ["src/topic.ts", "src/a.ts", "src/b.ts"])},
        signs={MIRROR_NODE: Seen(1, ["src/mirror.ts"])},
        imports=Seen(4, ["src/topic.ts", "src/a.ts", "src/b.ts", "src/c.ts"]),
        mentions=Seen(6, ["package.json", "src/topic.ts", "src/a.ts", "src/b.ts", "src/c.ts",
                          "src/mirror.ts"]),
    )  # fmt: skip
    for name, value in changes.items():
        setattr(scan, name, value)
    whole = status in (github_code.READ, github_code.PARTIAL)
    return CodeRead(status, scan if whole else None, "2026-10-21T20:00:00Z")


def test_what_the_code_says_about_hedera_is_written_and_replaced(database: str) -> None:
    ids = three_projects(database)
    store = RepositoryStore(database)
    store.link({ids[PROJECT_PAGE]: PEBBLE, ids[SECOND_PAGE]: QUARTZ})
    # Two services in a file that nothing uses: the one that a used file also calls is a call.
    unused = {"Token Service": Seen(1, ["src/old.ts"]),
              "Consensus Service (topics)": Seen(1, ["src/old.ts"])}  # fmt: skip
    store.save_code(PEBBLE, code_read(unused=unused))
    store.save_code(QUARTZ, code_read(github_code.GONE))
    store.save_code("https://github.com/sample-org/linked-by-nobody", code_read())
    assert rows(
        database,
        "SELECT url, archive_status, archive_commit, archive_files, archive_partial "
        "FROM repositories ORDER BY url",
    ) == [
        (PEBBLE, "read", ARCHIVE_COMMIT, 40, None),
        (QUARTZ, "gone", None, None, None),
    ]
    assert rows(
        database, "SELECT kind, name, files, examples FROM hedera_in_code ORDER BY kind, name"
    ) == [
        ("feature", "Consensus Service (topics)", 3, ["src/topic.ts", "src/a.ts", "src/b.ts"]),
        ("import", IMPORT_NAME, 4, ["src/topic.ts", "src/a.ts", "src/b.ts", "src/c.ts"]),
        (
            "mention",
            MENTION_NAME,
            6,
            ["package.json", "src/topic.ts", "src/a.ts", "src/b.ts", "src/c.ts", "src/mirror.ts"],
        ),
        ("package", "@hashgraph/sdk", 2, ["package.json", "web/package.json"]),
        ("sign", MIRROR_NODE, 1, ["src/mirror.ts"]),
        ("unused", "Token Service", 1, ["src/old.ts"]),  # migration 0034
    ]

    # A newer reading of the same repository replaces what the older one found.
    newer = code_read(github_code.PARTIAL, partial=UNREADABLE, features={}, signs={},
                      imports=Seen(), mentions=Seen())  # fmt: skip
    store.save_code(PEBBLE, newer)
    assert rows(database, "SELECT kind, name FROM hedera_in_code") == [
        ("package", "@hashgraph/sdk")]  # fmt: skip
    assert rows(
        database, "SELECT archive_status, archive_partial FROM repositories WHERE url = %s", PEBBLE
    ) == [("partial", UNREADABLE)]
