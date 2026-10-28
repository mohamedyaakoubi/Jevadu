"""Where the readings of the projects are kept (migration 0019, check/readings.py).

A reading compares what the tool holds about a project before and after it asks GitHub and the
ledger again (design 7.3, 28 October 2026). `states` takes that picture for some projects or for
all of them, in a few queries over the tables, so that the step `refresh` can take it for the
whole collection; `save` keeps what changed, and `latest` gives a card its newest reading.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

import psycopg

from hackathon_memory.check.readings import ProjectState
from hackathon_memory.db.history import OWN

BUTTON, ROUND, REFRESH = "button", "round", "refresh"  # who read: the card, the website, the step
SERVICE = "feature"  # a Hedera service that the code calls (migration 0014)


@dataclass(frozen=True)
class Reading:
    """One reading of a project, for its card."""

    read_at: datetime
    source: str
    changes: tuple[str, ...]


class ReadingStore:
    """Keeps the readings in PostgreSQL. A short connection for each call."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def states(self, projects: Iterable[int] | None = None) -> dict[int, ProjectState]:
        """What the tool holds about each project, for all of them when `projects` is None."""
        only = sorted(projects) if projects is not None else None
        args = (only,) if only is not None else ()
        of_projects = " WHERE p.id = ANY(%s)" if only is not None else ""
        of_ids = " WHERE h.project_id = ANY(%s)" if only is not None else ""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT p.id, r.code_status, r.last_push_at, r.readme_sha256, r.archive_commit "  # noqa: S608  (fixed text)
                "FROM projects p LEFT JOIN repositories r ON r.id = p.repository_id" + of_projects,
                args,
            ).fetchall()
            services: dict[int, set[str]] = defaultdict(set)
            for project_id, name in conn.execute(
                "SELECT p.id, f.name FROM projects p JOIN hedera_in_code f "  # noqa: S608  (fixed text)
                "ON f.repository_id = p.repository_id AND f.kind = %s" + of_projects,
                (SERVICE, *args),
            ):
                services[project_id].add(name)
            ids: dict[int, set[str]] = defaultdict(set)
            statuses: dict[int, dict[str, str]] = defaultdict(dict)
            for project_id, entity, status in conn.execute(
                "SELECT h.project_id, h.entity_id, c.status FROM hedera_ids h "  # noqa: S608  (fixed text)
                "LEFT JOIN id_checks c ON c.hedera_id = h.id"
                + of_ids
                + " ORDER BY h.project_id, h.entity_id, c.network",
                args,
            ):
                ids[project_id].add(entity)
                if status is not None:
                    statuses[project_id].setdefault(entity, status)  # the first network's
            events = dict(conn.execute(
                OWN  # noqa: S608  (fixed text)
                + "SELECT h.project_id, count(e.stamp) FROM (SELECT DISTINCT project_id, entity_id "
                "FROM hedera_ids) h JOIN own USING (entity_id) "
                "JOIN ledger_events e ON e.entity_id = h.entity_id" + of_ids + " GROUP BY 1",
                args,
            ).fetchall())  # fmt: skip
        return {
            project_id: ProjectState(code_status, last_push_at, readme, commit,
                                     frozenset(services[project_id]), frozenset(ids[project_id]),
                                     dict(statuses[project_id]), events.get(project_id, 0))
            for project_id, code_status, last_push_at, readme, commit in rows
        }  # fmt: skip

    def save(self, rows: Sequence[tuple[int, datetime, str, tuple[str, ...]]]) -> None:
        """Keep readings: (project, moment, who read, what changed)."""
        if not rows:
            return
        with psycopg.connect(self._conninfo) as conn, conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO project_readings (project_id, read_at, source, changes) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (project_id, read_at) "
                "DO UPDATE SET source = EXCLUDED.source, changes = EXCLUDED.changes",
                [(project_id, read_at, source, list(changes))
                 for project_id, read_at, source, changes in rows],
            )  # fmt: skip

    def latest(self, project_id: int) -> Reading | None:
        """The newest reading of a project, whoever made it."""
        with psycopg.connect(self._conninfo) as conn:
            return latest_reading(conn, project_id)


def latest_reading(conn: psycopg.Connection, project_id: int) -> Reading | None:
    """The newest reading of a project, whoever made it, on an open connection."""
    row = conn.execute(
        "SELECT read_at, source, changes FROM project_readings WHERE project_id = %s "
        "ORDER BY read_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    return Reading(row[0], row[1], tuple(row[2])) if row is not None else None
