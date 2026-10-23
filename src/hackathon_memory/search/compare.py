"""What is the same and what differs between an idea and its first results (design 8.3).

A fast model (the search model of the settings) reads the idea and, for each project, the texts
that its card shows: the fields of the model's card when the card keeps them, otherwise the
project's own short line and the start of its first text. For each project it writes one short
sentence on what is the same, one on what differs, and the names of the texts it used.

It never scores, ranks or judges a project, and never says that a project is a copy (design rule
1); facts stay with the tables (design rule 2). The list of results never waits for it: the page
asks for it after the results are shown, and the cards stay complete when it fails.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from google.genai import types
from pydantic import BaseModel, ValidationError

from hackathon_memory.db.embeddings import idea_fingerprint
from hackathon_memory.db.idea_answers import AnswerStore, KeptComparison
from hackathon_memory.llm.client import again_if_dropped
from hackathon_memory.read.quotes import KEPT

INSTRUCTIONS_VERSION = "compare-2"
FIRST_TEXT_LETTERS = 700  # of the page's first text, when the project has no card
MAX_OUTPUT_TOKENS = 8192
SYSTEM_INSTRUCTIONS = """\
You compare a builder's idea with past hackathon projects that a search found close to it.

For each project given, write:
- "same": one short sentence on what the project shares with the idea. Write "Nothing clear." \
when the texts show nothing in common.
- "differs": one short sentence on the main difference from the idea.
- "fields_used": the names of the texts of that project that you used.

Rules:
- Use only the texts given. Do not use what you know about the projects from elsewhere.
- The texts of a project are a short summary of its page, not the whole page. When they do not \
mention something, write that its texts do not say it; never write that the project does not do it.
- Do not score, rank or judge the projects, and do not say that a project is a copy of anything.
- Write for a reader whose first language is not English: common words, at most 20 words in a \
sentence.
- Give one answer for each project, with the number it has in the list.
"""
CARD_TEXTS = ("what_it_does", "how_it_works", "for_whom", "problem", "solution")


class ProjectComparison(BaseModel):
    number: int
    same: str
    differs: str
    fields_used: list[str]


class Comparison(BaseModel):
    projects: list[ProjectComparison]


class CompareError(Exception):
    """The model gave no usable comparison."""


@dataclass(frozen=True)
class Item:
    """One project as the model sees it: a number in the list, and its texts by name."""

    number: int
    project_id: int
    texts: dict[str, str]


def items_for(conninfo: str, project_ids: Sequence[int], *, model: str, version: str) -> list[Item]:
    """The texts of each project, in the order given: its card's fields when kept, otherwise its
    short line and the start of its first text."""
    with psycopg.connect(conninfo) as conn:
        rows = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT p.id, p.name, coalesce(p.short_line, ''), "
                "coalesce((SELECT s.body FROM sections s WHERE s.project_id = p.id "
                "ORDER BY s.position LIMIT 1), ''), c.fields "
                "FROM projects p LEFT JOIN cards c ON c.project_id = p.id AND c.model = %s "
                "AND c.instructions_version = %s WHERE p.id = ANY(%s)",
                (model, version, list(project_ids)),
            ).fetchall()
        }
    items = []
    for number, project_id in enumerate(project_ids, start=1):
        if project_id not in rows:
            continue
        name, short_line, first_text, fields = rows[project_id]
        texts = {"name": name}
        for key in CARD_TEXTS:
            field = (fields or {}).get(key) or {}
            if field.get("state") == KEPT and field.get("value"):
                value = field["value"]
                texts[key] = " ".join(value) if isinstance(value, list) else value
        if len(texts) == 1:  # no field of a card: the project's own words
            if short_line.strip():
                texts["short_line"] = short_line.strip()
            if first_text.strip():
                texts["page_text"] = first_text.strip()[:FIRST_TEXT_LETTERS]
        items.append(Item(number, project_id, texts))
    return items


def prompt(idea: str, items: Sequence[Item]) -> str:
    return json.dumps(
        {"idea": idea, "projects": [{"number": i.number, **i.texts} for i in items]},
        ensure_ascii=False,
        indent=1,
    )


def compare(
    client: Any,
    idea: str,
    items: Sequence[Item],
    *,
    model: str,
    thinking_level: str,
    timeout_seconds: float | None = None,
) -> dict[int, ProjectComparison]:
    """The comparison of each project, by project id. A project that the model leaves out, or
    answers with a number that is not in the list, has none.

    With `timeout_seconds`, the call is made once and given up after that time: a person waits
    for it (google-genai 2.29.0 lets the config of one call override the options of the client).
    """
    if not items:
        return {}
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        response_mime_type="application/json",
        response_schema=Comparison,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel[thinking_level]),
        max_output_tokens=MAX_OUTPUT_TOKENS,
        http_options=None
        if timeout_seconds is None
        else types.HttpOptions(
            timeout=int(timeout_seconds * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    text = prompt(idea, items)
    response = again_if_dropped(
        lambda: client.models.generate_content(model=model, contents=text, config=config)
    )
    try:
        answer = Comparison.model_validate_json(response.text or "")
    except ValidationError as error:
        raise CompareError("the model gave no valid comparison") from error
    by_number = {item.number: item for item in items}
    found: dict[int, ProjectComparison] = {}
    for one in answer.projects:
        item = by_number.get(one.number)
        if item is None or item.project_id in found:
            continue
        used = [name for name in one.fields_used if name in item.texts]
        found[item.project_id] = one.model_copy(update={"fields_used": used})
    return found


def input_fingerprint(item: Item) -> str:
    """The fingerprint of the texts of a project that the model reads, for the key of a kept
    comparison: when a card or a page changes, the old comparison is not used."""
    texts = json.dumps(item.texts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{INSTRUCTIONS_VERSION}\n{texts}".encode()).hexdigest()


def kept_or_compared(
    conninfo: str,
    client: Any,
    idea: str,
    items: Sequence[Item],
    *,
    model: str,
    thinking_level: str,
    timeout_seconds: float | None = None,
    now: datetime | None = None,
) -> tuple[dict[int, ProjectComparison], int]:
    """The comparison of each project: the one of the last day for the same idea and exactly the
    same texts when there is one, otherwise asked now, for those projects only, and kept for a
    day. Returns the comparisons by project id and how many projects the model was asked about.
    A failure of the model is raised, as by compare()."""
    store = AnswerStore(conninfo)
    store.forget_old(now)
    fingerprint = idea_fingerprint(idea)
    inputs = {item.project_id: input_fingerprint(item) for item in items}
    kept = store.comparisons(fingerprint, inputs, model, thinking_level, INSTRUCTIONS_VERSION, now)
    found = {
        item.project_id: ProjectComparison(number=item.number, same=kept[item.project_id].same,
                                           differs=kept[item.project_id].differs,
                                           fields_used=kept[item.project_id].fields_used)
        for item in items
        if item.project_id in kept
    }  # fmt: skip
    missing = [item for item in items if item.project_id not in kept]
    if missing:
        asked = compare(client, idea, missing, model=model, thinking_level=thinking_level,
                        timeout_seconds=timeout_seconds)  # fmt: skip
        store.save_comparisons(
            fingerprint,
            {pid: (inputs[pid], KeptComparison(one.same, one.differs, list(one.fields_used)))
             for pid, one in asked.items()},
            model, thinking_level, INSTRUCTIONS_VERSION, now,
        )  # fmt: skip
        found.update(asked)
    return found, len(missing)
