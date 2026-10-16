"""The search model puts a list of projects in order of closeness to an idea.

It reads the idea and a numbered list of projects, one line each: the name, the short line or the
start of the first text, and the start of the first text. It answers with the numbers of the 10
projects whose idea is closest, the closest first. It never scores a project or judges its quality
(design rule 1), and its order is not a fact about a project (design rule 2). These are the words
and the lines that the measure of the modes used (evals/search_modes.py).
"""

from __future__ import annotations

from typing import Any

import psycopg
from google.genai import types
from pydantic import BaseModel

from hackathon_memory.llm.client import again_if_dropped

MAX_OUTPUT_TOKENS = 2048
INSTRUCTIONS = """\
You help a builder find past hackathon projects that are close to their idea.

You get the idea and a numbered list of projects. Give the numbers of the 10 projects whose idea \
is closest to the builder's idea, the closest first. Close means the same problem, or the same \
kind of solution for the same people. Use only the texts given.

Do not judge how good a project is. Give only numbers from the list."""


class Closest(BaseModel):
    closest: list[int]


def texts_of(conninfo: str) -> dict[int, tuple[str, str, str]]:
    """The name, the short line and the first text of every project."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT p.id, p.name, coalesce(p.short_line, ''), coalesce((SELECT s.body FROM "
            "sections s WHERE s.project_id = p.id ORDER BY s.position LIMIT 1), '') "
            "FROM projects p ORDER BY p.id"
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


def ask_closest(client: Any, model: str, level: str, idea: str, lines: list[str]) -> list[int]:
    """The numbers the model gives, in its order, kept only when they are in the list."""
    config = types.GenerateContentConfig(
        system_instruction=INSTRUCTIONS,
        response_mime_type="application/json",
        response_schema=Closest,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel[level]),
        max_output_tokens=MAX_OUTPUT_TOKENS,
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
          with_text: bool) -> list[int]:  # fmt: skip
    lines = [line(i, texts[pid], letters, with_text) for i, pid in enumerate(pool, start=1)]
    return [pool[n - 1] for n in ask_closest(client, model, level, idea, lines)]
