"""Find the projects closest to an idea, by meaning and by words (design 8.2).

Two lists are made, and merged:

* **By meaning.** The idea is embedded as a question, and every project embedding is compared
  with it (an exact search, design 11.6). The 50 closest are kept.
* **By words.** PostgreSQL's own text search over the name (weighted most), the short line and
  the two texts of each project, in English, with any of the words of the idea. The 50 best are
  kept. The texts of the page are always searched, so a weak field can never hide a project.

The two lists are merged by reciprocal rank fusion: each list gives a project 1 / (60 + its
rank), and the sums decide. The number 60 is the one of the paper that brought the method in:
Cormack, Clarke and Buettcher, "Reciprocal rank fusion outperforms Condorcet and individual rank
learning methods", SIGIR 2009. It needs no tuning, which is why it is used before any test.

The idea itself is kept nowhere. Its embedding is kept for a day under the fingerprint of the
idea, so that the same idea is not paid for twice (db/embeddings.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from hackathon_memory.db.embeddings import EmbeddingStore, idea_fingerprint
from hackathon_memory.llm.embeddings import embed_query

RRF_K = 60
CANDIDATES = 50  # from each of the two lists
LANGUAGE = "english"  # the texts of the showcase are in English

# The text search of one project: its name counts most, then its short line, then its texts.
# The words of the idea are taken with "or" in place of "and": a project that has some of them
# is found, and one that has more of them ranks higher. They are cast, not parsed again, so that
# a word is not shortened twice.
_WORDS = """
WITH idea AS (
    SELECT replace(plainto_tsquery(%(language)s, %(idea)s)::text, '&', '|')::tsquery AS words
), documents AS (
    SELECT p.id,
           setweight(to_tsvector(%(language)s, p.name), 'A')
           || setweight(to_tsvector(%(language)s, p.short_line), 'B')
           || setweight(to_tsvector(%(language)s, coalesce(string_agg(s.body, ' '), '')), 'C')
           AS document
    FROM projects p LEFT JOIN sections s ON s.project_id = p.id
    GROUP BY p.id
)
SELECT d.id, ts_rank_cd(d.document, i.words) AS rank
FROM documents d, idea i
WHERE numnode(i.words) > 0 AND d.document @@ i.words
ORDER BY rank DESC, d.id
LIMIT %(limit)s
"""


@dataclass(frozen=True)
class Hit:
    project_id: int
    score: float  # the sum of the reciprocal ranks
    meaning_rank: int | None  # its place in the list by meaning, from 1, or None
    words_rank: int | None  # its place in the list by words, from 1, or None


def merge(by_meaning: list[int], by_words: list[int], *, k: int = RRF_K) -> list[Hit]:
    """Reciprocal rank fusion of two ranked lists of projects, best first."""
    meaning = {project: rank for rank, project in enumerate(by_meaning, start=1)}
    words = {project: rank for rank, project in enumerate(by_words, start=1)}
    hits = [
        Hit(
            project,
            sum(1 / (k + rank) for rank in (meaning.get(project), words.get(project)) if rank),
            meaning.get(project),
            words.get(project),
        )
        for project in dict.fromkeys([*by_meaning, *by_words])
    ]
    return sorted(hits, key=lambda hit: (-hit.score, hit.project_id))


def by_words(conninfo: str, idea: str, *, limit: int = CANDIDATES) -> list[int]:
    """The projects whose words match any word of the idea, best first."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(_WORDS, {"language": LANGUAGE, "idea": idea, "limit": limit})
        return [project for project, _ in rows.fetchall()]


def by_meaning(
    store: EmbeddingStore,
    client: Any,
    idea: str,
    *,
    model: str,
    limit: int = CANDIDATES,
    now: datetime | None = None,
) -> list[int]:
    """The projects closest in meaning to the idea, closest first. The idea is embedded once a
    day at most."""
    store.forget_old_ideas(now)
    fingerprint = idea_fingerprint(idea)
    values = store.idea(fingerprint, model, now)
    if values is None:
        values = embed_query(client, idea, model=model).values
        store.save_idea(fingerprint, model, values, now)
    return [project for project, _ in store.nearest(values, model, limit=limit)]


def search(
    conninfo: str,
    client: Any,
    idea: str,
    *,
    model: str,
    limit: int = 10,
    now: datetime | None = None,
) -> list[Hit]:
    """The projects closest to the idea, best first. With no project embedding of the model, only
    the words are searched, and the idea is not embedded: nothing is paid for."""
    if not idea.strip():
        return []
    store = EmbeddingStore(conninfo)
    meaning = (
        by_meaning(store, client, idea, model=model, now=now)
        if store.counts(model)["embeddings"]
        else []
    )
    return merge(meaning, by_words(conninfo, idea))[:limit]
