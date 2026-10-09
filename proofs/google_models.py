"""Gate A, proof 3: the two Gemini layers return a valid form for one real text, and one embedding
call returns a list of the expected size.

    python -m proofs.google_models

It needs GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION in .env, and a sign-in (design 15,
step 3). Use the location `global`: Gemini 3.1 Pro is offered only there.

The two layers are the maintainer's decision of 9 October 2026 (design rule 7):

* REWRITE (GEMINI_REWRITE_MODEL, now Gemini 3.1 Pro) reads a project page and fills its card;
* SEARCH (GEMINI_SEARCH_MODEL, now Gemini 3.8 Flash) compares the closest projects with an idea.
  Its own form is built in Phase D. Here it is checked with the card form, which shows that the
  model, the location and the thinking level work through the same code.

The real text is the longest description of the winners of Hedera x AI that the maintainer copied by
hand into data/by-hand/hol.org/. It is real text, but it is short (58 to 81 words) and it is not a
full project page. The proof says so. Nothing of that text, and nothing that a model answers, is
printed or saved: the result file holds counts, labels, times and prices only (design rule 18).

What it checks:

1. For each layer, the answer is a valid form (design 4.1, 4.3, 4.5). The form is checked by
   our own model of it, not by the library.
2. Three embedding calls: the text as a document, a question about it, and an unrelated question.
   Each answer has 3,072 numbers, and the related question is closer to the text than the
   unrelated one. This shows that both modes (document and question) work.
3. What the calls cost, from the token counts and Google's prices.
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


def layers(settings: Settings) -> list[tuple[str, str, str]]:
    """(name of the layer, model, thinking level) for the two layers."""
    return [
        ("rewrite", settings.gemini_rewrite_model, settings.gemini_rewrite_thinking_level),
        ("search", settings.gemini_search_model, settings.gemini_search_thinking_level),
    ]


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
            "and set GOOGLE_CLOUD_LOCATION=global. Never paste values into a chat.\n"
            "The steps are in README.md."
        )
        return 3

    result = ProofResult(proof="google-models")
    result.hide(project, settings.google_application_credentials.get_secret_value())
    result.does_not_prove = [
        "The text is short (58 to 81 words) and it is not a full project page. How well the form "
        "is filled for full pages is measured by Test 1 (design 13.2), not here.",
        "It does not show that the quotes are right. The check of the quotes is Phase D "
        "(design 6.3). The count of quotes found in the text is only an observation.",
        "The search layer is checked with the card form only. Its own form, the comparison of "
        "projects, is built in Phase D.",
        "One call per model. The speed, the quota and the cost of a full run are not shown. "
        "Gemini 3.1 Pro is a public preview model: Google may change or retire it, and its quota "
        "may be lower than that of a generally available model.",
        "The price of the embedding model was not read from Google, so only "
        "its token count is reported.",
    ]

    plan = layers(settings)
    for _, model, _ in plan:
        try:
            gemini.check_location(model, location)
        except gemini.CardFormatError as error:
            result.check(f"the location is one that {model} is offered in", False, str(error))
            return result.finish()
        result.check(f"the location is one that {model} is offered in", True, location)

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

    # --- 1. the form, for each layer
    page = _normal(real.text)
    per_layer: dict[str, dict] = {}
    total_cost = 0.0
    cost_known = True
    for layer, model, level in plan:
        name = f"{layer}: {model} (thinking {level}) returned a valid form"
        try:
            started = time.monotonic()
            card = gemini.fill_card(client, real.text, model=model, thinking_level=level)
            seconds = round(time.monotonic() - started, 1)
        except gemini.CardFormatError as error:
            result.check(name, False, str(error))
            if error.usage is not None:  # a failed attempt is billed too
                cost = error.usage.cost_usd(model)
                per_layer[layer] = {
                    "model": model,
                    "thinking_level": level,
                    "failed_attempts": error.attempts,
                    "prompt_tokens": error.usage.prompt_tokens,
                    "output_tokens": error.usage.output_tokens,
                    "thought_tokens": error.usage.thought_tokens,
                    "cost_usd": None if cost is None else round(cost, 6),
                }
                if cost is None:
                    cost_known = False
                else:
                    total_cost += cost
            continue
        except Exception as error:  # noqa: BLE001  (a refusal or a quota problem is a result too)
            result.check(name, False, f"{type(error).__name__}: {error}")
            continue
        result.check(name, True, f"{seconds} seconds, {card.attempts} attempt(s)")
        usage = card.usage
        quotes = card.fields.all_quotes()
        cost = card.cost_usd
        if cost is None:
            cost_known = False
        else:
            total_cost += cost
        per_layer[layer] = {
            "model": model,
            "thinking_level": level,
            "instructions_version": card.instructions_version,
            "seconds": seconds,
            "attempts": card.attempts,
            "prompt_tokens": usage.prompt_tokens,
            "output_tokens": usage.output_tokens,
            "thought_tokens": usage.thought_tokens,
            "cost_usd": None if cost is None else round(cost, 6),
            "labels": dict(
                Counter(
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
            ),
            "quotes_total": len(quotes),
            "quotes_found_in_text": sum(_normal(q) in page for q in quotes),
        }
    result.measurements["location"] = location
    result.measurements["layers"] = per_layer
    if per_layer:
        result.measurements["gemini_cost_usd_total"] = round(total_cost, 6) if cost_known else None

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
