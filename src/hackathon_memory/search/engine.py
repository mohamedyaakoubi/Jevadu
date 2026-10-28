"""Find the projects closest to an idea, by meaning and by words (design 8.2).

Two lists are made, and merged:

* **By meaning.** The idea is embedded as a question, and every project embedding is compared
  with it (an exact search, design 11.6).
* **By words.** BM25 over the name, the short line and the two texts of each project, with the
  words of the idea. The texts of the page are always searched, so a weak
  field can never hide a project.

Why BM25 and not PostgreSQL's own ranking: PostgreSQL's ranking functions "do not use any
global information" (its documentation, 12.3.3, read on 12 October 2026). They count how
often a word of the idea stands in a project, but not how rare the word is. In this collection
every project says "Hedera" and "token", so these words decided the order of the first try.
BM25 gives a word a weight that grows as the word gets rarer across the projects, and it stops
counting a word that is repeated many times. The words are cut into their stems by
PostgreSQL's own English rules (to_tsvector), which also drop the small words such as "the".
The two numbers are the usual ones, k1 = 1.2 and b = 0.75: Robertson and Zaragoza, "The
Probabilistic Relevance Framework: BM25 and Beyond", 2009.

The two lists are merged by reciprocal rank fusion: each list gives a project 1 / (60 + its
rank), and the sums decide. The number 60 is the one of the paper that brought the method in:
Cormack, Clarke and Buettcher, "Reciprocal rank fusion outperforms Condorcet and individual rank
learning methods", SIGIR 2009. It needs no tuning, which is why it is used before any test.

Each list gives as many projects as the listing shows (the window). This is the default of
Elasticsearch's own reciprocal rank fusion, whose rank_window_size "defaults to the value of
size" (its reference page, read on 12 October 2026). A first try merged 50 of each list: a
project in the middle of both lists then beat the best one of each, and the closest project
in meaning fell out of the first ten. The window and the constant are compared by the test of
the search (design 13.3).

The idea itself is kept nowhere. Its embedding is kept for a day under the fingerprint of the
idea, so that the same idea is not paid for twice (db/embeddings.py).

The filters of the website (search/filters.py) can limit the search to some projects. Both lists
are then taken from those projects only. The weights of the words are still counted over every
project, so a filter never changes the order of two projects that it keeps.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from hackathon_memory.db.embeddings import EmbeddingStore, idea_fingerprint
from hackathon_memory.llm.embeddings import embed_query

RRF_K = 60
BOTH, MEANING, WORDS = "both", "meaning", "words"
MODES = (BOTH, MEANING, WORDS)  # which lists a search makes
CANDIDATES = 10  # from each of the two lists, when no other number is asked for
LANGUAGE = "english"  # the texts of the showcase are in English

BM25_K1 = 1.2
BM25_B = 0.75

# BM25 over every project. One document is the name, the short line and the two texts. tf is
# how often a stem stands in it, dl its length in stems, and the weight of a stem is
# ln(1 + (n - df + 0.5) / (df + 0.5)), with df the number of projects that have it.
_WORDS = """
WITH documents AS (
    SELECT p.id, to_tsvector(%(language)s, concat_ws(' ', p.name, p.short_line,
                                                    string_agg(s.body, ' '))) AS document
    FROM projects p LEFT JOIN sections s ON s.project_id = p.id
    GROUP BY p.id
), terms AS (
    SELECT d.id, t.lexeme, cardinality(t.positions) AS tf
    FROM documents d, unnest(d.document) AS t
), lengths AS (
    SELECT id, sum(tf) AS dl FROM terms GROUP BY id
), corpus AS (
    SELECT count(*) AS n, avg(dl) AS avgdl FROM lengths
), idea AS (
    SELECT lexeme FROM unnest(to_tsvector(%(language)s, %(idea)s))
), frequency AS (
    SELECT t.lexeme, count(*) AS df FROM terms t JOIN idea USING (lexeme) GROUP BY t.lexeme
)
SELECT t.id,
       sum(ln(1 + (c.n - f.df + 0.5) / (f.df + 0.5))
           * t.tf * (%(k1)s + 1)
           / (t.tf + %(k1)s * (1 - %(b)s + %(b)s * l.dl / c.avgdl))) AS score
FROM terms t
JOIN frequency f USING (lexeme)
JOIN lengths l USING (id)
CROSS JOIN corpus c
WHERE %(only)s::bigint[] IS NULL OR t.id = ANY(%(only)s)
GROUP BY t.id
ORDER BY score DESC, t.id
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


def by_words(
    conninfo: str, idea: str, *, limit: int = CANDIDATES, only: Sequence[int] | None = None
) -> list[int]:
    """The projects that have words of the idea, best first by BM25. With `only`, the projects
    are taken from those alone; the weights of the words still come from every project."""
    values = {"language": LANGUAGE, "idea": idea, "limit": limit, "k1": BM25_K1, "b": BM25_B,
              "only": None if only is None else list(only)}  # fmt: skip
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(_WORDS, values)
        return [project for project, _ in rows.fetchall()]


def by_meaning(
    store: EmbeddingStore,
    client: Any,
    idea: str,
    *,
    model: str,
    limit: int = CANDIDATES,
    now: datetime | None = None,
    only: Sequence[int] | None = None,
) -> list[int]:
    """The projects closest in meaning to the idea, closest first, from `only` when it is given.
    The idea is embedded once a day at most."""
    values = idea_embedding(store, client, idea, model=model, now=now)
    return [project for project, _ in store.nearest(values, model, limit=limit, only=only)]


def idea_embedding(
    store: EmbeddingStore, client: Any, idea: str, *, model: str, now: datetime | None = None
) -> list[float]:
    """The embedding of the idea: the one made less than a day ago, or a new one, kept a day."""
    store.forget_old_ideas(now)
    fingerprint = idea_fingerprint(idea)
    values = store.idea(fingerprint, model, now)
    if values is None:
        values = embed_query(client, idea, model=model).values
        store.save_idea(fingerprint, model, values, now)
    return values


def search(
    conninfo: str,
    client: Any,
    idea: str,
    *,
    model: str,
    limit: int = 10,
    now: datetime | None = None,
    only: Sequence[int] | None = None,
    mode: str = BOTH,
) -> list[Hit]:
    """The projects closest to the idea, best first, from the projects of `only` when it is given
    (the filters). The mode says which lists are made: both (the default), meaning or words.
    With no project embedding of the model, only the words are searched, and the idea is not
    embedded: nothing is paid for. No idea, or no project left, finds nothing."""
    if mode not in MODES:
        raise ValueError(f"unknown mode of search: {mode}")
    if not idea.strip() or (only is not None and not only):
        return []
    store = EmbeddingStore(conninfo)
    meaning = (
        by_meaning(store, client, idea, model=model, limit=limit, now=now, only=only)
        if mode != WORDS and store.counts(model)["embeddings"]
        else []
    )
    words = by_words(conninfo, idea, limit=limit, only=only) if mode != MEANING else []
    return merge(meaning, words)[:limit]
