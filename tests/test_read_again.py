"""How often "Read again now" may be pressed (db/read_again.py, migration 0031)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg

from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.read_again import EVERY, ReadAgainStore, free_from, of_project

NOW = datetime(2026, 11, 6, 1, 0, tzinfo=UTC)
REPOSITORY = "https://github.com/sample-org/pebble-pay"


def test_one_press_every_15_minutes_for_each_thing(empty_database: str) -> None:
    migrate(empty_database)
    store = ReadAgainStore(empty_database)
    assert EVERY == timedelta(minutes=15)  # 3 hours until 8 November 2026
    assert store.free_from(REPOSITORY, NOW) is None
    assert store.take(REPOSITORY, NOW) is True
    assert store.free_from(REPOSITORY, NOW) == NOW + EVERY
    just_before = NOW + EVERY - timedelta(seconds=1)
    assert store.take(REPOSITORY, just_before) is False  # refused: the next stays NOW + EVERY
    assert store.free_from(REPOSITORY, just_before) == NOW + EVERY
    assert store.take(of_project(7), just_before) is True  # another thing has its own count
    assert store.free_from(REPOSITORY, NOW + EVERY) is None
    assert store.take(REPOSITORY, NOW + EVERY) is True
    assert store.free_from(REPOSITORY, NOW + EVERY) == NOW + 2 * EVERY


def test_a_press_is_given_back_only_up_to_its_moment(empty_database: str) -> None:
    migrate(empty_database)
    store = ReadAgainStore(empty_database)
    assert store.take(REPOSITORY, NOW) is True
    store.give_back(REPOSITORY, NOW - timedelta(seconds=1))  # a press made after the failure stays
    assert store.free_from(REPOSITORY, NOW) == NOW + EVERY
    store.give_back(REPOSITORY, NOW + timedelta(seconds=1))
    assert store.free_from(REPOSITORY, NOW) is None
    store.give_back(REPOSITORY, NOW)  # nothing left to give back: no error
    assert store.take(REPOSITORY, NOW) is True


def test_the_time_is_given_in_utc_on_an_open_connection(empty_database: str) -> None:
    migrate(empty_database)
    assert ReadAgainStore(empty_database).take(REPOSITORY, NOW) is True
    with psycopg.connect(empty_database) as conn:
        conn.execute("SET TIME ZONE 'Africa/Tunis'")
        free = free_from(conn, REPOSITORY, NOW)
    assert free == NOW + EVERY and free.utcoffset() == timedelta(0)
