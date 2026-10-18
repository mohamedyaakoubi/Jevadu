"""Where the cards of the LLM are kept (design 4.1, 6.3, 6.5; migration 0010).

The model reads the text of a full card: its name, its short line, and each section of the page
with its title, as the parser copied them (design 6.2). A winner entry gets no card of the LLM
(design 4.6). A card is made again only when that text, the model or the version of the
instructions changes (design 6.5).
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from hackathon_memory.llm.gemini import CardResult
from hackathon_memory.parse.project import FULL_CARD
from hackathon_memory.read.quotes import CheckedCard


@dataclass(frozen=True)
class CardInput:
    """What the model reads of one project, and where the project's page is."""

    project_id: int
    page: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def card_text(name: str, short_line: str, sections: list[tuple[str, str]]) -> str:
    """The name, the short line, then each section as its title and its words."""
    parts = [name.strip(), short_line.strip()]
    for title, body in sections:
        parts.append("\n".join(part for part in (title.strip(), body.strip()) if part))
    return "\n\n".join(part for part in parts if part)


class CardStore:
    """Keeps the cards in PostgreSQL. Opens a short connection for each operation."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def inputs(self, pages: Collection[str] | None = None) -> list[CardInput]:
        """The text of each full card, for the pages named, or for every one."""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT p.id, p.page_url, p.name, p.short_line, "
                "coalesce(json_agg(json_build_array(coalesce(s.title, ''), s.body) "
                "ORDER BY s.position) FILTER (WHERE s.project_id IS NOT NULL), '[]') "
                "FROM projects p LEFT JOIN sections s ON s.project_id = p.id "
                "WHERE p.entry_kind = %s GROUP BY p.id ORDER BY p.id",
                (FULL_CARD,),
            ).fetchall()
        wanted = None if pages is None else set(pages)
        return [
            CardInput(project_id, page, card_text(name, short_line, [tuple(s) for s in sections]))
            for project_id, page, name, short_line, sections in rows
            if wanted is None or page in wanted
        ]

    def known(self, model: str, instructions_version: str) -> dict[int, str]:
        """For each project with a card of this model and version, the fingerprint of its text."""
        with psycopg.connect(self._conninfo) as conn:
            rows = conn.execute(
                "SELECT project_id, input_sha256 FROM cards "
                "WHERE model = %s AND instructions_version = %s",
                (model, instructions_version),
            ).fetchall()
        return dict(rows)

    def save(
        self,
        card: CardInput,
        result: CardResult,
        checked: CheckedCard,
        *,
        made_at: datetime | None = None,
    ) -> None:
        """Keep the card, in place of an older one of the same model and version. `made_at` is
        the time of a card put back from a file (read/restore.py); a new card is made now."""
        usage = result.usage
        cost = result.cost_usd
        with psycopg.connect(self._conninfo) as conn:
            conn.execute(
                "INSERT INTO cards (project_id, model, instructions_version, thinking_level, "
                "input_sha256, fields, answer, quotes_given, quotes_found, fields_dropped, "
                "attempts, input_tokens, output_tokens, thinking_tokens, cost_usd, made_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "coalesce(%s, now())) "
                "ON CONFLICT (project_id, model, instructions_version) DO UPDATE SET "
                "thinking_level = EXCLUDED.thinking_level, input_sha256 = EXCLUDED.input_sha256, "
                "fields = EXCLUDED.fields, answer = EXCLUDED.answer, "
                "quotes_given = EXCLUDED.quotes_given, quotes_found = EXCLUDED.quotes_found, "
                "fields_dropped = EXCLUDED.fields_dropped, attempts = EXCLUDED.attempts, "
                "input_tokens = EXCLUDED.input_tokens, output_tokens = EXCLUDED.output_tokens, "
                "thinking_tokens = EXCLUDED.thinking_tokens, cost_usd = EXCLUDED.cost_usd, "
                "made_at = EXCLUDED.made_at",
                (
                    card.project_id,
                    result.model,
                    result.instructions_version,
                    result.thinking_level,
                    card.sha256,
                    Jsonb(checked.as_json()),
                    Jsonb(result.fields.model_dump(mode="json")),
                    checked.quotes_given,
                    checked.quotes_found,
                    len(checked.dropped()),
                    result.attempts,
                    usage.prompt_tokens,
                    usage.output_tokens,
                    usage.thought_tokens,
                    cost,
                    made_at,
                ),
            )

    def counts(self, model: str, instructions_version: str) -> dict[str, int]:
        """How many cards, quotes and dropped fields there are for this model and version."""
        with psycopg.connect(self._conninfo) as conn:
            row = conn.execute(
                "SELECT count(*), coalesce(sum(quotes_given), 0), coalesce(sum(quotes_found), 0), "
                "coalesce(sum(fields_dropped), 0) FROM cards "
                "WHERE model = %s AND instructions_version = %s",
                (model, instructions_version),
            ).fetchone()
        return dict(
            zip(("cards", "quotes_given", "quotes_found", "fields_dropped"), row, strict=True)
        )
