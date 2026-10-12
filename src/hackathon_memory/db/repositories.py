"""Where the repositories of the projects' code are kept (design 7.3, migration 0007).

A project names its code with a link. The repository of that link gets one row here, shared by
every project that names it. The row says what GitHub answered about the README.

The Hedera ids of a README are kept for each project, in hedera_ids (ProjectStore).
"""

from __future__ import annotations

from collections.abc import Mapping

import psycopg

from hackathon_memory.collect.github_facts import RepositoryFacts
from hackathon_memory.collect.github_readmes import Readme
from hackathon_memory.db.projects import IN_THE_README


class RepositoryStore:
    """Keeps the repositories in PostgreSQL. Opens a short connection for each operation."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def code_links(self) -> dict[int, str]:
        """For each project, the first link to its code that has an address."""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT project_id, url FROM links WHERE kind = 'code' AND url IS NOT NULL "
                "ORDER BY project_id, position"
            ).fetchall()
        first: dict[int, str] = {}
        for project_id, url in rows:
            first.setdefault(project_id, url)
        return first

    def link(self, repository_of_project: Mapping[int, str]) -> dict[str, int]:
        """Make a row for each repository, and set the repository of each project, in one
        transaction. A project that no longer names a repository loses it, and the ids of its
        old README with it. Returns the id of each repository.
        """
        urls = sorted(set(repository_of_project.values()))
        projects = sorted(repository_of_project)
        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO repositories (url) VALUES (%s) ON CONFLICT (url) DO NOTHING",
                    [(url,) for url in urls],
                )
            ids = dict(
                conn.execute(
                    "SELECT url, id FROM repositories WHERE url = ANY(%s)", (urls,)
                ).fetchall()
            )
            left = conn.execute(
                "UPDATE projects SET repository_id = NULL, proof_status = NULL "
                "WHERE repository_id IS NOT NULL AND id <> ALL(%s) RETURNING id",
                (projects,),
            ).fetchall()
            if left:
                conn.execute(
                    "DELETE FROM hedera_ids WHERE found_in = %s AND project_id = ANY(%s)",
                    (IN_THE_README, [project_id for (project_id,) in left]),
                )
            with conn.cursor() as cursor:
                cursor.executemany(
                    "UPDATE projects SET repository_id = %s "
                    "WHERE id = %s AND repository_id IS DISTINCT FROM %s",
                    [
                        (ids[url], project_id, ids[url])
                        for project_id, url in sorted(repository_of_project.items())
                    ],
                )
        return ids

    def save_readme(self, url: str, readme: Readme) -> None:
        """Write what GitHub answered about the README of a repository."""
        taken_out = readme.taken_out
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "UPDATE repositories SET readme_status = %s, readme_name = %s, "
                "readme_sha256 = %s, readme_fetched_at = %s::timestamptz, "
                "people_words_hidden = %s, team_lines_cut = %s, ids_in_the_cut = %s "
                "WHERE url = %s",
                (
                    readme.status,
                    readme.name,
                    readme.sha256,
                    readme.fetched_at,
                    int(taken_out.get("words_hidden", 0)),
                    int(taken_out.get("team_lines_cut", 0)),
                    int(taken_out.get("ids_in_the_cut", 0)),
                    url,
                ),
            )

    def save_facts(self, url: str, facts: RepositoryFacts) -> None:
        """Write what GitHub answered about a repository: its dates and its state."""
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "UPDATE repositories SET code_status = %s, code_fetched_at = %s::timestamptz, "
                "made_at = %s, last_push_at = %s, archived = %s, fork = %s, language = %s, "
                "current_url = %s WHERE url = %s",
                (
                    facts.status,
                    facts.fetched_at,
                    facts.created_at,
                    facts.pushed_at,
                    facts.archived,
                    facts.fork,
                    facts.language,
                    facts.current_url,
                    url,
                ),
            )

    def counts(self) -> dict[str, int]:
        """How many repositories there are, and how many of each answer about the README."""
        with psycopg.connect(self._conninfo) as conn:
            total = conn.execute("SELECT count(*) FROM repositories").fetchone()[0]
            by_status = conn.execute(
                "SELECT coalesce(readme_status, 'not_asked'), count(*) FROM repositories GROUP BY 1"
            ).fetchall()
            linked = conn.execute(
                "SELECT count(*) FROM projects WHERE repository_id IS NOT NULL"
            ).fetchone()[0]
        return {"repositories": total, "projects_with_a_repository": linked} | {
            f"readme_{status}": number for status, number in by_status
        }
