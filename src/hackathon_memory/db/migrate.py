"""Numbered SQL migrations.

Design section 11.6 asks for "a numbered script" for every change to the tables.
The rules, and the need behind each one:

* A migration is a file named NNNN_name.sql in the folder `migrations/`. The numbers start at
  1 and have no gap. Two people who both add number 5 get an error at once, not a surprise later.
* Each file runs once, in one transaction. A file that fails leaves nothing behind.
* The checksum of every applied file is stored. If someone edits an applied file, the run stops:
  the database and the folder would no longer tell the same story. A change is a new file.
* A run takes a lock, so two runs at the same time cannot apply the same file twice.
* Running again when everything is applied does nothing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable

import psycopg

_FILE_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")

# Any fixed number will do. It names the lock that keeps two migration runs apart.
_LOCK_KEY = 6_283_742_001

_BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    integer     PRIMARY KEY CHECK (version > 0),
    name       text        NOT NULL,
    checksum   text        NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


class MigrationError(Exception):
    """The folder of migrations and the database do not agree, or a file is wrong."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    checksum: str


@dataclass(frozen=True)
class MigrationState:
    migration: Migration
    applied: bool


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_migrations(directory: Traversable | None = None) -> list[Migration]:
    """Read the migration files, check their names and numbers, and return them in order."""
    if directory is None:
        directory = files("hackathon_memory.db") / "migrations"

    found: list[Migration] = []
    for entry in directory.iterdir():
        if not entry.name.endswith(".sql"):
            continue
        match = _FILE_NAME.match(entry.name)
        if match is None:
            raise MigrationError(
                f"{entry.name}: a migration file must be named NNNN_name.sql "
                "(four digits, then lower-case words joined by underscores)"
            )
        # Line endings are made the same first, so a Windows copy and a Linux copy of the
        # same file give the same checksum.
        text = entry.read_bytes().decode("utf-8").replace("\r\n", "\n")
        found.append(Migration(int(match[1]), match[2], text, _checksum(text)))

    found.sort(key=lambda m: m.version)
    for position, migration in enumerate(found, start=1):
        if migration.version != position:
            raise MigrationError(
                f"migration numbers must start at 1 and have no gap or repeat: "
                f"expected {position:04d}, found {migration.version:04d}_{migration.name}.sql"
            )
    return found


def _applied(conn: psycopg.Connection) -> dict[int, tuple[str, str]]:
    rows = conn.execute("SELECT version, name, checksum FROM schema_migrations").fetchall()
    return {version: (name, checksum) for version, name, checksum in rows}


def _check_agreement(applied: dict[int, tuple[str, str]], migrations: list[Migration]) -> None:
    by_version = {m.version: m for m in migrations}
    for version, (name, checksum) in sorted(applied.items()):
        migration = by_version.get(version)
        if migration is None:
            raise MigrationError(
                f"migration {version:04d}_{name} is applied in the database but its file is "
                "missing from the folder"
            )
        if migration.checksum != checksum:
            raise MigrationError(
                f"migration {version:04d}_{name} was changed after it was applied. "
                "Do not edit an applied file: add a new migration instead."
            )


def status(conninfo: str, migrations: list[Migration] | None = None) -> list[MigrationState]:
    """For each migration, whether it is applied. Stops with an error if the two disagree."""
    migrations = load_migrations() if migrations is None else migrations
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(_BOOTSTRAP_SQL)
        applied = _applied(conn)
    _check_agreement(applied, migrations)
    return [MigrationState(m, m.version in applied) for m in migrations]


def migrate(conninfo: str, migrations: list[Migration] | None = None) -> list[Migration]:
    """Apply the migrations that are not applied yet. Returns the ones applied by this call."""
    migrations = load_migrations() if migrations is None else migrations
    applied_now: list[Migration] = []
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
        try:
            conn.execute(_BOOTSTRAP_SQL)
            applied = _applied(conn)
            _check_agreement(applied, migrations)
            for migration in migrations:
                if migration.version in applied:
                    continue
                with conn.transaction():
                    conn.execute(migration.sql.encode("utf-8"))
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, checksum) "
                        "VALUES (%s, %s, %s)",
                        (migration.version, migration.name, migration.checksum),
                    )
                applied_now.append(migration)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
    return applied_now
