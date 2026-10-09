"""The Gemini layers and the embedding model, through the real library with a fake network.

These tests pin what Google's pages and the library's source said on 9 October 2026. If the library changes its requests, a test here goes red instead of a live call failing
silently.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from googlefake import PAGE_CANARY, FakeGoogle, answer, valid_form
from hackathon_memory.llm import embeddings
from hackathon_memory.llm.card_form import CardFields, Category, Label
from hackathon_memory.llm.gemini import (
    LOCATIONS,
    PRICES,
    CardFormatError,
    Usage,
    check_location,
    fill_card,
)

PAGE = f"{PAGE_CANARY} lets a shop keep a public list of small facts on Hedera."
PRO = "gemini-3.1-pro-preview"
FLASH = "gemini-3.8-flash"


# ------------------------------------------------------------------ the request to Gemini


@pytest.mark.parametrize(
    ("model", "level"),
    [(PRO, "HIGH"), (FLASH, "HIGH"), (FLASH, "LOW"), (PRO, "MEDIUM")],
)
def test_the_request_is_what_googles_pages_ask_for(model: str, level: str) -> None:
    google = FakeGoogle(answer())
    fill_card(google.client(), PAGE, model=model, thinking_level=level)

    path, body = google.requests[0]
    assert path.endswith(f"/publishers/google/models/{model}:generateContent")
    assert "/locations/global/" in path

    config = body["generationConfig"]
    for ignored in ("temperature", "topP", "topK", "top_p", "top_k"):
        assert ignored not in config  # Google: ignored by the backend, remove them
    thinking = config["thinkingConfig"]
    assert (thinking.get("thinking_level") or thinking.get("thinkingLevel")) == level
    # The old budget must never be sent with a level: Google answers with an error.
    assert not any("budget" in key.lower() for key in thinking)
    assert config["responseMimeType"] == "application/json"
    assert config["maxOutputTokens"] == 16384
    assert sorted(config["responseSchema"]["properties"]) == sorted(CardFields.model_fields)

    instructions = json.dumps(body["systemInstruction"])
    assert "Use only what the page says" in instructions
    assert "Do not score the project" in instructions  # design 3.3
    assert PAGE_CANARY in json.dumps(body["contents"])


def test_a_thinking_level_that_google_refuses_is_never_sent() -> None:
    google = FakeGoogle(answer())
    for level in ("MINIMAL", "", "high", "EXTREME"):
        with pytest.raises(CardFormatError, match="thinking level"):
            fill_card(google.client(), PAGE, model=PRO, thinking_level=level)
    assert google.requests == []


def test_the_form_has_the_seven_fields_of_the_design() -> None:
    assert list(CardFields.model_fields) == [
        "what_it_does",
        "how_it_works",
        "for_whom",
        "hedera_services",
        "category",
        "problem",
        "solution",
    ]
    assert len(Category) == 16  # the list of design 4.5


# ------------------------------------------------------------------ the answer


def test_a_valid_answer_becomes_a_card_with_its_cost() -> None:
    google = FakeGoogle(answer())
    result = fill_card(google.client(), PAGE, model=FLASH, thinking_level="LOW")

    assert result.model == FLASH
    assert result.thinking_level == "LOW"
    assert result.instructions_version == "card-form-0"
    assert result.fields.what_it_does.label is Label.STATED
    assert result.fields.category.category is Category.PAYMENTS
    assert result.fields.problem.label is Label.NOT_FOUND
    assert result.usage == Usage(1000, 200, 300, 1500)
    # 1000 tokens in at 0.75, and 200 + 300 thinking tokens out at 3.75, per million
    assert result.cost_usd == pytest.approx(0.002625)


def test_the_cost_depends_on_the_model() -> None:
    usage = Usage(1000, 200, 300, 1500)
    assert usage.cost_usd(FLASH) == pytest.approx(0.002625)
    assert usage.cost_usd(PRO) == pytest.approx(0.008)  # 1000 x 2.00 + 500 x 12.00, per million
    assert usage.cost_usd("gemini-9-unknown") is None  # an unknown price is never guessed


def test_the_prices_are_the_ones_read_on_9_october_2026() -> None:
    assert PRICES[FLASH] == (0.75, 3.75)  # until 31 December 2026
    assert PRICES[PRO] == (2.00, 12.00)  # prompts up to 200,000 tokens


@pytest.mark.parametrize(
    "bad",
    [
        {"what_it_does": {"label": "maybe", "text": "x", "quotes": []}},
        {"category": {"label": "stated", "category": "Pizza", "quotes": []}},
        {"how_it_works": {"label": "stated", "steps": ["a"] * 7, "quotes": []}},
        {"problem": {"label": "not_found", "text": "I made this up", "quotes": []}},
        {"solution": {"label": "not_found", "text": "", "quotes": ["a quote"]}},
    ],
)
def test_an_answer_that_breaks_the_form_is_refused(bad: dict) -> None:
    with pytest.raises(CardFormatError, match="not a valid form"):
        fill_card(FakeGoogle(answer(**bad)).client(), PAGE, model=PRO, thinking_level="HIGH")


def test_a_missing_field_is_refused() -> None:
    form = valid_form()
    del form["for_whom"]
    with pytest.raises(CardFormatError, match="for_whom"):
        fill_card(FakeGoogle(json.dumps(form)).client(), PAGE, model=PRO, thinking_level="HIGH")


def test_text_that_is_not_json_is_refused() -> None:
    with pytest.raises(CardFormatError, match="not JSON"):
        fill_card(
            FakeGoogle("Sorry, I cannot do that.").client(), PAGE, model=PRO, thinking_level="HIGH"
        )


def test_the_error_never_repeats_the_page_or_the_answer() -> None:
    leak = f"{PAGE_CANARY} SECRET-ANSWER-TEXT"
    bad = answer(what_it_does={"label": "maybe", "text": leak, "quotes": [leak]})
    with pytest.raises(CardFormatError) as failure:
        fill_card(FakeGoogle(bad).client(), PAGE, model=PRO, thinking_level="HIGH")
    assert "SECRET-ANSWER-TEXT" not in str(failure.value)
    assert PAGE_CANARY not in str(failure.value)


def test_an_answer_with_no_text_is_refused_with_the_reason() -> None:
    google = FakeGoogle("")
    google.finish_reason = "SAFETY"
    with pytest.raises(CardFormatError, match="SAFETY"):
        fill_card(google.client(), PAGE, model=PRO, thinking_level="HIGH")


def test_an_empty_page_is_refused_before_any_request() -> None:
    google = FakeGoogle(answer())
    with pytest.raises(CardFormatError, match="empty"):
        fill_card(google.client(), "   ", model=PRO, thinking_level="HIGH")
    assert google.requests == []


def test_a_field_with_the_label_not_found_must_be_empty() -> None:
    bad = valid_form(problem={"label": "not_found", "text": "x", "quotes": []})
    with pytest.raises(ValidationError):
        CardFields.model_validate(bad)


# ------------------------------------------------------------------ the locations


def test_gemini_3_1_pro_is_offered_only_in_global() -> None:
    assert LOCATIONS[PRO] == ("global",)
    check_location(PRO, "global")
    for other in ("us", "eu", "us-central1"):
        with pytest.raises(CardFormatError, match="global"):
            check_location(PRO, other)


def test_gemini_3_8_flash_is_offered_in_global_us_and_eu() -> None:
    for location in ("global", "us", "eu"):
        check_location(FLASH, location)
    with pytest.raises(CardFormatError, match="global"):
        check_location(FLASH, "us-central1")


def test_a_model_that_is_not_in_the_table_is_not_checked() -> None:
    check_location("gemini-9-future", "anywhere")  # the first call shows if the place is wrong


# ------------------------------------------------------------------ the embedding model


def test_the_embedding_request_is_what_googles_pages_ask_for() -> None:
    google = FakeGoogle()
    client = google.client()
    embeddings.embed_documents(client, ["first text", "second text", "third text"])
    embeddings.embed_query(client, "a question")

    path, body = google.requests[0]
    assert path.endswith("/publishers/google/models/gemini-embedding-001:predict")
    assert [i["task_type"] for i in body["instances"]] == ["RETRIEVAL_DOCUMENT"] * 3
    assert [i["content"] for i in body["instances"]] == ["first text", "second text", "third text"]
    assert body["parameters"]["outputDimensionality"] == 3072

    _, query_body = google.requests[1]
    assert [i["task_type"] for i in query_body["instances"]] == ["RETRIEVAL_QUERY"]


def test_an_embedding_has_3072_numbers_and_says_if_the_text_was_cut() -> None:
    google = FakeGoogle()
    google.truncated = True
    [one] = embeddings.embed_documents(google.client(), ["a long text"])
    assert len(one.values) == 3072
    assert one.token_count == 7
    assert one.truncated is True


def test_a_vector_of_the_wrong_size_is_refused() -> None:
    google = FakeGoogle()
    google.embedding_size = 768
    with pytest.raises(embeddings.EmbeddingError, match="Expected 3072"):
        embeddings.embed_documents(google.client(), ["text"])


def test_the_wrong_number_of_vectors_is_refused() -> None:
    google = FakeGoogle()
    google.embedding_count = 1
    with pytest.raises(embeddings.EmbeddingError, match="Asked for 2"):
        embeddings.embed_documents(google.client(), ["one", "two"])


def test_a_request_that_breaks_the_limits_is_never_sent() -> None:
    google = FakeGoogle()
    client = google.client()
    with pytest.raises(embeddings.EmbeddingError, match="250"):
        embeddings.embed_documents(client, ["x"] * 251)
    with pytest.raises(embeddings.EmbeddingError, match="no text"):
        embeddings.embed_documents(client, [])
    with pytest.raises(embeddings.EmbeddingError, match="empty"):
        embeddings.embed_documents(client, ["fine", "  "])
    assert google.requests == []


def test_cosine_similarity() -> None:
    assert embeddings.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert embeddings.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert embeddings.cosine_similarity([1.0, 1.0], [-1.0, -1.0]) == pytest.approx(-1.0)


# ------------------------------------------------------------------ bad answers are asked for again


def generate_calls(google: FakeGoogle) -> int:
    return sum(path.endswith(":generateContent") for path, _ in google.requests)


def test_an_answer_that_is_not_json_is_asked_for_again() -> None:
    # The first live run saw this: the same call returned text that was not valid JSON.
    google = FakeGoogle(answer())
    google.answer_queue = ['{"what_it_does": {"label": "stated", "text": "cut off']
    result = fill_card(google.client(), PAGE, model=FLASH, thinking_level="HIGH")
    assert result.attempts == 2
    assert generate_calls(google) == 2
    # Both attempts are billed, so the usage counts both: 2 x (1000 in, 200 out, 300 thoughts).
    assert result.usage == Usage(2000, 400, 600, 3000)
    assert result.cost_usd == pytest.approx(2 * 0.002625)


def test_an_answer_that_breaks_the_form_is_also_asked_for_again() -> None:
    google = FakeGoogle(answer())
    google.answer_queue = [answer(category={"label": "stated", "category": "Pizza", "quotes": []})]
    result = fill_card(google.client(), PAGE, model=PRO, thinking_level="HIGH")
    assert result.attempts == 2


def test_three_bad_answers_in_a_row_are_an_error_that_counts_the_cost() -> None:
    google = FakeGoogle("not json")
    with pytest.raises(CardFormatError, match=r"No valid form after 3 attempt\(s\)") as failure:
        fill_card(google.client(), PAGE, model=FLASH, thinking_level="HIGH")
    assert generate_calls(google) == 3
    assert failure.value.attempts == 3
    assert failure.value.usage == Usage(3000, 600, 900, 4500)  # money was spent on all three


def test_the_number_of_attempts_can_be_set() -> None:
    google = FakeGoogle("not json")
    with pytest.raises(CardFormatError):
        fill_card(google.client(), PAGE, model=FLASH, thinking_level="LOW", attempts=1)
    assert generate_calls(google) == 1


def test_a_stop_for_a_safety_reason_is_not_asked_for_again() -> None:
    google = FakeGoogle("")
    google.finish_reason = "SAFETY"
    with pytest.raises(CardFormatError, match="SAFETY") as failure:
        fill_card(google.client(), PAGE, model=PRO, thinking_level="HIGH")
    assert generate_calls(google) == 1  # it would stop again
    assert failure.value.attempts == 1


def test_the_error_says_how_the_json_failed_and_never_what_it_said() -> None:
    cut = '{"what_it_does": {"label": "stated", "text": "' + PAGE_CANARY + " cut off"
    google = FakeGoogle(cut)
    with pytest.raises(CardFormatError) as failure:
        fill_card(google.client(), PAGE, model=FLASH, thinking_level="HIGH", attempts=1)
    message = str(failure.value)
    assert "not JSON" in message
    assert "finish reason STOP" in message
    assert "at character" in message
    assert PAGE_CANARY not in message  # nothing of the answer
