"""The step that makes the embedding of every project for the search (design 8.1).

What is embedded for now is the page as it is: the name of the project as the title, then its
short line and its two texts, with the words about people already hidden by the parser. The
fields of the card come later and will be compared with it (design 13.3).

Every call goes through the meter, with its budget (design 11.4). A project whose text and model
are the same as at its last embedding is passed over, so the step is safe to run again and
pays only for what changed.
"""

from __future__ import annotations

from typing import Any

from google.genai import errors as google_errors

from hackathon_memory.db.embeddings import EmbeddingStore
from hackathon_memory.db.runs import Run
from hackathon_memory.llm.embeddings import EmbeddingError, embed_documents

STEP = "embed"
# Google errors in a row (after the client's own retries) that stop the step: Google is away.
MAX_ERRORS_IN_A_ROW = 3


class GoogleIsAway(Exception):
    """The embedding model failed several times in a row. Nothing more is asked."""


def embed_pages(
    store: EmbeddingStore,
    client: Any,
    run: Run,
    *,
    model: str,
    limit: int | None = None,
) -> None:
    """Make the embedding of every project whose text changed, and count what was done."""
    known = store.known(model)
    made = errors_in_a_row = 0
    for page in store.page_texts():
        run.counts["projects"] += 1
        if not page.text.strip():
            run.counts["projects_with_no_text"] += 1
            continue
        if known.get(page.project_id) == page.sha256:
            run.counts["the_same_as_before"] += 1
            continue
        if limit is not None and made >= limit:
            run.counts["left_for_later"] += 1
            continue
        try:
            [embedding] = embed_documents(client, [page.text], model=model, titles=[page.title])
        except (EmbeddingError, google_errors.APIError) as error:
            # The kind of the error only: its text could hold a piece of the page.
            run.problem(f"project {page.project_id}", type(error).__name__)
            errors_in_a_row += 1
            if errors_in_a_row >= MAX_ERRORS_IN_A_ROW:
                raise GoogleIsAway(
                    f"the embedding model failed {errors_in_a_row} times in a row"
                ) from None
            continue
        errors_in_a_row = 0
        store.save(page.project_id, model, page.sha256, embedding)
        made += 1
        run.counts["made"] += 1
        run.counts["tokens"] += embedding.token_count or 0
        if embedding.truncated:
            run.counts["texts_cut_by_the_model"] += 1


def embed_lines(run: Run) -> list[str]:
    """What a run of the step did, in plain words."""
    counts = run.counts
    lines = [
        f"Projects: {counts['projects']}. Embeddings made: {counts['made']} "
        f"({counts['tokens']} tokens). The same as before: {counts['the_same_as_before']}. "
        f"With no text: {counts['projects_with_no_text']}."
    ]
    if counts["left_for_later"]:
        lines.append(f"Left for a later run, because of the limit: {counts['left_for_later']}.")
    if counts["texts_cut_by_the_model"]:
        lines.append(
            "Texts longer than the model reads, whose end was cut: "
            f"{counts['texts_cut_by_the_model']}."
        )
    return lines
