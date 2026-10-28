"""The Hedera IDs of the code (migration 0017, design 7.3): the candidates that the reading of
each repository found, and the ones that the check gives a project."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import psycopg

IN_THE_CODE = "code"
# The candidates of one project that the check asks about, the ones in the most files first. On 24
# October 2026, 257 of 273 projects with candidates had 30 or fewer; the 16 others had up to 199,
# lists of other people's things such as the tokens of an exchange.
MOST_CANDIDATES = 30


@dataclass(frozen=True)
class Candidate:
    """An ID that the code of a project's repository names, with the days of its event."""

    project_id: int
    entity_id: str
    network: str | None  # None when the code leaves the network open
    path: str  # the first file of the code where it stands
    event_starts_at: datetime | None
    event_ends_on: date | None
    repository: str  # the link of the repository whose code names it


@dataclass(frozen=True)
class Given:
    """An ID of the code that the check gives a project, on the network where it passed."""

    entity_id: str
    network: str
    path: str


# The things that each name of an ID stands for (design 8.4): the name itself, and the ID that the
# ledger gives it on each network where it found it. Two names that share a thing are one ID: an
# EVM address and the 0.0 ID of one contract (28 October 2026). A name never asked stands only for
# itself.
_THINGS = """
WITH thing AS (SELECT entity_id AS name, entity_id AS thing FROM hedera_ids
               UNION SELECT entity_id, entity_id FROM ids_in_code
               UNION SELECT entity_id, ledger_id FROM ledger_facts
               WHERE found AND ledger_id IS NOT NULL)
"""

# The candidates of every project: an ID that the code of its repository names, that no page and
# no README of the collection names (the page's own rule judges an ID that its page names, and
# an ID that another project's page names is not this project's own), and that the code of no
# other repository names, in any of its forms; at most MOST_CANDIDATES, the ones in the most files
# first.
_CANDIDATES = """
SELECT project_id, entity_id, network, path, starts_at, ends_on, repository FROM (
    SELECT p.id AS project_id, c.entity_id, c.network, c.examples[1] AS path, e.starts_at,
           e.ends_on, r.url AS repository, row_number() OVER (PARTITION BY p.id
               ORDER BY c.files DESC, c.entity_id, c.network NULLS FIRST) AS place
    FROM ids_in_code c
    JOIN repositories r ON r.id = c.repository_id
    JOIN projects p ON p.repository_id = c.repository_id
    JOIN events e ON e.id = p.event_id
    WHERE NOT EXISTS (SELECT 1 FROM thing a JOIN thing b USING (thing)
                      JOIN hedera_ids h ON h.entity_id = b.name
                      WHERE a.name = c.entity_id AND h.found_in <> %s)
      AND NOT EXISTS (SELECT 1 FROM thing a JOIN thing b USING (thing)
                      JOIN ids_in_code o ON o.entity_id = b.name
                      WHERE a.name = c.entity_id AND o.repository_id <> c.repository_id)
) ranked
WHERE place <= %s
ORDER BY project_id, place
"""

# Of some names, those that stand for a thing that a page or a README of the collection names, or
# the code of a repository other than one, in any of its forms.
_ELSEWHERE = """
, asked AS (SELECT name, name AS thing FROM unnest(%s::text[]) AS name
            UNION SELECT entity_id, ledger_id FROM ledger_facts
            WHERE found AND ledger_id IS NOT NULL AND entity_id = ANY(%s))
SELECT DISTINCT a.name FROM asked a JOIN thing b USING (thing)
WHERE EXISTS (SELECT 1 FROM hedera_ids h WHERE h.entity_id = b.name AND h.found_in <> %s)
   OR EXISTS (SELECT 1 FROM ids_in_code c JOIN repositories r ON r.id = c.repository_id
              WHERE c.entity_id = b.name AND r.url <> %s)
"""


class CodeIdStore:
    """Reads the candidates and keeps the IDs of the code. A short connection for each call."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def candidates(self) -> list[Candidate]:
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(_THINGS + _CANDIDATES, (IN_THE_CODE, MOST_CANDIDATES))  # noqa: S608
            return [Candidate(*row) for row in rows]

    def named_elsewhere(self, entities: Sequence[str], repository: str) -> set[str]:
        """Of `entities`, those that a page or a README of the collection names, or the code of
        a repository other than `repository`, in any of their forms: not the own IDs of the code
        of `repository`. A form is known once the ledger was asked about the name."""
        with psycopg.connect(self._conninfo) as conn:
            return {entity for (entity,) in conn.execute(
                _THINGS + _ELSEWHERE,  # noqa: S608  (fixed text)
                (list(entities), list(entities), IN_THE_CODE, repository))}  # fmt: skip

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
