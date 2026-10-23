"""Settings must never show a secret (design rule 9)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from hackathon_memory.settings import Settings, SettingsError, describe

CANARY = "CANARY-secret-value-0123456789"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every setting from the environment, so a real value on this laptop cannot leak in."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def make(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_describe_never_shows_a_secret(clean_env: None) -> None:
    settings = make(
        hedera_operator_key=CANARY,
        github_token=CANARY,
        postgres_password=CANARY,
        database_url=CANARY,
        collector_contact_email=CANARY,
        google_cloud_project=CANARY,
    )
    shown = "\n".join(f"{line.name}: {line.state}" for line in describe(settings))
    assert CANARY not in shown
    assert CANARY not in repr(settings)
    assert CANARY not in str(settings)


def test_every_private_setting_is_a_secretstr() -> None:
    """A new private setting added as a plain str would print in repr(). This stops it."""
    for name, field in Settings.model_fields.items():
        is_public = bool((field.json_schema_extra or {}).get("public"))
        if not is_public:
            assert field.annotation is SecretStr, f"{name} must be a SecretStr or be marked public"


def test_describe_shows_set_or_empty_for_private_and_the_value_for_public(clean_env: None) -> None:
    lines = {line.name: line.state for line in describe(make(github_token=CANARY))}
    assert lines["GITHUB_TOKEN"] == "set"
    assert lines["HEDERA_OPERATOR_KEY"] == "empty"
    assert lines["HEDERA_NETWORK"] == "testnet"
    assert lines["COLLECT_ETHGLOBAL"] == "False"


def test_every_setting_is_listed_in_the_example_file() -> None:
    root = Path(__file__).resolve().parents[1]
    example = (root / ".env.example").read_text(encoding="utf-8")
    listed = {
        line.split("=", 1)[0].lstrip("# ").strip() for line in example.splitlines() if "=" in line
    }
    for name in Settings.model_fields:
        assert name.upper() in listed, f"{name.upper()} is missing from .env.example"


def test_collectors_are_off_by_default(clean_env: None) -> None:
    assert make().collect_ethglobal is False
    assert make().collect_github is False
    assert make().collect_africa_winners is False
    assert make().collect_hedera_posts is False


def test_the_switch_reads_on_and_off(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLLECT_ETHGLOBAL", "on")
    assert Settings(_env_file=None).collect_ethglobal is True
    monkeypatch.setenv("COLLECT_ETHGLOBAL", "off")
    assert Settings(_env_file=None).collect_ethglobal is False


def test_conninfo_needs_a_password_or_a_url(clean_env: None) -> None:
    with pytest.raises(SettingsError):
        make().database_conninfo()


def test_conninfo_is_built_from_the_parts(clean_env: None) -> None:
    info = make(postgres_password="pw with space").database_conninfo()
    assert "host=127.0.0.1" in info  # not "localhost": see the comment in settings.py
    assert "connect_timeout=10" in info
    assert "port=55432" in info
    assert "user=hackathon" in info
    assert "dbname=hackathon_memory" in info


def test_a_database_url_replaces_the_parts(clean_env: None) -> None:
    url = "postgresql://someone:pw@db.example.test:5432/other"
    assert make(database_url=url).database_conninfo() == url


# ------------------------------------------------------------------ the two Gemini layers


def test_the_gemini_layers_have_the_owners_choices_by_default(clean_env: None) -> None:
    s = make()
    assert s.gemini_rewrite_model == "gemini-3.1-pro-preview"  # reading and rewriting the pages
    assert s.gemini_search_model == "gemini-3.8-flash"  # the search
    assert s.gemini_rewrite_thinking_level == "HIGH"
    assert s.gemini_search_thinking_level == "LOW"  # measured faster, 16 October 2026


def test_the_gemini_settings_are_read_from_the_environment(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEMINI_REWRITE_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("GEMINI_REWRITE_THINKING_LEVEL", " low ")
    monkeypatch.setenv("GEMINI_SEARCH_THINKING_LEVEL", "medium")
    s = Settings(_env_file=None)
    assert s.gemini_rewrite_model == "gemini-3.8-flash"
    assert s.gemini_rewrite_thinking_level == "LOW"  # capitals and spaces are fixed
    assert s.gemini_search_thinking_level == "MEDIUM"


@pytest.mark.parametrize(
    "bad",
    [
        {"gemini_rewrite_model": "gpt-4o"},  # design rule 7: Gemini only
        {"gemini_search_model": "other-vendor-model"},
        {"gemini_search_model": ""},
        {"gemini_rewrite_model": "gemini-3.8 flash"},
        {"gemini_rewrite_thinking_level": "MINIMAL"},  # refused by both models
        {"gemini_search_thinking_level": "2048"},  # a budget is not a level
    ],
)
def test_a_wrong_gemini_setting_is_refused_at_once(clean_env: None, bad: dict) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        make(**bad)


def test_the_gemini_settings_are_public(clean_env: None) -> None:
    lines = {line.name: line.state for line in describe(make())}
    assert lines["GEMINI_REWRITE_MODEL"] == "gemini-3.1-pro-preview"
    assert lines["GEMINI_SEARCH_THINKING_LEVEL"] == "LOW"
