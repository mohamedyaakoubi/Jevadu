"""Gate A, proof 3: one call to Gemini 3.8 Flash returns a valid form for one real text, and one
embedding call returns a list of the expected size.

    python -m proofs.google_models

It needs GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION in .env, and a sign-in (design 15,
step 3). Use the location `global`: it is one of the three that Google lists for this model.

The real text is the longest description of the winners of Hedera x AI that the maintainer copied by
hand into data/by-hand/hol.org/. It is real text, but it is short (58 to 81 words) and it is not a
full project page. The proof says so. Nothing of that text, and nothing that the model answers,
is printed or saved: the result file holds counts, labels and prices only (design rule 18).

What it checks:

1. The answer of Gemini is a valid form (design 4.1, 4.3, 4.5). The form is checked by our
   own model of it, not by the library.
2. Three embedding calls: the text as a document, a question about it, and an unrelated question.
   Each answer has 3,072 numbers, and the related question is closer to the text than the
   unrelated one. This shows that both modes (document and question) work.
3. What the calls cost, from the token counts.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from google import genai

from hackathon_memory.llm import embeddings, gemini
from hackathon_memory.llm.client import GoogleSetupError, make_client
from hackathon_memory.settings import Settings
from proofs.result import ProofResult

UNRELATED_QUESTION = "chocolate cake recipe with eggs and sugar"
# Dollars per million tokens for the embedding model are not known, so the cost
# of the embedding calls is reported as tokens only.


@dataclass(frozen=True)
class RealText:
    name: str
    text: str


def load_real_text(settings: Settings) -> RealText | None:
    """The longest published description among the hand-copied winners of Hedera x AI."""
    path = Path(settings.data_dir) / "by-hand" / "hol.org" / "hedera-x-ai-2025-winners.entries.json"
    if not path.exists():
        return None
    entries = json.loads(path.read_text(encoding="utf-8"))
    best = max(entries, key=lambda e: len(e["description_as_published"]))
    return RealText(name=best["name"], text=best["description_as_published"])


def _normal(text: str) -> str:
    """Spaces and letter case made uniform, as the quote check of design 6.3 does."""
    return re.sub(r"\s+", " ", text).strip().lower()


def run(
    settings: Settings | None = None,
    make: Callable[[Settings], genai.Client] = make_client,
    text_source: Callable[[Settings], RealText | None] = load_real_text,
) -> int:
    settings = settings or Settings()
    project = settings.google_cloud_project.get_secret_value().strip()
    location = settings.google_cloud_location.strip()
    if not project or not location:
        print(
            "Blocked: GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are empty in .env.\n"
            "Make the Vertex AI project ready (design 15, step 3), sign in with\n"
            "  gcloud auth application-default login\n"
            "and set GOOGLE_CLOUD_LOCATION=global. Never paste values into a chat."
        )
        return 3

    result = ProofResult(proof="google-models")
    result.hide(project, settings.google_application_credentials.get_secret_value())
    result.does_not_prove = [
        "The text is short (58 to 81 words) and it is not a full project page. How well the form "
        "is filled for full pages is measured by Test 1 (design 13.2), not here.",
        "It does not show that the quotes are right. The check of the quotes is Phase D "
        "(design 6.3). The count of quotes found in the text is only an observation.",
        "One call per model. The speed and the cost of a full run are not shown.",
        "The price of the embedding model was not read from Google, so only "
        "its token count is reported.",
    ]

    try:
        gemini.check_location(location)
    except gemini.CardFormatError as error:
        result.check("the location is one that Gemini 3.8 Flash is offered in", False, str(error))
        return result.finish()
    result.check("the location is one that Gemini 3.8 Flash is offered in", True, location)

    real = text_source(settings)
    result.check(
        "a real text is available (the hand-copied winners of Hedera x AI)",
        real is not None,
        "" if real else "data/by-hand/hol.org/hedera-x-ai-2025-winners.entries.json is missing",
    )
    if real is None:
        return result.finish()
    result.hide(real.text)
    result.measurements["text_words"] = len(real.text.split())

    try:
        client = make(settings)
    except GoogleSetupError as error:
        result.check("the Google client can be made", False, str(error))
        return result.finish()
    result.check("the Google client can be made", True)

    # --- 1. the form
    try:
        started = time.monotonic()
        card = gemini.fill_card(client, real.text)
        result.measurements["gemini_seconds"] = round(time.monotonic() - started, 1)
    except gemini.CardFormatError as error:
        result.check("Gemini 3.8 Flash returned a valid form", False, str(error))
        card = None
    except Exception as error:  # noqa: BLE001  (a refusal or a quota problem is a result too)
        result.check(
            "Gemini 3.8 Flash returned a valid form", False, f"{type(error).__name__}: {error}"
        )
        card = None
    if card is not None:
        result.check("Gemini 3.8 Flash returned a valid form", True, f"model {card.model}")
        usage = card.usage
        result.measurements.update(
            {
                "model": card.model,
                "instructions_version": card.instructions_version,
                "location": location,
                "prompt_tokens": usage.prompt_tokens,
                "output_tokens": usage.output_tokens,
                "thought_tokens": usage.thought_tokens,
                "gemini_cost_usd": round(usage.cost_usd, 6),
            }
        )
        labels = Counter(
            f.label.value
            for f in (
                card.fields.what_it_does,
                card.fields.how_it_works,
                card.fields.for_whom,
                card.fields.hedera_services,
                card.fields.category,
                card.fields.problem,
                card.fields.solution,
            )
        )
        result.measurements["labels"] = dict(labels)
        page = _normal(real.text)
        quotes = card.fields.all_quotes()
        result.measurements["quotes_total"] = len(quotes)
        result.measurements["quotes_found_in_text"] = sum(_normal(q) in page for q in quotes)

    # --- 2. the embeddings
    try:
        [document] = embeddings.embed_documents(client, [real.text])
        related = embeddings.embed_query(client, f"{real.name} on Hedera")
        unrelated = embeddings.embed_query(client, UNRELATED_QUESTION)
    except embeddings.EmbeddingError as error:
        result.check("the embedding model returned vectors of the expected size", False, str(error))
        return result.finish()
    except Exception as error:  # noqa: BLE001
        result.check(
            "the embedding model returned vectors of the expected size",
            False,
            f"{type(error).__name__}: {error}",
        )
        return result.finish()
    result.check(
        "the embedding model returned vectors of the expected size",
        all(len(e.values) == embeddings.DIMENSIONS for e in (document, related, unrelated)),
        f"3 vectors of {len(document.values)} numbers",
    )
    close = embeddings.cosine_similarity(document.values, related.values)
    far = embeddings.cosine_similarity(document.values, unrelated.values)
    result.check(
        "a question about the text is closer to it than an unrelated question",
        close > far,
        f"similarity {close:.3f} against {far:.3f}",
    )
    result.measurements.update(
        {
            "embedding_model": embeddings.MODEL,
            "embedding_dimensions": len(document.values),
            "similarity_related": round(close, 4),
            "similarity_unrelated": round(far, 4),
            "document_tokens": document.token_count,
            "document_truncated": document.truncated,
        }
    )
    return result.finish()


if __name__ == "__main__":
    sys.exit(run())
