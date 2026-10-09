"""The migration runner: numbered files, applied once, safe to run again."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest

from hackathon_memory.db.migrate import (
    MigrationError,
    load_migrations,
    migrate,
    status,
)


def write(folder: Path, name: str, sql: str, newline: str = "\n") -> None:
    (folder / name).write_bytes(sql.replace("\n", newline).encode("utf-8"))


# ---------------------------------------------------------------- reading the folder (no database)


def test_the_real_migrations_load_in_order() -> None:
    migrations = load_migrations()
    assert [m.version for m in migrations] == list(range(1, len(migrations) + 1))
    assert migrations[0].name == "vector_extension"
    assert all(re.fullmatch(r"[0-9a-f]{64}", m.checksum) for m in migrations)


def test_line_endings_do_not_change_the_checksum(tmp_path: Path) -> None:
    unix, windows = tmp_path / "unix", tmp_path / "windows"
    unix.mkdir()
    windows.mkdir()
    write(unix, "0001_a.sql", "SELECT 1;\nSELECT 2;\n")
    write(windows, "0001_a.sql", "SELECT 1;\nSELECT 2;\n", newline="\r\n")
    assert load_migrations(unix)[0].checksum == load_migrations(windows)[0].checksum


def test_a_gap_in_the_numbers_is_an_error(tmp_path: Path) -> None:
    write(tmp_path, "0001_a.sql", "SELECT 1;")
    write(tmp_path, "0003_c.sql", "SELECT 3;")
    with pytest.raises(MigrationError, match="expected 0002"):
        load_migrations(tmp_path)


def test_a_repeated_number_is_an_error(tmp_path: Path) -> None:
    write(tmp_path, "0001_a.sql", "SELECT 1;")
    write(tmp_path, "0001_b.sql", "SELECT 2;")
    with pytest.raises(MigrationError, match="expected 0002"):
        load_migrations(tmp_path)


def test_a_badly_named_sql_file_is_an_error(tmp_path: Path) -> None:
    write(tmp_path, "add_table.sql", "SELECT 1;")
    with pytest.raises(MigrationError, match="must be named"):
        load_migrations(tmp_path)


def test_files_that_are_not_sql_are_ignored(tmp_path: Path) -> None:
    write(tmp_path, "0001_a.sql", "SELECT 1;")
    (tmp_path / "notes.md").write_text("not a migration", encoding="utf-8")
    assert len(load_migrations(tmp_path)) == 1


# ---------------------------------------------------------------- against the real database


@pytest.mark.integration
def test_migrate_turns_on_pgvector_and_is_safe_to_run_again(empty_database: str) -> None:
    first = migrate(empty_database)
    assert [m.name for m in first] == [m.name for m in load_migrations()]
    assert migrate(empty_database) == []  # the second run does nothing

    with psycopg.connect(empty_database) as conn:
        extension = conn.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        assert extension.fetchone() == ("vector",)
        assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone() == (len(first),)
    assert all(state.applied for state in status(empty_database))


@pytest.mark.integration
def test_an_edited_migration_stops_the_run(empty_database: str, tmp_path: Path) -> None:
    write(tmp_path, "0001_a.sql", "CREATE TABLE t1 (id integer);")
    migrate(empty_database, load_migrations(tmp_path))

    write(tmp_path, "0001_a.sql", "CREATE TABLE t1 (id bigint);")  # the applied file is edited
    write(tmp_path, "0002_b.sql", "CREATE TABLE t2 (id integer);")
    with pytest.raises(MigrationError, match="changed after it was applied"):
        migrate(empty_database, load_migrations(tmp_path))

    with psycopg.connect(empty_database) as conn:  # nothing new was applied
        assert conn.execute("SELECT to_regclass('t2')").fetchone() == (None,)


@pytest.mark.integration
def test_a_failed_migration_leaves_nothing_behind(empty_database: str, tmp_path: Path) -> None:
    write(tmp_path, "0001_ok.sql", "CREATE TABLE t1 (id integer);")
    write(tmp_path, "0002_bad.sql", "CREATE TABLE t2 (id integer);\nSELECT 1/0;")
    with pytest.raises(psycopg.errors.DivisionByZero):
        migrate(empty_database, load_migrations(tmp_path))

    with psycopg.connect(empty_database) as conn:
        assert conn.execute("SELECT to_regclass('t1')").fetchone() == ("t1",)  # the good one stays
        assert conn.execute("SELECT to_regclass('t2')").fetchone() == (None,)  # rolled back
        versions = conn.execute("SELECT version FROM schema_migrations").fetchall()
        assert versions == [(1,)]  # only the good one is recorded


@pytest.mark.integration
def test_a_missing_file_for_an_applied_migration_stops_the_run(
    empty_database: str, tmp_path: Path
) -> None:
    write(tmp_path, "0001_a.sql", "CREATE TABLE t1 (id integer);")
    migrate(empty_database, load_migrations(tmp_path))
    (tmp_path / "0001_a.sql").unlink()
    with pytest.raises(MigrationError, match="file is missing"):
        migrate(empty_database, load_migrations(tmp_path))


@pytest.mark.integration
def test_two_runs_at_the_same_time_apply_each_file_once(
    empty_database: str, tmp_path: Path
) -> None:
    # The first file is slow on purpose, so the two runs overlap in time.
    write(tmp_path, "0001_slow.sql", "SELECT pg_sleep(0.6);\nCREATE TABLE t1 (id integer);")
    write(tmp_path, "0002_fast.sql", "CREATE TABLE t2 (id integer);")
    migrations = load_migrations(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = [pool.submit(migrate, empty_database, migrations) for _ in range(2)]
        applied = [len(run.result()) for run in runs]

    assert sorted(applied) == [0, 2]  # one run did the work, the other found nothing to do
