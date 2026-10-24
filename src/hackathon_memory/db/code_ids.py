"""The Hedera IDs of the code (migration 0017, design 7.3): the candidates that the reading of
each repository found, and the ones that the check gives a project."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import psycopg

IN_THE_CODE = "code"


@dataclass(frozen=True)
class Candidate:
    """An ID that the code of a project's repository names, with the days of its event."""

    project_id: int
    entity_id: str
    network: str | None  # None when the code leaves the network open
    path: str  # the first file of the code where it stands
    event_starts_at: datetime | None
    event_ends_on: date | None


@dataclass(frozen=True)
class Given:
    """An ID of the code that the check gives a project, on the network where it passed."""

    entity_id: str
    network: str
    path: str


# The candidates of every project: an ID that the code of its repository names, that no page and
# no README of the collection names (the page's own rule judges an ID that its page names, and
# an ID that another project's page names is not this project's own), and that the code of no
# other repository names.
_CANDIDATES = """
SELECT p.id, c.entity_id, c.network, c.examples[1], e.starts_at, e.ends_on
FROM ids_in_code c
JOIN projects p ON p.repository_id = c.repository_id
JOIN events e ON e.id = p.event_id
WHERE NOT EXISTS (SELECT 1 FROM hedera_ids h WHERE h.entity_id = c.entity_id AND h.found_in <> %s)
  AND NOT EXISTS (SELECT 1 FROM ids_in_code o
                  WHERE o.entity_id = c.entity_id AND o.repository_id <> c.repository_id)
ORDER BY p.id, c.entity_id, c.network NULLS FIRST
"""


class CodeIdStore:
    """Reads the candidates and keeps the IDs of the code. A short connection for each call."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def candidates(self) -> list[Candidate]:
        with psycopg.connect(self._conninfo) as conn:
            return [Candidate(*row) for row in conn.execute(_CANDIDATES, (IN_THE_CODE,))]

    def named_elsewhere(self, entities: Sequence[str], repository: str) -> set[str]:
        """Of `entities`, those that a page or a README of the collection names, or the code of
        a repository other than `repository`: not the own IDs of the code of `repository`."""
        with psycopg.connect(self._conninfo) as conn:
            return {entity for (entity,) in conn.execute(
                "SELECT entity_id FROM hedera_ids WHERE entity_id = ANY(%s) AND found_in <> %s "
                "UNION SELECT c.entity_id FROM ids_in_code c "
                "JOIN repositories r ON r.id = c.repository_id "
                "WHERE c.entity_id = ANY(%s) AND r.url <> %s",
                (list(entities), IN_THE_CODE, list(entities), repository))}  # fmt: skip

    def projects_with_code_ids(self) -> set[int]:
        """The projects that hold IDs of the code from an earlier check."""
        with psycopg.connect(self._conninfo) as conn:
            return {pid for (pid,) in conn.execute(
                "SELECT DISTINCT project_id FROM hedera_ids WHERE found_in = %s",
                (IN_THE_CODE,))}  # fmt: skip

    def replace(self, project_id: int, given: Sequence[Given]) -> None:
        """The IDs of the code that the check gives a project, in place of the old ones. No words
        around them are kept; the file where each one stands is."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute("DELETE FROM hedera_ids WHERE project_id = %s AND found_in = %s",
                         (project_id, IN_THE_CODE))  # fmt: skip
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
                    "words_around, in_hashscan_link, found_at) "
                    "VALUES (%s, %s, %s, NULL, %s, '', false, %s)",
                    [(project_id, one.entity_id, one.network, IN_THE_CODE, one.path)
                     for one in given],
                )  # fmt: skip
