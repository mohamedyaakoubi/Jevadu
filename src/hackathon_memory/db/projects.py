"""Where the parsed projects are kept (design 10, the tables of migration 0003).

One call saves one project with all that the parser read from its page, in one transaction: a
project is in the database whole, or not at all. Saving the same page, read by the same parser,
a second time does nothing. So the step that parses the saved pages is safe to run again
(design 11.6), and it reads a page again only when the page or the parser has changed.

What the check adds later (ids found in a README, facts of the ledger and of the code) is not
touched when a page is parsed again. Only the result of the proof rule for that project is set
back to "not checked", because the ids of the page may have changed.
"""

from __future__ import annotations

from dataclasses import asdict

import psycopg
from psycopg.types.json import Jsonb

from hackathon_memory.parse.project import ProjectPage

# What saving a project did.
NEW = "new"
CHANGED = "changed"
SAME = "same"

FULL_CARD = "full_card"
# Where an id was found. The parser of a page writes only ids of the first kind.
ON_THE_PAGE = "page"


class ProjectStore:
    """Keeps parsed projects in PostgreSQL. Opens a short connection for each operation."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def already_parsed(self) -> dict[str, tuple[str, str]]:
        """For each page address: the fingerprint of the page and the parser that read it."""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute("SELECT page_url, page_sha256, parser FROM projects").fetchall()
        return {url: (sha256, parser) for url, sha256, parser in rows}

    def save(self, page: ProjectPage, page_sha256: str) -> str:
        """Save one project. Returns NEW, CHANGED or SAME."""
        with psycopg.connect(self._conninfo) as conn:  # one transaction, committed at the end
            known = conn.execute(
                "SELECT id, page_sha256, parser FROM projects WHERE page_url = %s FOR UPDATE",
                (page.page,),
            ).fetchone()
            if known and known[1:] == (page_sha256, page.parser):
                return SAME
            event_id = conn.execute(
                "INSERT INTO events (site, slug, name, starts_at) "
                "VALUES (%s, %s, %s, %s::timestamptz) "
                "ON CONFLICT (site, slug) DO UPDATE SET name = EXCLUDED.name, "
                "starts_at = COALESCE(EXCLUDED.starts_at, events.starts_at) RETURNING id",
                (page.event.site, page.event.slug, page.event.name, page.event.starts_at),
            ).fetchone()[0]
            facts = (
                page.site,
                page.site_key,
                FULL_CARD,
                event_id,
                page.name,
                page.short_line,
                page.prize_state,
                page.has_video,
                page_sha256,
                page.parser,
            )
            if known:
                project_id = known[0]
                conn.execute(
                    "UPDATE projects SET site = %s, site_key = %s, entry_kind = %s, "
                    "event_id = %s, name = %s, short_line = %s, prize_state = %s, "
                    "has_video = %s, page_sha256 = %s, parser = %s, parsed_at = now(), "
                    "proof_status = NULL WHERE id = %s",  # its ids may have changed
                    (*facts, project_id),
                )
                for table in ("prizes", "links", "sections"):
                    conn.execute(
                        f"DELETE FROM {table} WHERE project_id = %s",  # noqa: S608  (fixed names)
                        (project_id,),
                    )
                conn.execute(
                    "DELETE FROM hedera_ids WHERE project_id = %s AND found_in = %s",
                    (project_id, ON_THE_PAGE),
                )
            else:
                project_id = conn.execute(
                    "INSERT INTO projects (site, site_key, entry_kind, event_id, name, "
                    "short_line, prize_state, has_video, page_sha256, parser, page_url) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (*facts, page.page),
                ).fetchone()[0]
            self._save_parts(conn, project_id, page)
        return CHANGED if known else NEW

    @staticmethod
    def _save_parts(conn: psycopg.Connection, project_id: int, page: ProjectPage) -> None:
        with conn.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO prizes (project_id, position, sponsor, sponsor_id, track, award, "
                "kind, pool, line) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (project_id, at, p.sponsor, p.sponsor_id, p.track, p.award, p.kind, p.pool,
                     p.line)
                    for at, p in enumerate(page.prizes, start=1)
                ],
            )  # fmt: skip
            cursor.executemany(
                "INSERT INTO links (project_id, position, kind, url, label) "
                "VALUES (%s, %s, %s, %s, %s)",
                [
                    (project_id, at, link.kind, link.url, link.label)
                    for at, link in enumerate(page.links, start=1)
                ],
            )
            cursor.executemany(
                "INSERT INTO sections (project_id, position, kind, title, body, blocks) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (
                        project_id,
                        at,
                        section.kind,
                        section.title,
                        section.text,
                        Jsonb([asdict(block) for block in section.blocks]),
                    )
                    for at, section in enumerate(page.sections, start=1)
                ],
            )
            cursor.executemany(
                "INSERT INTO hedera_ids (project_id, entity_id, network, said_kind, found_in, "
                "words_around, in_hashscan_link) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        project_id,
                        found.entity_id,
                        found.network,
                        found.said_kind,
                        ON_THE_PAGE,
                        found.words_around,
                        found.in_hashscan_link,
                    )
                    for found in page.hedera_ids
                ],
            )

    def counts(self) -> dict[str, int]:
        """How many rows the tables hold, and how many projects of each prize state."""
        with psycopg.connect(self._conninfo) as conn:
            counts = {
                table: conn.execute(
                    f"SELECT count(*) FROM {table}"  # noqa: S608  (fixed names)
                ).fetchone()[0]
                for table in ("events", "projects", "prizes", "links", "sections", "hedera_ids")
            }
            by_state = conn.execute(
                "SELECT prize_state, count(*) FROM projects GROUP BY prize_state"
            ).fetchall()
        return counts | {state: number for state, number in by_state}
