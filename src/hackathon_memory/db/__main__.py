"""Command line for the database:  python -m hackathon_memory.db migrate | status

It prints migration names and states. It never prints the connection text, which holds a password.
"""

from __future__ import annotations

import sys

import psycopg

from hackathon_memory.db.migrate import MigrationError, migrate, status
from hackathon_memory.settings import Settings, SettingsError


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("migrate", "status"):
        print("usage: python -m hackathon_memory.db migrate | status")
        return 2
    try:
        conninfo = Settings().database_conninfo()
        if argv[0] == "migrate":
            applied = migrate(conninfo)
            if not applied:
                print("Nothing to do: every migration is already applied.")
            for m in applied:
                print(f"Applied {m.version:04d}_{m.name}")
        else:
            for state in status(conninfo):
                mark = "applied" if state.applied else "pending"
                print(f"{state.migration.version:04d}_{state.migration.name}: {mark}")
    except (SettingsError, MigrationError) as error:
        print(f"Stopped: {error}")
        return 1
    except psycopg.OperationalError:
        # The message of this error can hold the connection text, so it is not shown.
        print("Stopped: cannot reach the database. Is it running? (docker compose up -d db)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
