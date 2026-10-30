"""Settings, read from the process environment and from the file ".env".

Design rule 9: a secret never appears in git, in a log, in the database,
in a test file or in the chat. So this module has two rules:

* Secrets are held in SecretStr, which prints as "**********".
* describe() tells whether a value is set. It prints the value only for the few settings
  that are marked public below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Marks a setting whose value is safe to show on a screen. Everything else is shown as
# "set" or "empty" only.
_PUBLIC = {"public": True}

DEFAULT_POSTGRES_PORT = 55432

# The levels of thinking that Gemini 3.1 Pro and Gemini 3.8 Flash both accept (Google's page
# "Thinking", 9 October 2026). MINIMAL is refused by both. The old "thinking budget" is not a
# setting: Google deprecated it for Gemini 3, and sending it with a level is an error.
ThinkingLevelName = Literal["LOW", "MEDIUM", "HIGH"]


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
    # The project ID of WalletConnect (Reown), which a Hedera wallet such as HashPack needs to
    # sign a registration (design 9.6). Not a secret: every page that connects a wallet shows it.
    walletconnect_project_id: str = Field("", json_schema_extra=_PUBLIC)
    # A second topic, for rehearsals of a registration: the website writes to it only when it
    # is started with --rehearsal (design 9.3, 25 October 2026).
    hedera_rehearsal_topic_id: str = Field("", json_schema_extra=_PUBLIC)

    # GitHub (step 2)
    github_token: SecretStr = SecretStr("")
    # Jevadu's GitHub App (web/github_app.py, design 9.2): at a team's request, it adds the line
    # of the register to the team's README, as a commit of the person who signs in with GitHub.
    # Made once with GitHub's manifest flow. Its slug and its client ID are public (every link
    # to the app shows them); its client secret is not. Empty: the box offers no such button.
    github_app_slug: str = Field("", json_schema_extra=_PUBLIC)
    github_app_client_id: str = Field("", json_schema_extra=_PUBLIC)
    github_app_client_secret: SecretStr = SecretStr("")
    # The salt of the hash that counts each visitor of the public copy (web/public.py): any long
    # random text, kept so that the counts of a day hold across a restart.
    public_salt: SecretStr = SecretStr("")
    # The Cloudflare tunnel of the public copy (web/tunnel.py): where it is, its port on this
    # computer, the API token that makes it (Cloudflare Tunnel: Edit, DNS: Edit), the account,
    # the token of the tunnel itself, and the program cloudflared when it is not found alone.
    public_host: str = Field("jevadu.mohamedyaakoubi.com", json_schema_extra=_PUBLIC)
    public_port: int = Field(8020, json_schema_extra=_PUBLIC)
    # The header in which the host of the public copy writes the visitor's address itself:
    # Cloudflare's for the tunnel; x-vercel-forwarded-for on Vercel (web/vercel_app.py).
    public_address_header: str = Field("cf-connecting-ip", json_schema_extra=_PUBLIC)
    # A token of Vercel, for the public copy's project there (web/vercel.py): the switch of the
    # Google account moves the copy too when it is set.
    vercel_token: SecretStr = SecretStr("")
    # The database of the public copy on its host (Neon), seen from this computer: the switches
    # of the public copy write there (web/switch.py).
    public_database_url: SecretStr = SecretStr("")
    # How many times one visitor of the public copy may ask Gemini, one time only (design
    # 12.5): 30 dollars pay about 300 visitors who use all 12.
    public_ai_per_visitor: int = Field(12, ge=0, json_schema_extra=_PUBLIC)
    # The GitHub account of the public copy's owner: once signed in with GitHub on /owner, through
    # Jevadu's GitHub App, its browser checks, reads again and registers with no count (web/
    # public.py, OWNERS_OWN). Public, like the name of every GitHub account. Empty: nobody.
    public_owner_github: str = Field("", json_schema_extra=_PUBLIC)
    # Cloudflare's Turnstile on the public copy (web/turnstile.py): the site key, which every
    # page that shows the widget carries, and the secret that spends its tokens. With both set,
    # a visitor confirms being a person before asking Gemini, checking, reading again or
    # registering.
    turnstile_site_key: str = Field("", json_schema_extra=_PUBLIC)
    turnstile_secret_key: SecretStr = SecretStr("")
    cloudflare_api_token: SecretStr = SecretStr("")
    cloudflare_account_id: str = Field("", json_schema_extra=_PUBLIC)
    cloudflare_tunnel_token: SecretStr = SecretStr("")
    cloudflared_path: str = Field("", json_schema_extra=_PUBLIC)

    # Google Cloud: the Gemini models and the embedding model on Vertex AI (step 3)
    google_cloud_project: SecretStr = SecretStr("")
    google_cloud_location: str = Field("", json_schema_extra=_PUBLIC)
    google_application_credentials: SecretStr = SecretStr("")
    # The public copy on Vercel signs in to Google with no key, by Workload Identity Federation
    # (llm/client.py): the audience of the pool's provider, and the service account that may only
    # call Vertex AI. python -m hackathon_memory.llm.account switch sets them on the host; here
    # they stay empty.
    google_federation_audience: str = Field("", json_schema_extra=_PUBLIC)
    google_federation_account: str = Field("", json_schema_extra=_PUBLIC)

    # The two Gemini layers. The maintainer decided on 9 October 2026 (design rule 7):
    # the first layer reads and rewrites project pages into cards with Gemini 3.1 Pro, for the
    # quality of the rewrite. The search uses Gemini 3.8 Flash. Both are public settings: they
    # are model names and a level, not secrets. The defaults are the maintainer's choice.
    gemini_rewrite_model: str = Field("gemini-3.1-pro-preview", json_schema_extra=_PUBLIC)
    gemini_rewrite_thinking_level: ThinkingLevelName = Field("HIGH", json_schema_extra=_PUBLIC)
    gemini_search_model: str = Field("gemini-3.8-flash", json_schema_extra=_PUBLIC)
    gemini_search_thinking_level: ThinkingLevelName = Field("LOW", json_schema_extra=_PUBLIC)
    # The embedding model of the search (design 8.1). Chosen on 11 October 2026 for its known
    # price and its length of 8,192 tokens (llm/embeddings.py).
    gemini_embedding_model: str = Field("gemini-embedding-2", json_schema_extra=_PUBLIC)

    # What the models may cost (finops). "test" is all the work before the tool is shown: the
    # proofs, the tests, the first runs. "prod" is the tool while people use it. "public" is the
    # public copy of the website (design 12.5), which always counts under it, whatever
    # LLM_ENVIRONMENT says. Each has its own budget in dollars, and a call that could go over it
    # is not made. The defaults are small on purpose: about 70 project pages cost about 3
    # dollars with the two layers. The public copy has 30 dollars in all and 5 a day (29 October
    # 2026).
    llm_environment: Literal["test", "prod", "public"] = Field("test", json_schema_extra=_PUBLIC)
    llm_budget_test_usd: float = Field(15.0, ge=0, json_schema_extra=_PUBLIC)
    llm_budget_prod_usd: float = Field(30.0, ge=0, json_schema_extra=_PUBLIC)
    llm_budget_prod_per_day_usd: float = Field(5.0, ge=0, json_schema_extra=_PUBLIC)
    llm_budget_public_usd: float = Field(30.0, ge=0, json_schema_extra=_PUBLIC)
    llm_budget_public_per_day_usd: float = Field(5.0, ge=0, json_schema_extra=_PUBLIC)
    llm_budget_warn_percent: int = Field(80, ge=1, le=100, json_schema_extra=_PUBLIC)

    # The local PostgreSQL that Docker Compose starts
    postgres_user: str = Field("hackathon", json_schema_extra=_PUBLIC)
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = Field("hackathon_memory", json_schema_extra=_PUBLIC)
    postgres_port: int = Field(DEFAULT_POSTGRES_PORT, json_schema_extra=_PUBLIC)
    # Optional. When set, it replaces the four POSTGRES lines above.
    database_url: SecretStr = SecretStr("")

    # Where collected pages are kept. The folder is ignored by git (design section 5.3).
    data_dir: str = Field("data", json_schema_extra=_PUBLIC)

    # The promises made to the sites (design section 5.7)
    collector_name: str = Field("", json_schema_extra=_PUBLIC)
    collector_contact_email: SecretStr = SecretStr("")
    # One switch per site. "off" is the default: a collector runs only when it is turned on.
    collect_ethglobal: bool = Field(False, json_schema_extra=_PUBLIC)
    # GitHub's API: the README and the facts of the code of each project (design 7.3).
    collect_github: bool = Field(False, json_schema_extra=_PUBLIC)
    # The one page with the winners of the Hedera Africa hackathon (design 4.6).
    collect_africa_winners: bool = Field(False, json_schema_extra=_PUBLIC)
    # Hedera's own posts with the winners of its older hackathons (design 4.6).
    collect_hedera_posts: bool = Field(False, json_schema_extra=_PUBLIC)
    # What changes after an event is asked again once its newest answer is this old: GitHub's
    # answers and the facts of the ledger (design 7.3, 25 October 2026).
    refresh_after_hours: float = Field(24.0, gt=0, json_schema_extra=_PUBLIC)
    # While the website runs, the same work goes on in the background ("off" in tests).
    refresh_in_background: bool = Field(False, json_schema_extra=_PUBLIC)

    @field_validator("llm_environment", mode="before")
    @classmethod
    def _environment_in_small_letters(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("gemini_rewrite_thinking_level", "gemini_search_thinking_level", mode="before")
    @classmethod
    def _level_in_capitals(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("gemini_rewrite_model", "gemini_search_model", "gemini_embedding_model")
    @classmethod
    def _a_gemini_model(cls, value: str) -> str:
        """Design rule 7: the LLM is a Gemini model on Vertex AI, and no other service."""
        cleaned = value.strip()
        if not re.fullmatch(r"gemini-[a-z0-9][a-z0-9.\-]*", cleaned):
            raise ValueError("must be the id of a Gemini model, for example gemini-3.8-flash")
        return cleaned

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
