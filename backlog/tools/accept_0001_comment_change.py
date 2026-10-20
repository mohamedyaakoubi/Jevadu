"""One time, on this laptop only: tell the local database that migration 0001 is the file of today.

What happened. The database applied 0001 on 9 October 2026 and wrote down its checksum. On 10
October one comment line of the file was changed (the word for the design document), in the same
work that took every sign of the working notes out of the public files. The line that does
something, CREATE EXTENSION, did not change. The migration tool is right to refuse such a file:
"do not edit an applied file". This script accepts the change for this one file, after it has
checked again that the lines which are not comments still say what the database ran.

    .venv/Scripts/python.exe backlog/tools/accept_0001_comment_change.py

It prints no connection text. Run it once. A second run does nothing.
"""

from __future__ import annotations

import psycopg

from hackathon_memory.db.migrate import load_migrations
from hackathon_memory.settings import Settings

FIRST_CHECKSUM_STARTS = None  # the old checksum is read from the database, not typed here
EXPECTED_SQL = ["CREATE EXTENSION IF NOT EXISTS vector;"]

migration = next(m for m in load_migrations() if m.version == 1)
sql_lines = [
    line for line in migration.sql.splitlines() if line.strip() and not line.startswith("--")
]
if sql_lines != EXPECTED_SQL:
    raise SystemExit("Stopped: the file does more than the database ran. Nothing was changed.")

with psycopg.connect(Settings().database_conninfo()) as conn:
    row = conn.execute("SELECT name, checksum FROM schema_migrations WHERE version = 1").fetchone()
    if row is None:
        raise SystemExit("Migration 0001 is not applied here. Nothing to do.")
    if row[1] == migration.checksum:
        print("The database already holds the checksum of today's file. Nothing to do.")
    else:
        conn.execute(
            "UPDATE schema_migrations SET checksum = %s WHERE version = 1 AND checksum = %s",
            (migration.checksum, row[1]),
        )
        print(f"Accepted: 0001_{row[0]} now has the checksum of today's file.")
