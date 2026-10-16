"""The search model puts a list of projects in order of closeness to an idea.

It reads the idea and a numbered list of projects, one line each: the name, the short line or the
start of the first text, and the start of the first text. It answers with the numbers of the 10
projects whose idea is closest, the closest first. It never scores a project or judges its quality
(design rule 1), and its order is not a fact about a project (design rule 2). These are the words
and the lines that the measure of the modes used (evals/search_modes.py).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx
import psycopg
from google.genai import errors as google_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from hackathon_memory.db.embeddings import EmbeddingStore
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.llm.client import again_if_dropped
from hackathon_memory.search import engine

MAX_OUTPUT_TOKENS = 2048
POOL = 30  # the closest by meaning that the model puts in order
TEXT_LETTERS = 300  # of the short line and of the first text, in each line the model reads
# The model's answer is not used when it fails, is not valid, is late, or the budget is spent.
NOT_ORDERED = (google_errors.APIError, httpx.TransportError, ValidationError, BudgetExceeded)
INSTRUCTIONS = """\
You help a builder find past hackathon projects that are close to their idea.

You get the idea and a numbered list of projects. Give the numbers of the 10 projects whose idea \
is closest to the builder's idea, the closest first. Close means the same problem, or the same \
kind of solution for the same people. Use only the texts given.

Do not judge how good a project is. Give only numbers from the list."""


class Closest(BaseModel):
    closest: list[int]


def texts_of(conninfo: str, ids: Sequence[int] | None = None) -> dict[int, tuple[str, str, str]]:
    """The name, the short line and the first text of every project, or of the projects of
    `ids`."""
    wanted = None if ids is None else list(ids)
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT p.id, p.name, coalesce(p.short_line, ''), coalesce((SELECT s.body FROM "
            "sections s WHERE s.project_id = p.id ORDER BY s.position LIMIT 1), '') "
            "FROM projects p WHERE %s::bigint[] IS NULL OR p.id = ANY(%s) ORDER BY p.id",
            (wanted, wanted),
        ).fetchall()
    return {row[0]: (row[1], row[2].strip(), row[3].strip()) for row in rows}


def line(number: int, texts: tuple[str, str, str], letters: int, with_text: bool) -> str:
    """One numbered line: the name, then the short line (or the start of the first text), and
    with `with_text` also the start of the first text."""
    name, short_line, first_text = texts
    words = " ".join((short_line or first_text).split())[:letters].rstrip()
    if with_text and short_line and first_text:
        words += " " + " ".join(first_text.split())[:letters].rstrip()
    return f"{number}. {name}: {words}"


def ask_closest(
    client: Any,
    model: str,
    level: str,
    idea: str,
    lines: list[str],
    timeout_seconds: float | None = None,
) -> list[int]:
    """The numbers the model gives, in its order, kept only when they are in the list. With
    `timeout_seconds`, the call is made once and given up after that time."""
    config = types.GenerateContentConfig(
        system_instruction=INSTRUCTIONS,
        response_mime_type="application/json",
        response_schema=Closest,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel[level]),
        max_output_tokens=MAX_OUTPUT_TOKENS,
        http_options=None
        if timeout_seconds is None
        else types.HttpOptions(
            timeout=int(timeout_seconds * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    contents = f"Idea: {idea}\n\nProjects:\n" + "\n".join(lines)
    response = again_if_dropped(
        lambda: client.models.generate_content(model=model, contents=contents, config=config)
    )
    numbers = Closest.model_validate_json(response.text or "").closest
    allowed = range(1, len(lines) + 1)
    return list(dict.fromkeys(n for n in numbers if n in allowed))


def by_ai(client: Any, model: str, level: str, idea: str, pool: list[int],
          texts: dict[int, tuple[str, str, str]], *, letters: int,
          with_text: bool, timeout_seconds: float | None = None) -> list[int]:  # fmt: skip
    lines = [line(i, texts[pid], letters, with_text) for i, pid in enumerate(pool, start=1)]
    numbers = ask_closest(client, model, level, idea, lines, timeout_seconds)
    return [pool[n - 1] for n in numbers]


def closest_by_ai(
    conninfo: str,
    google: Any,
    llm: Any,
    idea: str,
    *,
    embedding_model: str,
    model: str,
    level: str,
    limit: int = 10,
    only: Sequence[int] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[list[engine.Hit], bool]:
    """The projects closest to the idea: the 30 closest by meaning, put in order by the search
    model, the first `limit`; and whether the model's order was used. When the model fails or
    is late, the order is the order by meaning. With no embedding of the pages, only the words
    are searched. A failure of the embedding of the idea is raised, as by engine.search."""
    if not idea.strip() or (only is not None and not only):
        return [], False
    store = EmbeddingStore(conninfo)
    if not store.counts(embedding_model)["embeddings"]:
        words = engine.search(conninfo, google, idea, model=embedding_model, limit=limit,
                              only=only, mode=engine.WORDS)  # fmt: skip
        return words, False
    pool = engine.by_meaning(store, google, idea, model=embedding_model, limit=POOL, only=only)
    try:
        ordered = by_ai(llm, model, level, idea, pool, texts_of(conninfo, pool),
                        letters=TEXT_LETTERS, with_text=True,
                        timeout_seconds=timeout_seconds)  # fmt: skip
    except NOT_ORDERED:
        return engine.merge(pool[:limit], []), False
    ordered += [pid for pid in pool if pid not in ordered]
    return engine.merge(ordered[:limit], []), True
