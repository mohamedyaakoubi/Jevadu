"""What the pages show, read from the tables (design 4.1).

A card has three sources, and the page keeps them apart:

* the page, copied word for word by the parser: the name, the short line, the texts, the links,
  the event and the prize;
* the code host and the ledger, read by code: the repository, its dates, each Hedera ID and what
  the mirror node said about it, the proof status and the life status;
* the model: the fields of the card of the instructions in use, each with its label and the
  quotes that the program found in the page.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg
from markupsafe import Markup, escape

from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.read.quotes import FIELDS, KEPT
from hackathon_memory.search import listing
from hackathon_memory.search.engine import LANGUAGE, Hit
from hackathon_memory.search.listing import ResultCard

FIELD_TITLES = {
    "what_it_does": "What it does",
    "how_it_works": "How it works",
    "for_whom": "For whom",
    "hedera_services": "Hedera services",
    "category": "Category",
    "problem": "Problem",
    "solution": "Solution",
}
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
# HashScan has a page for each of these kinds; a number of another kind, or not found, gets none.
HASHSCAN_KINDS = frozenset({"account", "contract", "topic", "token"})
NETWORKS = frozenset({"mainnet", "testnet", "previewnet"})


def hashscan(network: str | None, kind: str | None, entity_id: str) -> str | None:
    """The page of an ID on HashScan, where anybody can see what the mirror node says."""
    if network not in NETWORKS or kind not in HASHSCAN_KINDS:
        return None
    return f"https://hashscan.io/{network}/{kind}/{entity_id}"


@dataclass(frozen=True)
class Summary:
    """The one sentence that a result shows, and where it comes from."""

    text: str
    source: str  # "model" or "page"
    label: str | None  # the label of the model's field, when it comes from the model


@dataclass(frozen=True)
class Section:
    title: str
    body: str


@dataclass(frozen=True)
class PageLink:
    kind: str
    url: str
    label: str


@dataclass(frozen=True)
class Prize:
    sponsor: str
    track: str | None
    award: str | None


@dataclass(frozen=True)
class ModelField:
    name: str
    title: str
    label: str
    state: str  # kept, dropped or not_found (design 6.3)
    value: str | list[str]
    quotes: tuple[str, ...]


@dataclass(frozen=True)
class ModelCard:
    model: str
    instructions_version: str
    made_at: datetime
    fields: tuple[ModelField, ...]


@dataclass(frozen=True)
class ProjectCard:
    facts: ResultCard  # the event, the prize, the proof, the life, the ledger, the repository
    short_line: str
    sections: tuple[Section, ...]
    links: tuple[PageLink, ...]
    prizes: tuple[Prize, ...]
    parsed_at: datetime | None
    collected_at: datetime | None  # when the page was saved from its site
    language: str | None
    card: ModelCard | None


def first_sentence(text: str) -> str:
    return next((part.strip() for part in _SENTENCE_END.split(text or "") if part.strip()), "")


def summaries(
    conninfo: str, project_ids: Sequence[int], *, model: str, version: str
) -> dict[int, Summary]:
    """For each project: the model's sentence "what it does" when its card keeps it, otherwise
    the short line, otherwise the first sentence of the first text of the page."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT p.id, coalesce(p.short_line, ''), "
            "coalesce((SELECT s.body FROM sections s WHERE s.project_id = p.id "
            "ORDER BY s.position LIMIT 1), ''), c.fields -> 'what_it_does' "
            "FROM projects p LEFT JOIN cards c ON c.project_id = p.id AND c.model = %s "
            "AND c.instructions_version = %s WHERE p.id = ANY(%s)",
            (model, version, list(project_ids)),
        ).fetchall()
    found = {}
    for project_id, short_line, first_text, field in rows:
        if field and field.get("state") == KEPT and field.get("value"):
            found[project_id] = Summary(field["value"], "model", field.get("label"))
        else:
            found[project_id] = Summary(short_line.strip() or first_sentence(first_text), "page",
                                        None)  # fmt: skip
    return found


def project_card(
    conninfo: str,
    project_id: int,
    *,
    model: str,
    version: str,
    raw_dir: Path | None = None,
    now: datetime | None = None,
) -> ProjectCard | None:
    """Everything that the card of one project shows, or None when there is no such project."""
    found = listing.cards(conninfo, [Hit(project_id, 0.0, None, None)], now=now)
    if not found:
        return None
    with psycopg.connect(conninfo) as conn:
        short_line, parsed_at, language = conn.execute(
            "SELECT coalesce(p.short_line, ''), p.parsed_at, r.language FROM projects p "
            "LEFT JOIN repositories r ON r.id = p.repository_id WHERE p.id = %s",
            (project_id,),
        ).fetchone()
        sections = tuple(
            Section(title or "", body)
            for title, body in conn.execute(
                "SELECT title, body FROM sections WHERE project_id = %s ORDER BY position",
                (project_id,),
            ).fetchall()
        )
        links = tuple(
            PageLink(kind, url, label or "")
            for kind, url, label in conn.execute(
                "SELECT kind, url, label FROM links WHERE project_id = %s AND url IS NOT NULL "
                "ORDER BY position",
                (project_id,),
            ).fetchall()
        )
        prizes = tuple(
            Prize(sponsor or "", track, award)
            for sponsor, track, award in conn.execute(
                "SELECT sponsor, track, award FROM prizes WHERE project_id = %s ORDER BY position",
                (project_id,),
            ).fetchall()
        )
        row = conn.execute(
            "SELECT fields, made_at FROM cards WHERE project_id = %s AND model = %s "
            "AND instructions_version = %s",
            (project_id, model, version),
        ).fetchone()
    card = None
    if row is not None:
        fields, made_at = row
        card = ModelCard(model, version, made_at, tuple(
            ModelField(name, FIELD_TITLES[name], fields[name]["label"], fields[name]["state"],
                       fields[name]["value"], tuple(fields[name]["quotes"]))
            for name in FIELDS
        ))  # fmt: skip
    return ProjectCard(found[0], short_line, sections, links, prizes, parsed_at,
                       collected_at(raw_dir, found[0].page_url), language, card)  # fmt: skip


