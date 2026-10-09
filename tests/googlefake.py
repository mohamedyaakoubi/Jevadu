"""The real google-genai library with only the network faked.

The library builds its real requests and reads its real answers. A handler plays the part of Google
and records what it was sent. No real credential is involved: FakeCredentials hands out a dummy
token, and nothing leaves the computer.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import google.auth.credentials
import httpx
from google import genai
from google.genai import types

PAGE_CANARY = "PAGE-CANARY-TEXT-ZED-WIDGET"


class FakeCredentials(google.auth.credentials.Credentials):
    def refresh(self, request: object) -> None:
        self.token = "dummy-token-for-an-offline-test"


class FakeGoogle:
    """Answers like Vertex AI would, and keeps every request it got."""

    def __init__(self, answer_text: str = "{}", usage: dict | None = None) -> None:
        self.requests: list[tuple[str, dict]] = []
        self.answer_text = answer_text
        self.usage = usage or {
            "promptTokenCount": 1000,
            "candidatesTokenCount": 200,
            "thoughtsTokenCount": 300,
            "totalTokenCount": 1500,
        }
        self.finish_reason = "STOP"
        self.embedding_size = 3072
        self.embedding_count: int | None = None
        self.truncated = False
        # Optional: make the vector depend on the text, so that close and far can differ.
        self.vector_for: Callable[[str], list[float]] | None = None
        # Optional: answer every request with an error, as (status, message).
        self.fail_with: tuple[int, str] | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.requests.append((request.url.path, body))
        if self.fail_with:
            status, message = self.fail_with
            return httpx.Response(status, json={"error": {"code": status, "message": message}})
        if request.url.path.endswith(":predict"):
            instances = body["instances"]
            count = self.embedding_count or len(instances)

            def values_for(position: int) -> list[float]:
                if self.vector_for and position < len(instances):
                    return self.vector_for(instances[position]["content"])
                return [0.5] * self.embedding_size

            predictions = [
                {
                    "embeddings": {
                        "values": values_for(i),
                        "statistics": {"token_count": 7, "truncated": self.truncated},
                    }
                }
                for i in range(count)
            ]
            return httpx.Response(200, json={"predictions": predictions})
        parts = [{"text": self.answer_text}] if self.answer_text else []
        candidate = {
            "content": {"role": "model", "parts": parts},
            "finishReason": self.finish_reason,
        }
        return httpx.Response(200, json={"candidates": [candidate], "usageMetadata": self.usage})

    def client(self) -> genai.Client:
        transport = httpx.MockTransport(self.handler)
        return genai.Client(
            enterprise=True,
            project="test-project",
            location="global",
            credentials=FakeCredentials(),
            http_options=types.HttpOptions(httpx_client=httpx.Client(transport=transport)),
        )


def valid_form(**changes: object) -> dict:
    """An invented, valid answer for the card form."""
    quote = "Zed Widget lets a shop keep a public list of small facts."
    form: dict = {
        "what_it_does": {
            "label": "stated",
            "text": "It keeps a public list of facts.",
            "quotes": [quote],
        },
        "how_it_works": {
            "label": "inferred",
            "steps": [
                "A shop adds a fact.",
                "The widget writes it to a topic.",
                "Anyone reads the list.",
            ],
            "quotes": [quote],
        },
        "for_whom": {"label": "inferred", "text": "Small shops.", "quotes": [quote]},
        "hedera_services": {"label": "stated", "text": "The Consensus Service.", "quotes": [quote]},
        "category": {"label": "inferred", "category": "Payments and remittance", "quotes": [quote]},
        "problem": {"label": "not_found", "text": "", "quotes": []},
        "solution": {"label": "not_found", "text": "", "quotes": []},
    }
    form.update(changes)
    return form


def answer(**changes: object) -> str:
    return json.dumps(valid_form(**changes))


def body_text(handler_body: dict) -> Callable[[str], bool]:
    flat = json.dumps(handler_body)
    return lambda needle: needle in flat
