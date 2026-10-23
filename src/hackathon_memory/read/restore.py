"""The cards saved to a file, and put back into a database that was built again (design 6.5).

    python -m hackathon_memory.pipeline cards --export data/backups/<day>/cards.jsonl
    python -m hackathon_memory.pipeline cards --restore data/backups/<day>/cards.jsonl

A card costs a call to the model, and the model would not write the same card twice, so a database
built again from the saved pages takes its cards from such a file. A card comes back to the
project of the same page only when the text that the model read is the same, by its fingerprint.
The quote check runs again on that text, so the numbers of the card are made here, not copied.
No model is called. The file holds the model's answers with their quotes of the pages: it stays
in the data folder, outside git.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from hackathon_memory.db.cards import CardStore
from hackathon_memory.db.runs import Run
from hackathon_memory.llm.card_form import CardFields
from hackathon_memory.llm.gemini import CardResult, Usage
from hackathon_memory.read.quotes import check_card

_SAVED = (
    "SELECT p.page_url, c.model, c.instructions_version, c.thinking_level, c.input_sha256, "
    "c.answer, c.attempts, c.input_tokens, c.output_tokens, c.thinking_tokens, c.made_at "
    "FROM cards c JOIN projects p ON p.id = c.project_id "
    "ORDER BY c.model, c.instructions_version, p.page_url"
)


def export_cards(conninfo: str, path: Path) -> int:
    """Write every card with the address of its page, one line each. Returns how many."""
    with psycopg.connect(conninfo, row_factory=dict_row) as conn:
        rows = conn.execute(_SAVED).fetchall()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps({**row, "made_at": row["made_at"].isoformat()},
                                  ensure_ascii=False) + "\n")  # fmt: skip
    return len(rows)


def read_saved(path: Path) -> Iterator[dict]:
    """The cards of a file that export_cards wrote."""
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                yield json.loads(line)


def restore_cards(store: CardStore, rows: Iterable[dict], run: Run) -> None:
    """Put each card of the file back on the full card of its page, when its text is the same."""
    inputs = {card.page: card for card in store.inputs()}
    counts = run.counts
    for row in rows:
        counts["cards_in_the_file"] += 1
        card = inputs.get(row["page_url"])
        if card is None:
            counts["no_full_card_for_the_page"] += 1
            continue
        if card.sha256 != row["input_sha256"]:
            counts["text_not_the_same"] += 1
            run.problem(card.page, "the text of the card is not the one that the model read")
            continue
        fields = CardFields.model_validate(row["answer"])
        tokens = [row["input_tokens"] or 0, row["output_tokens"] or 0, row["thinking_tokens"] or 0]
        result = CardResult(fields, Usage(*tokens, sum(tokens)), row["model"],
                            row["thinking_level"], row["instructions_version"],
                            row["attempts"] or 1)  # fmt: skip
        checked = check_card(fields, card.text)
        store.save(card, result, checked, made_at=datetime.fromisoformat(row["made_at"]))
        counts["restored"] += 1
        counts["quotes_given"] += checked.quotes_given
        counts["quotes_found"] += checked.quotes_found
        counts["fields_dropped"] += len(checked.dropped())


def restore_lines(run: Run) -> list[str]:
    """What a restore did, in plain words."""
    counts = run.counts
    return [
        f"Cards in the file: {counts['cards_in_the_file']}. Put back: {counts['restored']}, "
        f"with {counts['quotes_found']} of {counts['quotes_given']} quotes found again and "
        f"{counts['fields_dropped']} fields dropped. No full card for the page: "
        f"{counts['no_full_card_for_the_page']}. Text not the same: "
        f"{counts['text_not_the_same']}. No model was called."
    ]
