"""One way to make the Google client, from the settings (design 11.3, design rule 7).

Google now calls the platform "Gemini Enterprise Agent Platform" (it was Vertex AI). In
google-genai 2.29.0 the client takes `enterprise=True`, and `vertexai=True` is the old name.
The settings are passed in on purpose: pydantic-settings does not put the values of .env into the
environment, so the library's own reading of GOOGLE_CLOUD_PROJECT would not see them.

Signing in, first found: the service account key of GOOGLE_SERVICE_ACCOUNT_KEY, which also names
the project (python -m hackathon_memory.llm.account switch writes it); the key file named by
GOOGLE_APPLICATION_CREDENTIALS; else Application Default Credentials, which
`gcloud auth application-default login` sets up.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
from google import genai
from google.auth.credentials import Credentials
from google.auth.exceptions import GoogleAuthError
from google.genai import types
from google.oauth2 import credentials as user_credentials
from google.oauth2 import service_account

from hackathon_memory.settings import Settings

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

# The codes that mean "try again in a moment": the request timed out, too many requests, and the
# errors of the server (500 was seen from Gemini 3.1 Pro preview on the second live run).
RETRYABLE_CODES = [408, 429, 500, 502, 503, 504]

# A connection that broke before Google answered: the network went away (a change of Wi-Fi broke
# a run on 12 October 2026), or the server closed it. google-genai 2.29.0 tries again only after
# a timeout or a connection that could not be made (`_HTTPX_TRANSIENT_EXC` in `_api_client.py`),
# and stops after about 15 seconds. These pauses are long enough for a change of network.
DROPPED = (httpx.NetworkError, httpx.RemoteProtocolError)
PAUSES_AFTER_A_DROP = (5.0, 15.0, 45.0)

T = TypeVar("T")


def again_if_dropped(call: Callable[[], T], *, sleep: Callable[[float], None] = time.sleep) -> T:
    """Make the call. If its connection breaks, wait and make it again, once after each pause.

    Each call goes through the meter, so a call that broke is counted, with the class of its
    error. Google may still have done a call whose answer was lost, and billed it: a rare second
    cost, paid so that a long run goes on.
    """
    for pause in PAUSES_AFTER_A_DROP:
        try:
            return call()
        except DROPPED:
            sleep(pause)
    return call()


class GoogleSetupError(Exception):
    """The Google settings or the sign-in are not ready. The message holds no secret."""


def load_key_file(path: str) -> Credentials:
    """Read a key file of one of the two kinds that Google gives, and nothing else.

    google.auth.load_credentials_from_file is deprecated: it does not check what kind of
    credential the file holds. Here the kind is read first and must be one of the two.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            kind = json.load(handle).get("type")
        if kind == "service_account":
            return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
        if kind == "authorized_user":
            return user_credentials.Credentials.from_authorized_user_file(path, scopes=SCOPES)
    except (OSError, ValueError, KeyError, AttributeError, GoogleAuthError):
        raise GoogleSetupError(
            "The key file named by GOOGLE_APPLICATION_CREDENTIALS cannot be read."
        ) from None
    raise GoogleSetupError(
        "The key file named by GOOGLE_APPLICATION_CREDENTIALS must be a service account key "
        "or a user login file."
    )


def service_account_key(settings: Settings) -> dict | None:
    """The service account key of GOOGLE_SERVICE_ACCOUNT_KEY, read from its line of base64, or
    None when the line is empty."""
    line = settings.google_service_account_key.get_secret_value().strip()
    if not line:
        return None
    try:
        key = json.loads(base64.b64decode(line, validate=True))
    except (ValueError, binascii.Error):
        key = None
    is_key = isinstance(key, dict) and key.get("type") == "service_account"
    if not (is_key and key.get("project_id")):
        raise GoogleSetupError(
            "GOOGLE_SERVICE_ACCOUNT_KEY is not a service account key in base64. Write it again: "
            "python -m hackathon_memory.llm.account switch"
        )
    return key


def project_of(settings: Settings) -> str:
    """The Google Cloud project that the models are asked and billed in: the project of the key
    of GOOGLE_SERVICE_ACCOUNT_KEY when there is one, since the switch gives that key the right
    to call Vertex AI there only; else GOOGLE_CLOUD_PROJECT."""
    key = service_account_key(settings)
    if key is not None:
        return str(key["project_id"])
    return settings.google_cloud_project.get_secret_value().strip()


def credentials_of(settings: Settings) -> Credentials | None:
    """The sign-in of the settings: the key of GOOGLE_SERVICE_ACCOUNT_KEY, else the key file named
    by GOOGLE_APPLICATION_CREDENTIALS, else None, and then the library uses Application Default
    Credentials."""
    key = service_account_key(settings)
    if key is not None:
        try:
            return service_account.Credentials.from_service_account_info(key, scopes=SCOPES)
        except (ValueError, KeyError, GoogleAuthError):
            raise GoogleSetupError(
                "The key of GOOGLE_SERVICE_ACCOUNT_KEY cannot be read. Write it again: "
                "python -m hackathon_memory.llm.account switch"
            ) from None
    key_file = settings.google_application_credentials.get_secret_value().strip()
    return load_key_file(key_file) if key_file else None


def default_http_options(
    *,
    attempts: int = 4,
    initial_delay: float = 2.0,
    max_delay: float = 30.0,
    timeout_seconds: int = 300,
) -> types.HttpOptions:
    """Retry on the transient errors, and never wait for ever.

    The library does NOT retry unless it is told to: without these options a single 500 from
    Google ends the call (found on the second live run). The waits grow
    (2, 4, 8 seconds, with some randomness) up to `attempts` calls in all. The timeout is long
    because a call with HIGH thinking takes 20 to 40 seconds.
    """
    return types.HttpOptions(
        timeout=timeout_seconds * 1000,  # the library counts in milliseconds
        retry_options=types.HttpRetryOptions(
            attempts=attempts,
            initial_delay=initial_delay,
            max_delay=max_delay,
            exp_base=2.0,
            jitter=1.0,
            http_status_codes=RETRYABLE_CODES,
        ),
    )


def make_client(
    settings: Settings,
    *,
    credentials: Credentials | None = None,
    http_options: types.HttpOptions | None = None,
) -> genai.Client:
    project = project_of(settings)
    location = settings.google_cloud_location.strip()
    if not project or not location:
        raise GoogleSetupError(
            "GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION must both be set in .env "
            "(design 15, step 3)."
        )
    if credentials is None:
        credentials = credentials_of(settings)
    try:
        return genai.Client(
            enterprise=True,
            project=project,
            location=location,
            credentials=credentials,
            http_options=http_options or default_http_options(),
        )
    except GoogleAuthError:
        raise GoogleSetupError(
            "No Google sign-in was found. Run: gcloud auth application-default login "
            "(or set GOOGLE_APPLICATION_CREDENTIALS to a key file)."
        ) from None
