"""Settings, read from the process environment and from the file ".env".

Design rule 9: a secret never appears in git, in a log, in the database,
in a test file or in the chat. So this module has two rules:

* Secrets are held in SecretStr, which prints as "**********".
* describe() tells whether a value is set. It prints the value only for the few settings
  that are marked public below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Marks a setting whose value is safe to show on a screen. Everything else is shown as
# "set" or "empty" only.
_PUBLIC = {"public": True}

DEFAULT_POSTGRES_PORT = 55432


class SettingsError(Exception):
    """A setting is missing or wrong. The message never contains a secret value."""


class Settings(BaseSettings):
    """Every name here is listed in .env.example. The names are the same, in capitals."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # The rule for this class: a setting is either marked public (its value may be shown) or it
    # is a SecretStr (its value never prints, also not in repr(), a log or a traceback).
    # A test enforces this, so a new private setting cannot be added as a plain str.

    # Hedera (design section 15, step 1). The IDs are public on the ledger by nature.
    hedera_network: Literal["testnet", "previewnet", "mainnet"] = Field(
        "testnet", json_schema_extra=_PUBLIC
    )
    hedera_operator_id: str = Field("", json_schema_extra=_PUBLIC)
    hedera_operator_key: SecretStr = SecretStr("")
    hedera_topic_id: str = Field("", json_schema_extra=_PUBLIC)

    # GitHub (step 2)
    github_token: SecretStr = SecretStr("")

    # Google Cloud: Gemini 3.8 Flash and the embedding model on Vertex AI (step 3)
    google_cloud_project: SecretStr = SecretStr("")
    google_cloud_location: str = Field("", json_schema_extra=_PUBLIC)
    google_application_credentials: SecretStr = SecretStr("")

    # The local PostgreSQL that Docker Compose starts
    postgres_user: str = Field("hackathon", json_schema_extra=_PUBLIC)
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = Field("hackathon_memory", json_schema_extra=_PUBLIC)
    postgres_port: int = Field(DEFAULT_POSTGRES_PORT, json_schema_extra=_PUBLIC)
    # Optional. When set, it replaces the four POSTGRES lines above.
    database_url: SecretStr = SecretStr("")

    # The promises made to the sites (design section 5.7)
    collector_name: str = Field("", json_schema_extra=_PUBLIC)
    collector_contact_email: SecretStr = SecretStr("")
    # One switch per site. "off" is the default: a collector runs only when it is turned on.
    collect_ethglobal: bool = Field(False, json_schema_extra=_PUBLIC)

    def database_conninfo(self) -> str:
        """The text that psycopg needs to open the database. It holds a password: never print it."""
        from psycopg.conninfo import make_conninfo

        url = self.database_url.get_secret_value()
        if url:
            return url
        password = self.postgres_password.get_secret_value()
        if not password:
            raise SettingsError("POSTGRES_PASSWORD is empty. Set it in .env (or set DATABASE_URL).")
        # "127.0.0.1" and not "localhost": on Windows with Docker Desktop, "localhost" can
        # resolve to the IPv6 address first, which accepts the connection and never answers.
        # The connection then waits for ever. The compose file binds 127.0.0.1 only.
        # The timeout makes any such wait end with an error.
        return make_conninfo(
            host="127.0.0.1",
            port=self.postgres_port,
            user=self.postgres_user,
            password=password,
            dbname=self.postgres_db,
            connect_timeout=10,
        )


@dataclass(frozen=True)
class SettingLine:
    name: str
    state: str  # "set", "empty", or the value itself for a public setting


def describe(settings: Settings) -> list[SettingLine]:
    """One line per setting. A value is shown only for a public setting."""
    lines: list[SettingLine] = []
    for field_name, field in type(settings).model_fields.items():
        value = getattr(settings, field_name)
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        is_public = bool((field.json_schema_extra or {}).get("public"))
        if is_public:
            state = str(value) if value != "" else "empty"
        else:
            state = "set" if value not in ("", None) else "empty"
        lines.append(SettingLine(name=field_name.upper(), state=state))
    return lines
