"""The summary of the cards of a set, in numbers only. Every card here is invented."""

from __future__ import annotations

import json
from pathlib import Path

from evals.cards_report import counts_of, summary, write


def field(label: str, value: object, state: str = "kept") -> dict:
    return {"label": label, "value": value, "quotes": [], "removed": 0, "state": state, "why": ""}


def card(words: str, category: str | None) -> dict:
    return {
        "what_it_does": field("stated", words),
        "how_it_works": field("inferred", ["One.", "Two.", "Three."]),
        "category": field("inferred", category, "kept" if category else "dropped"),
        "problem": field("not_found", "", "not_found"),
    }


def test_the_summary_counts_labels_lengths_steps_and_categories() -> None:
    rows = [
        (card("It pays a vendor.", "Payments and remittance"), 4, 4, 0, 0.04),
        (card("It logs every parcel when it moves today.", None), 4, 3, 1, 0.05),
    ]
    result = summary(rows, pages=3)
    assert (result["pages_of_the_set"], result["cards"]) == (3, 2)
    assert (result["quotes_given"], result["quotes_found"]) == (8, 7)
    assert result["fields"] == {"kept": 5, "dropped": 1, "not_found": 2}
    assert result["labels"]["what_it_does"] == {"stated": 2}
    assert result["words"]["what_it_does"] == {"middle": 6.0, "longest": 8}
    assert result["steps"] == {"3": 2}
    assert result["categories"] == {"Payments and remittance": 1, "(dropped)": 1}
    assert (result["cost_usd"], result["cost_usd_a_card"]) == (0.09, 0.045)


def test_a_result_file_is_dated_and_holds_no_text(tmp_path: Path) -> None:
    path = write(summary([(card("It pays.", "Health"), 1, 1, 0, 0.01)], pages=1), "tuning",
                 "card-form-9", tmp_path)  # fmt: skip
    assert path.name.endswith("-cards-tuning-card-form-9.json")
    text = path.read_text(encoding="utf-8")
    assert "It pays" not in text and json.loads(text)["cards"] == 1


def test_the_file_says_what_its_counts_are() -> None:
    assert counts_of("tuning").startswith("a run of the cards, for writing the instructions")
    assert counts_of("test1") == (
        "the cards of a test set, counted before any grading; not a test result"
    )
