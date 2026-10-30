"""Making the Google client from the settings."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from google.auth.exceptions import DefaultCredentialsError
from google.genai import errors as genai_errors
from google.genai import types

from googlefake import FakeCredentials, FakeGoogle
from hackathon_memory.llm import client as client_module
from hackathon_memory.llm import embeddings
from hackathon_memory.llm.client import (
    GoogleSetupError,
    again_if_dropped,
    credentials_of,
    default_http_options,
    load_key_file,
    make_client,
    project_of,
    vercel_token,
)
from hackathon_memory.settings import Settings


def settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_the_project_and_the_location_are_needed() -> None:
    with pytest.raises(GoogleSetupError, match="GOOGLE_CLOUD_PROJECT"):
        make_client(settings(), credentials=FakeCredentials())
    with pytest.raises(GoogleSetupError, match="GOOGLE_CLOUD_LOCATION"):
        make_client(settings(google_cloud_project="p"), credentials=FakeCredentials())


def test_a_client_is_made_in_the_enterprise_mode_with_the_values_passed_in() -> None:
    made = make_client(
        settings(google_cloud_project="my-project", google_cloud_location="global"),
        credentials=FakeCredentials(),
    )
    api = made._api_client
    assert api.vertexai is True
    assert api.project == "my-project"
    assert api.location == "global"


def test_a_key_file_that_cannot_be_read_gives_a_clear_error(tmp_path: Path) -> None:
    broken = tmp_path / "not-a-key.json"
    broken.write_text("{ this is not a key", encoding="utf-8")
    with pytest.raises(GoogleSetupError, match="key file"):
        make_client(
            settings(
                google_cloud_project="p",
                google_cloud_location="global",
                google_application_credentials=str(broken),
            )
        )


def test_no_sign_in_gives_the_command_to_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(**_: object) -> None:
        raise DefaultCredentialsError("no credentials in this test")

    monkeypatch.setattr(client_module.genai, "Client", refuse)
    with pytest.raises(GoogleSetupError, match="gcloud auth application-default login"):
        make_client(settings(google_cloud_project="p", google_cloud_location="global"))


def throwaway_key(project: str = "test-project") -> dict:
    """A service account key with a private key made for the test, never a real one."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return {
        "type": "service_account",
        "project_id": project,
        "private_key_id": "x",
        "private_key": pem,
        "client_email": f"tool@{project}.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def test_a_service_account_key_file_is_read(tmp_path: Path) -> None:
    path = tmp_path / "service-account.json"
    path.write_text(json.dumps(throwaway_key()), encoding="utf-8")
    loaded = load_key_file(str(path))
    assert loaded.service_account_email == "tool@test-project.iam.gserviceaccount.com"


def test_the_host_signs_in_with_the_token_of_its_request_and_no_key() -> None:
    """On Vercel, Google's Security Token Service takes the token that Vercel gives the request
    and lets it act as the service account that may only call Vertex AI (vercel.com/docs/oidc/gcp,
    read 29 October 2026)."""
    from google.auth import identity_pool
    from google.auth.exceptions import RefreshError

    audience = ("//iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/vercel/"
                "providers/vercel")  # fmt: skip
    account = "jevadu-gemini@p-one.iam.gserviceaccount.com"
    federation = {"google_federation_audience": audience, "google_federation_account": account}
    host = settings(google_cloud_project="p-one", google_cloud_location="global", **federation)
    signed = credentials_of(host)
    assert isinstance(signed, identity_pool.Credentials) and signed.info["audience"] == audience
    assert signed.service_account_email == account and project_of(host) == "p-one"
    supplier = signed._subject_token_supplier
    with pytest.raises(RefreshError, match="No token of Vercel"):
        supplier.get_subject_token(None, None)
    token = vercel_token.set("token-of-this-request")
    try:
        assert supplier.get_subject_token(None, None) == "token-of-this-request"
    finally:
        vercel_token.reset(token)
    assert credentials_of(settings(google_federation_audience=audience)) is None  # both, or none


def test_a_user_login_file_is_read(tmp_path: Path) -> None:
    path = tmp_path / "adc.json"
    path.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "client_id": "id",
                "client_secret": "secret",
                "refresh_token": "token",
            }
        ),
        encoding="utf-8",
    )
    assert load_key_file(str(path)).refresh_token == "token"


