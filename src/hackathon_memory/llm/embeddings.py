"""The embedding models (design 8.1, 11.3; design rule 7).

Two of Google's embedding models are known here.

`gemini-embedding-001`, the model of the first proof. From Google's embeddings page and task types
page, read on 9 October 2026:

* It gives 3,072 numbers by default. Each text is cut at 2,048 tokens, silently. One request
  takes up to 250 texts and 20,000 tokens.
* Texts that are stored are embedded with the task type RETRIEVAL_DOCUMENT, and a question with
  RETRIEVAL_QUERY.
* The library sends this model to the batch route (`predict`), so a list of texts is allowed.
* Google's price page does not list it, so its cost is not known here.

`gemini-embedding-2`, the model of the search. From Google's embeddings page of the Gemini API
and its model page on Vertex AI, read on 11 October 2026, and from the installed library
google-genai 2.29.0 (models.py, `embed_content`; _transformers.py,
`t_is_vertex_embed_content_model`):

* It is generally available on Vertex AI since 22 April 2026, also in the region "global".
* It reads 8,192 tokens of a text and silently cuts the rest. It gives 3,072 numbers by default.
* It takes no task type. A prefix in the text says what the text is: "title: {title} | text:
  {content}" for a document ("title: none" when it has no title), and "task: search result |
  query: {content}" for a question that searches the documents.
* On Vertex AI the library sends it to `embedContent`, one text per request, and refuses more.
* It costs 0.20 dollars for a million tokens (the price book).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from google import genai
from google.genai import types

from hackathon_memory.llm.client import again_if_dropped

MODEL = "gemini-embedding-001"  # the default, for the first proof
SEARCH_MODEL = "gemini-embedding-2"  # the default of the setting GEMINI_EMBEDDING_MODEL
DIMENSIONS = 3072
MAX_TEXTS_PER_REQUEST = 250  # gemini-embedding-001
DOCUMENT = "RETRIEVAL_DOCUMENT"
QUERY = "RETRIEVAL_QUERY"
NO_TITLE = "none"


class EmbeddingError(Exception):
    """The request or the answer is not what the embedding model promises."""


@dataclass(frozen=True)
class Embedding:
    values: list[float]
    token_count: int | None
    truncated: bool | None  # True when the text was longer than the model reads and was cut


def takes_a_prefix(model: str) -> bool:
    """True for the models that read a prefix in the text in place of a task type."""
    return model.startswith("gemini-embedding-2")


def document_text(text: str, title: str | None = None) -> str:
    """A document as gemini-embedding-2 wants it: "title: ... | text: ..."."""
    return f"title: {(title or '').strip() or NO_TITLE} | text: {text}"


def query_text(text: str) -> str:
    """A question that searches documents, as gemini-embedding-2 wants it."""
    return f"task: search result | query: {text}"


def embed(
    client: genai.Client,
    texts: list[str],
    task_type: str,
    *,
    model: str = MODEL,
    titles: list[str | None] | None = None,
) -> list[Embedding]:
    """One embedding for each text. `task_type` is DOCUMENT or QUERY. `titles` go with the
    documents of a model that takes a prefix."""
    if not texts:
        raise EmbeddingError("There is no text to embed.")
    if any(not t.strip() for t in texts):
        raise EmbeddingError("A text is empty.")
    if task_type not in (DOCUMENT, QUERY):
        raise EmbeddingError(f"The task is {DOCUMENT} or {QUERY}.")
    if titles is not None and len(titles) != len(texts):
        raise EmbeddingError("Give one title for each text, or none.")
    if takes_a_prefix(model):
        names = titles or [None] * len(texts)
        return [
            _one(
                client,
                model,
                document_text(text, title) if task_type == DOCUMENT else query_text(text),
            )
            for text, title in zip(texts, names, strict=True)
        ]
    if len(texts) > MAX_TEXTS_PER_REQUEST:
        raise EmbeddingError(f"One request takes {MAX_TEXTS_PER_REQUEST} texts at most.")
    response = again_if_dropped(
        lambda: client.models.embed_content(
            model=model,
            contents=texts,
            config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=DIMENSIONS),
        )
    )
    return _read(response, len(texts))


def _one(client: genai.Client, model: str, text: str) -> Embedding:
    response = again_if_dropped(
        lambda: client.models.embed_content(
            model=model,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=DIMENSIONS),
        )
    )
    return _read(response, 1)[0]


def _read(response: types.EmbedContentResponse, asked: int) -> list[Embedding]:
    answers = response.embeddings or []
    if len(answers) != asked:
        raise EmbeddingError(f"Asked for {asked} embeddings, got {len(answers)}.")
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


def embed_documents(
    client: genai.Client,
    texts: list[str],
    *,
    model: str = MODEL,
    titles: list[str | None] | None = None,
) -> list[Embedding]:
    return embed(client, texts, DOCUMENT, model=model, titles=titles)


def embed_query(client: genai.Client, text: str, *, model: str = MODEL) -> Embedding:
    return embed(client, [text], QUERY, model=model)[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))
