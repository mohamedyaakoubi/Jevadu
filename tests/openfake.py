"""A stand-in for the OpenAI-compatible endpoint of the open models of Vertex AI
(llm/open_models.py): it answers like the endpoint, from what a test gives it, and keeps every
request it got."""

from __future__ import annotations

import json
from typing import Any

import httpx

from hackathon_memory.finops.budget import Budget
from hackathon_memory.finops.calls import MemoryStore
from hackathon_memory.finops.meter import Meter, Tags
from hackathon_memory.llm.open_models import OpenModels


def answer(content: str, usage: dict[str, Any] | None = None) -> dict[str, Any]:
    """An answer of the endpoint with `content`, as measured on 24 October 2026."""
    return {"choices": [{"message": {"content": content, "reasoning_content": "thought"}}],
            "usage": usage or {"prompt_tokens": 120, "completion_tokens": 900}}  # fmt: skip


class FakeOpenModels:
    """Answers each request with the next of `replies`, then with `content` and a status of 200."""

    def __init__(self, *replies: tuple[int, dict[str, Any]], content: str = "{}") -> None:
        self.replies = list(replies)
        self.content = content
        self.sent: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        status, body = self.replies.pop(0) if self.replies else (200, answer(self.content))
        return httpx.Response(status, json=body)

    def body(self, number: int = 0) -> dict[str, Any]:
        return json.loads(self.sent[number].content)


def open_client(endpoint: FakeOpenModels, store: MemoryStore | None = None,
                budget: Budget | None = None, purpose: str = "rerank") -> OpenModels:  # fmt: skip
    """A client of the open models that asks `endpoint`, counted in `store`."""
    meter = Meter(store if store is not None else MemoryStore(), "test", budget=budget,
                  location="global")  # fmt: skip
    return OpenModels("a-project", meter, Tags(purpose=purpose), lambda: "a-token",
                      http=httpx.Client(transport=httpx.MockTransport(endpoint)))  # fmt: skip
