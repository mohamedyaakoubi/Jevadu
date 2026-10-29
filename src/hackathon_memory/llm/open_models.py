"""The open models that Google serves on Vertex AI as a service (Model as a Service), through their
OpenAI-compatible endpoint (Google's pages "Call MaaS APIs for open models", "DeepSeek-V4.1-Flash"
and "Thinking", read on 24 October 2026).

Only DeepSeek V4.1 Flash is used: the stand-in for the search model when Gemini keeps failing
(the maintainer's decision of 24 October 2026, design 8.2). Its model ID is
deepseek-v4.1-flash-maas, from the publisher deepseek-ai, on the global endpoint only, in Preview
until at least 28 November 2026. Thinking is switched on with "chat_template_kwargs":
{"thinking": true}, as Google's page of thinking says for DeepSeek, and "reasoning_effort":
"high", DeepSeek's own word, is accepted too. Seen on 24 October 2026 with three tiny calls: the
thinking comes back in "reasoning_content", and its tokens are inside "completion_tokens" with no
count of their own, so the meter counts them as output, at the same price.

Every call goes through the meter, as a call to Gemini does (finops/meter.py): the budget is asked
before it, and the tokens, the time and the class of an error after it, never a text.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import httpx

from hackathon_memory.finops.meter import Gate, Meter, Tags

DEEPSEEK_FLASH = "deepseek-v4.1-flash-maas"
PUBLISHERS = {DEEPSEEK_FLASH: "deepseek-ai"}
ENDPOINT = (
    "https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/endpoints/openapi/"
    "chat/completions"
)
SCOPE = "https://www.googleapis.com/auth/cloud-platform"
LETTERS_A_TOKEN = 4  # to guess the input tokens for the budget before the call


class OpenModelError(Exception):
    """The endpoint answered with an error, or with no answer to read. The message holds the
    status and its kind, never a text that was sent; `status` is the HTTP status, when there is
    one, which the meter keeps with the class of the error (429 is "too many requests")."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Answer:
    text: str
    input_tokens: int
    output_tokens: int  # without the thinking tokens
    thinking_tokens: int


class OpenModels:
    """A client of the open models of Vertex AI, counted by the meter. `token` gives a fresh
    access token of Google; `http` sends the requests (a test hands in a stand-in)."""

    def __init__(
        self,
        project: str,
        meter: Meter,
        tags: Tags,
        token: Callable[[], str],
        *,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._project = project
        self._url = ENDPOINT.format(project=project)
        self._meter = meter
        self._tags = tags
        self._token = token
        self._http = http or httpx.Client()
        self._clock = clock

    @property
    def meter(self) -> Meter:
        return self._meter

    def tagged(self, **changes: str | None) -> OpenModels:
        """The same client and the same meter, for another purpose, run or item."""
        return OpenModels(self._project, self._meter, replace(self._tags, **changes), self._token,
                          http=self._http, clock=self._clock)  # fmt: skip

    def gated(self, gate: Gate) -> OpenModels:
        """The same client and ledger, behind a gate (finops/meter.py); this one stays without."""
        return OpenModels(self._project, self._meter.with_gate(gate), self._tags, self._token,
                          http=self._http, clock=self._clock)  # fmt: skip

    def chat(
        self,
        model: str,
        system: str,
        user: str,
        *,
        thinking: bool,
        max_tokens: int,
        timeout_seconds: float,
        as_json: bool = False,
        effort: str | None = None,
    ) -> Answer:
        """One answer of the model, counted. Raises OpenModelError, an error of httpx, or
        BudgetExceeded before the call."""
        guessed = (len(system) + len(user)) // LETTERS_A_TOKEN + 1
        self._meter.before_call(model, guessed, max_tokens, self._tags)
        body: dict[str, Any] = {
            "model": f"{PUBLISHERS[model]}/{model}",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"thinking": thinking},
        }
        if as_json:
            body["response_format"] = {"type": "json_object"}
        if effort:  # DeepSeek's own word for how hard it thinks ("high"), on its page of the API
            body["reasoning_effort"] = effort
        start = self._clock()
        try:
            response = self._http.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._token()}"},
                timeout=timeout_seconds,
            )  # fmt: skip
            if response.status_code != 200:
                raise OpenModelError(f"the endpoint answered {response.status_code}",
                                     response.status_code)  # fmt: skip
            try:
                data = response.json()
            except json.JSONDecodeError as bad:
                raise OpenModelError("the endpoint answered 200 with no JSON") from bad
            text = _content(data)
        except (OpenModelError, httpx.HTTPError) as error:
            status = getattr(error, "status", None)
            kind = type(error).__name__ + (f" {status}" if status else "")
            self._meter.record(self._tags, model=model, input_tokens=0, ok=False,
                               latency_ms=int((self._clock() - start) * 1000),
                               error_kind=kind)  # fmt: skip
            raise
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        thought = int(details.get("reasoning_tokens") or 0)
        written = int(usage.get("completion_tokens") or 0)
        answer = Answer(text, int(usage.get("prompt_tokens") or 0), max(0, written - thought),
                        thought)  # fmt: skip
        self._meter.record(
            self._tags, model=model, input_tokens=answer.input_tokens,
            output_tokens=answer.output_tokens, thinking_tokens=answer.thinking_tokens,
            thinking_level=(effort or "ON").upper() if thinking else None,
            latency_ms=int((self._clock() - start) * 1000),
        )  # fmt: skip
        return answer


def _content(data: Any) -> str:
    """The text of the first choice of an answer. An answer of 200 with no choice in it was seen
    once on 24 October 2026; it raises OpenModelError, which names its keys, never a text."""
    try:
        return data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError, AttributeError) as bad:
        keys = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise OpenModelError(f"the endpoint answered 200 with no choice: {keys}") from bad


def google_token(settings: Any) -> Callable[[], str]:
    """What gives a fresh access token of the Google sign-in that the Gemini client uses."""
    import google.auth
    from google.auth.transport.requests import Request

    from hackathon_memory.llm.client import load_key_file

    key_file = settings.google_application_credentials.get_secret_value().strip()
    if key_file:
        credentials = load_key_file(key_file)  # with the scope of the Gemini client, the same
    else:
        credentials, _ = google.auth.default(scopes=[SCOPE])

    def token() -> str:
        if not credentials.valid:
            credentials.refresh(Request())
        return credentials.token

    return token


def open_models(
    settings: Any, purpose: str, *, run_id: str | None = None, gate: Gate | None = None
) -> OpenModels:
    """The client of the open models, counted by the meter of the environment in use, and behind
    `gate` when one is given."""
    from hackathon_memory.finops import budget as budgets
    from hackathon_memory.finops.calls import PostgresStore

    meter = Meter(PostgresStore(settings.database_conninfo()), settings.llm_environment,
                  budget=budgets.from_settings(settings), location="global", gate=gate)  # fmt: skip
    return OpenModels(settings.google_cloud_project.get_secret_value().strip(), meter,
                      Tags(purpose=purpose, run_id=run_id), google_token(settings))  # fmt: skip