def test_any_other_kind_of_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"type": "external_account"}), encoding="utf-8")
    with pytest.raises(GoogleSetupError, match="service account key or a user login"):
        load_key_file(str(path))


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(GoogleSetupError, match="cannot be read"):
        load_key_file(str(tmp_path / "missing.json"))


# ------------------------------------------------------------------ retry on transient errors


def quick_retry(attempts: int = 4) -> types.HttpRetryOptions:
    """The options of default_http_options, with waits of a few milliseconds for the tests."""
    options = default_http_options(attempts=attempts, initial_delay=0.001, max_delay=0.005)
    return options.retry_options


def test_the_default_options_retry_the_transient_codes_and_set_a_long_timeout() -> None:
    options = default_http_options()
    assert options.retry_options.attempts == 4
    assert options.retry_options.http_status_codes == [408, 429, 500, 502, 503, 504]
    assert options.timeout == 300_000  # milliseconds


def test_the_library_does_not_retry_unless_told_to() -> None:
    """The reason for default_http_options. If this test fails, the library changed its default."""
    google = FakeGoogle()
    google.fail_first = [500, 500]
    with pytest.raises(genai_errors.ServerError):
        embeddings.embed_documents(google.client(), ["text"])
    assert google.failed_requests == 1  # one try, then the error


def test_a_500_from_google_is_tried_again_and_then_answered() -> None:
    google = FakeGoogle()
    google.fail_first = [500, 503]
    [vector] = embeddings.embed_documents(google.client(quick_retry()), ["text"])
    assert len(vector.values) == 3072
    assert google.failed_requests == 2  # two failures, then the answer


def test_an_error_that_will_not_pass_is_not_tried_again() -> None:
    google = FakeGoogle()
    google.fail_first = [400, 400, 400]
    with pytest.raises(genai_errors.ClientError):
        embeddings.embed_documents(google.client(quick_retry()), ["text"])
    assert google.failed_requests == 1


def test_it_gives_up_after_the_attempts() -> None:
    google = FakeGoogle()
    google.fail_first = [500] * 10
    with pytest.raises(genai_errors.ServerError):
        embeddings.embed_documents(google.client(quick_retry(attempts=3)), ["text"])
    assert google.failed_requests == 3


# ------------------------------------------------------------------ a connection that broke


@pytest.fixture
def no_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "PAUSES_AFTER_A_DROP", (0.0, 0.0, 0.0))


def test_the_library_does_not_try_again_when_a_connection_breaks() -> None:
    """The reason for again_if_dropped. If this test fails, google-genai changed: read its
    _api_client.py again (_HTTPX_TRANSIENT_EXC) and see whether DROPPED is still needed."""
    google = FakeGoogle()
    google.drop_first = 1
    with pytest.raises(httpx.RemoteProtocolError):
        google.client(quick_retry()).models.embed_content(model="gemini-embedding-2", contents="x")
    assert google.dropped_requests == 1


def test_a_broken_connection_is_made_again_after_a_pause(no_pauses: None) -> None:
    google = FakeGoogle()
    google.drop_first = 2
    [vector] = embeddings.embed_documents(google.client(quick_retry()), ["text"])
    assert len(vector.values) == 3072
    assert google.dropped_requests == 2


def test_a_network_that_stays_away_fails_after_the_pauses() -> None:
    slept: list[float] = []
    tries: list[str] = []

    def call() -> str:
        tries.append("a try")
        raise httpx.ConnectError("no network")

    with pytest.raises(httpx.ConnectError):
        again_if_dropped(call, sleep=slept.append)
    assert slept == [5.0, 15.0, 45.0]
    assert len(tries) == 4


def test_an_error_that_is_not_a_broken_connection_is_not_made_again() -> None:
    slept: list[float] = []

    def call() -> str:
        raise ValueError("not the network")

    with pytest.raises(ValueError, match="not the network"):
        again_if_dropped(call, sleep=slept.append)
    assert slept == []


def test_make_client_uses_the_retry_options_by_default() -> None:
    made = make_client(
        settings(google_cloud_project="p", google_cloud_location="global"),
        credentials=FakeCredentials(),
    )
    assert made._api_client._http_options.retry_options.attempts == 4
