"""Making the Google client from the settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from google.auth.exceptions import DefaultCredentialsError

from googlefake import FakeCredentials
from hackathon_memory.llm import client as client_module
from hackathon_memory.llm.client import GoogleSetupError, load_key_file, make_client
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


def test_a_service_account_key_file_is_read(tmp_path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # a throwaway key
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    path = tmp_path / "service-account.json"
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "test-project",
                "private_key_id": "x",
                "private_key": pem,
                "client_email": "tool@test-project.iam.gserviceaccount.com",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        encoding="utf-8",
    )
    loaded = load_key_file(str(path))
    assert loaded.service_account_email == "tool@test-project.iam.gserviceaccount.com"


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
