"""How often the button "Read again now" may be pressed (migration 0031, design 7.3).

The button skips what is kept and asks GitHub and the mirror node at once, so it has a limit: one
press every 3 hours for each repository that is checked and for each project on its card, whoever
presses (6 November 2026). A plain check and the rounds of the website are not counted: they take
what is kept, and ask only for what is old. A reading that failed does not count: its press is given
back, so that the team can try again.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg

EVERY = timedelta(hours=3)


def of_project(project_id: int) -> str:
    """What the button of a card is counted on. The button of a check is counted on the link of
    its repository."""
    return f"project:{project_id}"


def free_from(conn: psycopg.Connection, what: str, now: datetime | None = None) -> datetime | None:
    """When the button can be pressed again for `what`, on an open connection; None when it can
    be pressed now."""
    row = conn.execute("SELECT used_at FROM read_again_uses WHERE what = %s", (what,)).fetchone()
    if row is None:
        return None
    free = row[0].astimezone(UTC) + EVERY
    return free if free > (now or datetime.now(UTC)) else None


class ReadAgainStore:
    """The presses, in PostgreSQL. A short connection for each call."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def free_from(self, what: str, now: datetime | None = None) -> datetime | None:
        with psycopg.connect(self._conninfo) as conn:
            return free_from(conn, what, now)

    def take(self, what: str, now: datetime | None = None) -> bool:
        """One press, unless the last one is younger than EVERY. In one statement, so that two
        presses at the same moment count as one."""
        now = now or datetime.now(UTC)
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "INSERT INTO read_again_uses (what, used_at) VALUES (%s, %s) "
                "ON CONFLICT (what) DO UPDATE SET used_at = EXCLUDED.used_at "
                "WHERE read_again_uses.used_at <= %s RETURNING used_at",
                (what, now, now - EVERY),
            ).fetchone()
        return row is not None

    def give_back(self, what: str, now: datetime | None = None) -> None:
        """Forget the press made up to `now`: its reading failed. A later press stays."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "DELETE FROM read_again_uses WHERE what = %s AND used_at <= %s",
                (what, now or datetime.now(UTC)),
            )