def collected_at(raw_dir: Path | None, page_url: str) -> datetime | None:
    """When the page was saved from its site, from the record kept next to the saved page."""
    saved = RawStore(raw_dir).load(page_url) if raw_dir is not None else None
    fetched = saved.meta.get("fetched_at") if saved else None
    try:
        return datetime.fromisoformat(fetched.replace("Z", "+00:00")) if fetched else None
    except ValueError:
        return None


# ------------------------------------------------------------------ what the list shows

# Two characters that a page never uses mark the start and the end of a matched word. The text is
# escaped first, and only then are they turned into <mark>, so no text of a page can reach the
# browser as code (PostgreSQL's manual warns that ts_headline does not make its output safe).
_START, _STOP = "", ""
_MARK_OPEN, _MARK_CLOSE = Markup("<mark>"), Markup("</mark>")
_HEADLINE_OPTIONS = (
    f'StartSel="{_START}", StopSel="{_STOP}", MaxWords=24, MinWords=10, MaxFragments=1, '
    'FragmentDelimiter=" ... "'
)


def matched_words(conninfo: str, project_ids: Sequence[int], idea: str) -> dict[int, Markup]:
    """For each project whose page has a word of the idea: the part of its short line and first
    text where those words stand, with each one marked. A project found only by meaning has
    none."""
    if not project_ids or not idea.strip():
        return {}
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "WITH q AS (SELECT replace(plainto_tsquery(%(language)s, %(idea)s)::text, ' & ', "
            "' | ')::tsquery AS query), docs AS (SELECT p.id, concat_ws(' ', p.short_line, "
            "(SELECT s.body FROM sections s WHERE s.project_id = p.id ORDER BY s.position "
            "LIMIT 1)) AS document FROM projects p WHERE p.id = ANY(%(ids)s)) "
            "SELECT d.id, ts_headline(%(language)s, d.document, q.query, %(options)s) "
            "FROM docs d, q WHERE q.query::text <> '' "
            "AND to_tsvector(%(language)s, d.document) @@ q.query",
            {"language": LANGUAGE, "idea": idea, "ids": list(project_ids),
             "options": _HEADLINE_OPTIONS},
        ).fetchall()  # fmt: skip
    return {
        project_id: escape(" ".join(headline.split()))
        .replace(_START, _MARK_OPEN)
        .replace(_STOP, _MARK_CLOSE)
        for project_id, headline in rows
    }


def browse(
    conninfo: str, only: Sequence[int] | None, *, offset: int, limit: int
) -> tuple[list[int], int]:
    """The projects to list when no idea is given, newest events first, and how many there are
    in all. With `only`, the projects are those (the filters)."""
    ids = None if only is None else list(only)
    with psycopg.connect(conninfo) as conn:
        total = conn.execute(
            "SELECT count(*) FROM projects WHERE %s::bigint[] IS NULL OR id = ANY(%s)", (ids, ids)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT p.id FROM projects p JOIN events e ON e.id = p.event_id "
            "WHERE %s::bigint[] IS NULL OR p.id = ANY(%s) "
            "ORDER BY coalesce(e.ends_on, e.starts_at::date) DESC NULLS LAST, e.name, p.name, p.id "
            "OFFSET %s LIMIT %s",
            (ids, ids, offset, limit),
        ).fetchall()
    return [row[0] for row in rows], total


def marked_lines(conninfo: str, lines: dict[int, str], idea: str) -> dict[int, Markup]:
    """Each line (the sentence that a result shows) with the words of the idea marked, for the
    lines that have one. The words count by their stem, as in the search by words."""
    if not lines or not idea.strip():
        return {}
    ids = list(lines)
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "WITH q AS (SELECT replace(plainto_tsquery(%(language)s, %(idea)s)::text, ' & ', "
            "' | ')::tsquery AS query) "
            "SELECT t.id, ts_headline(%(language)s, t.line, q.query, %(options)s) "
            "FROM unnest(%(ids)s::bigint[], %(lines)s::text[]) AS t(id, line), q "
            "WHERE q.query::text <> '' AND to_tsvector(%(language)s, t.line) @@ q.query",
            {"language": LANGUAGE, "idea": idea, "ids": ids, "lines": [lines[i] for i in ids],
             "options": f'StartSel="{_START}", StopSel="{_STOP}", HighlightAll=true'},
        ).fetchall()  # fmt: skip
    return {
        project_id: escape(" ".join(line.split()))
        .replace(_START, _MARK_OPEN)
        .replace(_STOP, _MARK_CLOSE)
        for project_id, line in rows
    }
