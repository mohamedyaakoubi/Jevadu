"""The embedding model (design 8.1, 11.3; design rule 7).

Facts from Google's embeddings page and task types page, read on 9 October 2026:

* `gemini-embedding-001` gives 3,072 numbers by default. Each text is cut at 2,048 tokens, silently.
  One request takes up to 250 texts and 20,000 tokens.
* Texts that are stored are embedded with the task type RETRIEVAL_DOCUMENT, and a question with
  RETRIEVAL_QUERY. This is the "one mode for documents and one for questions" of the design.
* `gemini-embedding-2` exists, but it takes no task type and one text per request. Test 2
  (design 13.3) compares the models, so the choice here is the one the design names.
* The library sends this model to the batch route (`predict`), so a list of texts is allowed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from google import genai
from google.genai import types

MODEL = "gemini-embedding-001"
DIMENSIONS = 3072
MAX_TEXTS_PER_REQUEST = 250
DOCUMENT = "RETRIEVAL_DOCUMENT"
QUERY = "RETRIEVAL_QUERY"


class EmbeddingError(Exception):
    """The request or the answer is not what the embedding model promises."""


@dataclass(frozen=True)
class Embedding:
    values: list[float]
    token_count: int | None
    truncated: bool | None  # True when the text was longer than 2,048 tokens and was cut


def embed(client: genai.Client, texts: list[str], task_type: str) -> list[Embedding]:
    if not texts:
        raise EmbeddingError("There is no text to embed.")
    if len(texts) > MAX_TEXTS_PER_REQUEST:
        raise EmbeddingError(f"One request takes {MAX_TEXTS_PER_REQUEST} texts at most.")
    if any(not t.strip() for t in texts):
        raise EmbeddingError("A text is empty.")
    response = client.models.embed_content(
        model=MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=DIMENSIONS),
    )
    answers = response.embeddings or []
    if len(answers) != len(texts):
        raise EmbeddingError(f"Asked for {len(texts)} embeddings, got {len(answers)}.")
    result: list[Embedding] = []
    for answer in answers:
        values = list(answer.values or [])
        if len(values) != DIMENSIONS:
            raise EmbeddingError(f"Expected {DIMENSIONS} numbers, got {len(values)}.")
        stats = answer.statistics
        result.append(
            Embedding(
                values=values,
                token_count=int(stats.token_count) if stats and stats.token_count else None,
                truncated=stats.truncated if stats else None,
            )
        )
    return result


def embed_documents(client: genai.Client, texts: list[str]) -> list[Embedding]:
    return embed(client, texts, DOCUMENT)


def embed_query(client: genai.Client, text: str) -> Embedding:
    return embed(client, [text], QUERY)[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))
