"""One way to make the Google client, from the settings (design 11.3, design rule 7).

Google now calls the platform "Gemini Enterprise Agent Platform" (it was Vertex AI). In
google-genai 2.29.0 the client takes `enterprise=True`, and `vertexai=True` is the old name.
The settings are passed in on purpose: pydantic-settings does not put the values of .env into the
environment, so the library's own reading of GOOGLE_CLOUD_PROJECT would not see them.

Signing in: if GOOGLE_APPLICATION_CREDENTIALS names a key file, it is used. If not, the library
uses Application Default Credentials, which `gcloud auth application-default login` sets up.
"""

from __future__ import annotations

import json

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
    project = settings.google_cloud_project.get_secret_value().strip()
    location = settings.google_cloud_location.strip()
    if not project or not location:
        raise GoogleSetupError(
            "GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION must both be set in .env "
            "(design 15, step 3)."
        )
    key_file = settings.google_application_credentials.get_secret_value().strip()
    if credentials is None and key_file:
        credentials = load_key_file(key_file)
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
