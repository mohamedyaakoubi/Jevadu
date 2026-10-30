"""The website: the search (S1), the card of a project over it (S2), the check of a submission
(S3) and its registration on Hedera (S4), the charts of a list (S5), the method (S6) and the graph
of a list (S7), on one page (design 12.1, fourth version, on Tabler).

While an idea is typed, the page shows quick results, by meaning or by words, with no model that
writes. Only the button "Order and compare with Gemini" calls the search model: it orders the 30
closest in meaning and compares the first ten with the idea. What the models answered is kept for
one day under the fingerprint of the idea (db/idea_answers.py), so a reload, the back button or
the same search again never asks twice. With JavaScript, htmx loads each part in place and keeps
the address up to date; without it, every link and form loads a whole page that shows the same.

Every page also has the states of design 12.1: nothing asked yet, nothing found, and something
failed, each in plain words with what to do. When Google cannot be reached, the words of the idea
are searched and the page says so.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode

import httpx
import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import escape
from psycopg.conninfo import make_conninfo
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from hackathon_memory import __version__
from hackathon_memory.check import submission
from hackathon_memory.check.history import MAX_EVENTS
from hackathon_memory.check.life import NOT_OVER
from hackathon_memory.check.proof import PROOF_FOUND
from hackathon_memory.collect import github
from hackathon_memory.collect.answers import Answers
from hackathon_memory.collect.ethglobal import data_paths
from hackathon_memory.collect.github_commits import FOUND as VERSION_FOUND
from hackathon_memory.collect.github_facts import FOUND as CODE_FOUND
from hackathon_memory.collect.github_facts import GONE as CODE_GONE
from hackathon_memory.collect.github_facts import saved_facts
from hackathon_memory.collect.github_readmes import FOUND as README_FOUND
from hackathon_memory.collect.github_readmes import saved_readme
from hackathon_memory.collect.polite import CollectorRefused
from hackathon_memory.db import readings
from hackathon_memory.db.embeddings import EmbeddingStore, idea_fingerprint
from hackathon_memory.db.idea_answers import AnswerStore, scope_of
from hackathon_memory.db.runs import recorded_run
from hackathon_memory.example_ideas import EXAMPLE_IDEAS
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.hedera import listed, registry, signing
from hackathon_memory.hedera.mirror import (
    MIRROR_URLS,
    MirrorError,
    MirrorNode,
    hashscan_topic,
    hashscan_transaction,
)
from hackathon_memory.hedera.register import RegisterError
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.llm.client import credentials_of, vercel_token
from hackathon_memory.pipeline import refresh as refresh_step
from hackathon_memory.pipeline.embed import FAILED_CALLS
from hackathon_memory.search import closeness, engine, listing, rerank, seen, stand_in
from hackathon_memory.search import compare as comparing
from hackathon_memory.search import counts as counting
from hackathon_memory.search import filters as filtering
from hackathon_memory.settings import Settings, SettingsError
from hackathon_memory.web import (
    charts,
    checks,
    code_reading,
    data,
    evidence,
    graph,
    hackathons,
    insights,
    references,
    strips,
    turnstile,
)
from hackathon_memory.web import public as public_copy
from hackathon_memory.web import refresher as refreshing

HERE = Path(__file__).parent


class Revalidated(StaticFiles):
    """The files of /static, with an answer that asks a browser to check its copy each time it uses
    one: "not modified" when it is the newest, which costs nothing (design 12.2, 28 October 2026: a
    browser that kept an earlier site.js showed the buttons of the strip of days, which did
    nothing). The hook is StaticFiles.file_response of Starlette 1.8.0 (staticfiles.py)."""

    def file_response(self, *args: Any, **kwargs: Any) -> Any:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


_FINGERPRINTS: dict[tuple[str, int, int], str] = {}


def static_url(name: str) -> str:
    """The address of one of the site's own files, with a fingerprint of its content: a browser
    asks for it again as soon as it changes."""
    path = HERE / "static" / name
    stat = path.stat()
    key = (name, stat.st_mtime_ns, stat.st_size)
    if key not in _FINGERPRINTS:
        _FINGERPRINTS[key] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return f"/static/{name}?v={_FINGERPRINTS[key]}"


LOG = logging.getLogger(__name__)
PAGE_SIZE = 10  # projects on one page, of the list and of the results
SHOWN = 50  # a search shows its 50 closest projects
# Without a limit, a connection to a database that does not answer waits 130 seconds (the
# default of psycopg, measured on 15 October 2026): a page would hang that long before it says
# that the database is not running.
CONNECT_SECONDS = 5
# The longest idea, from its cost. Each 1,000 characters add about 250 tokens to the embedding of
# the idea (0.20 dollars a million) and to the comparison at the level LOW (0.75 dollars a
# million): about 0.024 cent a search. A search with Gemini costs about 0.7 cent (the order and
# the comparison, measured on 15 and 16 October 2026), so 4,000 characters, a whole description
# of a project, keep it within about 0.1 cent of a one-line idea. The embedding model reads about
# 30,000 characters, and the server takes addresses of up to 64 KB (__main__.py).
LONGEST_IDEA = 4000
FACTS_SECONDS = 60  # the facts of the filters are read again after a minute
# The comparison is given up after this time. At the level LOW it took 7.5 s in the middle,
# but the service is sometimes much slower (35 to 200 s, measured on 16 October 2026).
COMPARE_SECONDS = 30
# The order by the model took 2 s in the middle; the service is sometimes much slower, so the
# order by meaning is kept after this time, and the page says so.
RERANK_SECONDS = 8
# The stand-in of the search model (search/stand_in.py), from its measure of 24 October 2026
# (evals/results/20261024T051625Z-search-fallback.json): with no thinking it found 40 of 57, and
# 38 on "high", which took 123 s in the middle; 49 of its 56 orders came within 7 s, the other 7
# in 29 to 47 s. Its comparisons were not measured, so they wait as long as Gemini's.
STAND_IN_LEVEL = rerank.OPEN_OFF
STAND_IN_RERANK_SECONDS = 10
STAND_IN_COMPARE_SECONDS = COMPARE_SECONDS
MEANING, WORDS = engine.MEANING, engine.WORDS
MODES = (MEANING, WORDS)
# The page opens on keyword search (design 12.1, S1, 28 October 2026): it needs no call to
# Google, so it answers when Google does not; semantic search is one click away.
DEFAULT_MODE = WORDS
FILTERS = ("event", "year", "category", "proof", "life", "winner")
SEARCH_PARAMS = ("idea", "mode", "ai", *FILTERS, "view")
CHARTS = "charts"
GRAPH = "graph"
VIEWS = (CHARTS, GRAPH)  # the views beside the cards, each named in the address
FILTER_WORDS = {"event": "the event", "year": "the year", "category": "the category",
                "proof": "the Hedera proof", "life": "the life", "winner": "the prize"}  # fmt: skip
EXAMPLES = EXAMPLE_IDEAS  # what the search learns about them is kept for good
# The block of the readings of a card (design 7.3, S2): who read, the steps of a reading as
# pipeline/refresh.py says them, and a failure of the reading by the kind of its error.
READING_BY = {
    readings.BUTTON: "read again by a visitor",
    readings.ROUND: "read again by the website",
    readings.REFRESH: "read again by the daily reading",
}
READING_STEP_WORDS = {
    refresh_step.GITHUB: "GitHub: the facts, the README, the newest commit",
    refresh_step.CODE: "The code, when its commit is new",
    refresh_step.LEDGER: "Its Hedera IDs on the ledger",
    refresh_step.HISTORIES: "The new transactions of its own IDs",
    refresh_step.CONTRACTS: "What the calls of its contracts reached",
}
READING_PROBLEMS = {
    "CollectorRefused": "GitHub refused the reading, or its limit for today is reached.",
    "MirrorError": "The mirror node did not answer.",
    "OperationalError": "The database did not answer.",
    "SettingsError": "The website is missing a setting for GitHub or the database.",
    "ReadTimeout": "GitHub or the mirror node did not answer in time.",
    "ConnectError": "There was no connection to GitHub or the mirror node.",
}
PROOF_SHORT = {
    "proof_found": "found",
    "window_not_known": "event end not known yet",
    "dates_do_not_fit": "dates don't fit",
    "found_but_empty": "empty ID",
    "another_kind": "wrong kind of ID",
    "cannot_be_checked": "can't be checked",
    "not_found": "ID not found",
    "no_id_given": "no ID given",
    filtering.NOT_CHECKED: "not checked yet",
    submission.NOT_ASKED: "no answer from the ledger",
    # A check with no hackathon: the ledger knows IDs, and their dates wait for one. "found, dates
    # not judged", in grey, was not understood (24 October 2026).
    "dates_not_judged": "IDs found, no hackathon chosen",
}
NO_SUCH_PROJECT = "There is no project with this ID. Close this window and search again."
SERVER_FAILED = (
    "Something went wrong on the server, so this cannot be shown. Please try again in a minute."
)
DATABASE_DOWN = (
    "The database of this site is not answering, so this cannot be shown. Try again in a minute. "
    'If you run the site: start Docker Desktop, run "docker compose up -d --wait db" in the '
    "project folder, then reload this page."
)
# What the page says when Gemini gives no order (design 8.2). Before 24 October 2026 it said "did
# not respond in time" also for errors that came back in 5 seconds.
AI_LATE = (
    "Gemini did not answer within {seconds} seconds, so the results are in the search order. Try "
    "the button again: after {left} more failure{s} in a row, {stand_in} takes its place for "
    "{minutes} minutes."
)
AI_FAILED = (
    "Gemini failed to give an order just now, so the results are in the search order. Try the "
    "button again: after {left} more failure{s} in a row, {stand_in} takes its place for "
    "{minutes} minutes."
)
AI_SPENT = "The budget for AI calls is spent, so the results are in the search order."
STAND_IN_USED = (
    "Gemini failed {failures} times in a row, so {stand_in} put these results in order. Gemini is "
    "asked again after {minutes} minutes."
)
BOTH_FAILED = (
    "Neither Gemini nor {stand_in}, which takes its place when it fails, gave an order just now, "
    "so the results are in the search order. Try again in a few minutes."
)
GOOGLE_AWAY = (
    "Semantic search is not available just now (Google's embedding service did not respond), "
    "so these are keyword results. Try again later."
)
GOOGLE_AWAY_CHECK = (
    "The most similar past projects cannot be shown just now: Google's embedding service did "
    "not respond. Try again later."
)
MEANING_SPENT = "The budget for AI calls is spent, so these are keyword results."
CHECK_SPENT = "The most similar past projects cannot be shown: the budget for AI calls is spent."
NO_PAGE_EMBEDDINGS = "The projects have no embeddings yet, so these are keyword results."
UNKNOWN_SHEET = "Page not found. Close this window."
NO_SUCH_PAGE = "This page does not exist. The search is on the start page."
NOT_A_REPOSITORY = (
    "This is not a GitHub repository link. Paste one such as github.com/owner/project, "
    "then try again."
)
CHECK_LOST = (
    "This check is no longer kept, for example because the server restarted. Check the "
    "submission again."
)
NO_EVENT = "That hackathon is not in the list. Pick one from the list, or none, and try again."
NO_DAYS = (
    "Enter the start and end dates of the hackathon; the end cannot come before the start. "
    "Or choose no hackathon to see the dates without judging them."
)
NO_VERSION = (
    "The latest commit could not be read from GitHub, so it cannot be registered. Check the "
    "repository again in a moment."
)
EVENT_FOR_REGISTER = (
    "Registering needs a hackathon. Check the repository again with its hackathon selected, "
    "then register it."
)
CLOSEST = 5  # the closest past projects that the check of a submission shows
NO_README_TO_SEARCH = (
    "This repository has no README, so no similar past project can be found. Describe its "
    "idea in the search box instead."
)
NOT_AN_ACCOUNT = "A Hedera account ID looks like 0.0.12345. Leave it empty to register without one."
# The signature of a team's own wallet (design 9.6, 29 October 2026).
NOT_SIGNED_RIGHT = "The signature came back incomplete from the wallet. Sign again."
# The public copy (web/public.py, design 12.5, 29 October 2026).
PUBLIC_AI_OFF = (
    "On this public copy of Jevadu, the AI is turned off, so these are keyword results. The search "
    "by meaning and the AI's order work on the full version, shown in the video."
)
PUBLIC_REGISTER_OFF = (
    "On this public copy of Jevadu, registering on Hedera is paused for now. Everything else of "
    "the check works."
)
PUBLIC_USED = (
    "This public copy of Jevadu gives each visitor {count} {what}, one time only, and you have "
    "used {them}{so}. The full version, shown in the video, has no such limit."
)
# The public copy with Cloudflare's Turnstile (web/turnstile.py, 30 October 2026).
PERSON_FIRST = (
    "Before it uses Gemini, GitHub or Hedera for you, this public copy of Jevadu asks Cloudflare "
    "whether you are a person. This usually takes a second, with nothing to click; if a box "
    "appears at the bottom right of the page, tick it. Then try again."
)
PUBLIC_WHAT = {
    public_copy.AI: ("ask of Gemini", "asks of Gemini"),
    public_copy.EMBED: ("search by meaning", "searches by meaning"),
    public_copy.CHECK: ("check", "checks"),
    public_copy.REFRESH: ("reading again", "readings again"),
    public_copy.REGISTER: ("registration", "registrations"),
}
SIGNED_OLD_COMMIT = (
    "A new commit reached the repository after you signed: the record must name the latest one. "
    "Sign again, then register."
)
NO_SUCH_SIGNER = (
    "The account {account} is not on the Hedera test network. Sign with an account of it."
)
NO_ACCOUNT_FOR_ADDRESS = (
    "This MetaMask address has no Hedera account on the test network yet. Send it some test "
    "HBAR from the faucet of portal.hedera.com, which makes the account, then sign again."
)
CHECK_FIRST = "Check the repository first: only a repository that GitHub shows can be registered."
NO_LINE = (
    "The README on GitHub does not contain the line {line} yet. Add it to the README on the "
    "default branch, then click the button again. It proves that the repository is yours, and "
    "that you agree to the record."
)
NOT_LISTED = (
    "Registering needs a hackathon from the list, so that every team of one hackathon names it "
    "the same way. Pick it in the list. Custom dates can be checked, but not registered."
)
REGISTER_CLOSED = (
    "The public register is not open yet: its topic on Hedera testnet has not been created."
)
# What a refusal of the network means for the register, by the name of Hedera's status
# (hedera/register.py, RegisterError.status); any other says that the network refused it.
REGISTER_REFUSED = {
    "INSUFFICIENT_PAYER_BALANCE": "the site's Hedera account has run out of HBAR",
    "INVALID_SIGNATURE": "the network did not accept the site's key",
    "INVALID_TOPIC_ID": "the register's topic was not found on the network",
    "TOPIC_EXPIRED": "the register's topic has expired",
    "BUSY": "Hedera testnet was busy",
    "PLATFORM_NOT_ACTIVE": "Hedera testnet was not ready",
    "PLATFORM_TRANSACTION_NOT_CREATED": "Hedera testnet was not ready",
}
REGISTER_FAILED = "Nothing was registered: {why}. Try again in a minute."
REGISTER_UNREAD = (
    "The register could not be read from the mirror node just now, so nothing can be "
    "written. Try again in a moment."
)
NOT_YET_VISIBLE = (
    "The record was sent to Hedera, but the mirror node does not show it yet. Check the "
    "repository again in a minute: it will be listed among its registrations."
)
# The mirror node for a page: one more try after 2 seconds, not three over a minute.
MIRROR_SECONDS = 10.0
MIRROR_PAUSES = (2.0,)
IDEA_CUT = f"Your idea was longer than {LONGEST_IDEA:,} characters, so it was shortened."
# The groups of a graph are kept this long: the whole collection takes about 4 seconds, and its
# embeddings change only when the pipeline runs. At most GRAPHS_KEPT lists are kept.
GRAPH_SECONDS = 600
GRAPHS_KEPT = 16
GRAPH_TOO_MANY = (
    "These filters keep {count:,} projects, and the graph draws at most {most}. Choose an event "
    "or a category to see fewer."
)
GRAPH_TOO_FEW = (
    "A graph needs at least two projects with an embedding. Remove a filter to see more."
)
SHEETS = {"how": ("How it works", "_about_how.html"),
          "questions": ("Common questions", "_about_questions.html"),
          "sources": ("Sources and references", "_about_sources.html")}  # fmt: skip


def day(value: date) -> str:
    """A date as the pages write it: 6 July 2025."""
    return f"{value.day} {value:%B %Y}"


def moment(value: datetime) -> str:
    """A moment with its time, in UTC: 16 October 2026, 18:42:07 UTC."""
    return f"{day(value)}, {value:%H:%M:%S} UTC"


@dataclass
class RegisterView:
    """What the box of the register shows before its button (design 12.1, S4)."""

    open: bool
    network: str = "testnet"
    topic_id: str = ""
    code: str = ""  # the fingerprint of the repository
    event: str = ""  # the event, as the register names it
    earlier: list = field(default_factory=list)  # the registrations of this code, oldest first
    same_event: Any = None  # the registration of this code for this event, if there is one
    problem: str | None = None
    line: str = ""  # the line that the team adds to its README before the registration
    line_found: bool = False  # the README that the check read carries it already


def iso_day(value: str) -> str:
    """A date written 2026-10-14 in a result file, as the pages write it: 14 October 2026."""
    try:
        return day(date.fromisoformat(value))
    except (TypeError, ValueError):
        return value


def github_reads(code: Any, readme: Any, version: Any) -> str:
    """On which day GitHub was read for a check, in one sentence. What was read on the same day
    is named together: "Read from GitHub: its facts and its README on 16 October 2026, the
    version on 18 October 2026"."""
    days: dict[str, list[str]] = {}
    if code is not None:
        days.setdefault(code.fetched_at[:10], []).append("the repository details")
    if readme is not None and readme.status == "found":
        name = f" ({readme.name})" if readme.name else ""
        days.setdefault(readme.fetched_at[:10], []).append(f"the README{name}")
    if version is not None and version.status == "found":
        days.setdefault(version.fetched_at[:10], []).append("the latest commit")

    def joined(items: list[str]) -> str:
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]

    if len(days) == 1:
        ((when, items),) = days.items()
        return f"Fetched from GitHub on {iso_day(when)}: {joined(items)}."
    each = [f"{joined(items)} on {iso_day(when)}" for when, items in sorted(days.items())]
    return f"Fetched from GitHub: {', '.join(each)}." if each else ""


def search_query(values: dict[str, str], *, drop: tuple[str, ...] = ()) -> str:
    """The part of an address that repeats a search: the idea, the way, Gemini's order when it was
    asked for, the filters and the view. The defaults need no word in the address."""
    kept = {k: v for k, v in values.items() if k in SEARCH_PARAMS and v and k not in drop}
    if kept.get("mode") == DEFAULT_MODE:
        del kept["mode"]
    if kept.get("ai") != "1":
        kept.pop("ai", None)
    if kept.get("view") not in VIEWS:
        kept.pop("view", None)
    return urlencode(kept)


def page_numbers(page: int, pages: int) -> list[int | None]:
    """The numbers of a row of pages: the first, the last, and two on each side of this one;
    None stands for the numbers left out."""
    wanted = sorted({1, pages, *range(max(1, page - 2), min(pages, page + 2) + 1)})
    numbers: list[int | None] = []
    for number in wanted:
        if numbers and number - numbers[-1] > 1:
            numbers.append(None if number - numbers[-1] > 2 else number - 1)
        numbers.append(number)
    return numbers


def used_up(count: int, kind: str, so: str = "") -> str:
    """The words for a visitor of the public copy whose allowance of `kind` is used, with what
    follows from it (design 12.5)."""
    one, many = PUBLIC_WHAT[kind]
    return PUBLIC_USED.format(
        count=count,
        what=one if count == 1 else many,
        them="it" if count == 1 else "them",
        so=f", so {so}" if so else "",
    )


def create_app(
    settings: Settings | None = None,
    google: Any = None,
    llm: Any = None,
    *,
    github_client: Any = None,
    mirrors: Mapping[str, Any] | None = None,
    register_writer: Any = None,
    stand_in_client: Any = None,
    turnstile_client: httpx.Client | None = None,
    refresh_inline: bool = False,
    rehearsal: bool = False,
    public: bool = False,
    serverless: bool = False,
) -> FastAPI:
    """The website. `google` is the client for the embeddings and `llm` the one for the search
    model; by default each is made, counted by the meter, when it is first needed. The check of
    a submission asks GitHub with `github_client` and the ledger with `mirrors`; by default they
    are made when first needed, with the promises of collect/github.py. `register_writer` writes
    one record to the register (hedera/registry.py); by default it is made when first needed.
    `stand_in_client` asks the stand-in of the search model (search/stand_in.py); by default it
    is made, counted by the meter, when it is first needed. `turnstile_client` asks Cloudflare
    whether a visitor of the public copy is a person (web/turnstile.py); by default it is made
    when first needed. `refresh_inline` reads a card again on the thread of its request, for the
    tests (web/refresher.py). With `rehearsal`, the topic of `settings` is the one for
    rehearsals, and every page says so (design 9.3). With `public`, it is
    the public copy, with the switches and the counts of web/public.py, and the calls it makes are
    counted against its own budget (design 12.5); with the keys of Turnstile in `settings`, a
    visitor confirms being a person first. With `serverless`, it runs as functions on a host
    such as Vercel, where a request may land on any copy and nothing runs between requests: a
    check and a reading again are done within their request, and no round runs in the
    background (web/vercel_app.py)."""
    settings = settings or Settings()
    if public:
        settings = settings.model_copy(update={"llm_environment": "public"})
    app = FastAPI(title="Jevadu", docs_url=None, redoc_url=None, openapi_url=None)
    # The graph of the whole collection is a page of about 0.8 MB, a tenth of it compressed. Level
    # 6 is zlib's own default: almost as small as 9, and faster.
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)
    app.mount("/static", Revalidated(directory=HERE / "static"), name="static")
    asks_person = bool(settings.turnstile_site_key
                       and settings.turnstile_secret_key.get_secret_value())  # fmt: skip
    limits = (public_copy.Limits(lambda: database(), settings.public_ai_per_visitor,
                                 needs_pass=asks_person)
              if public else None)  # fmt: skip
    gate = limits.admit if limits is not None else None  # the meter asks it before each call
    salt = settings.public_salt.get_secret_value()

    @app.middleware("http")
    async def unlisted(request: Request, call_next: Callable) -> Any:
        """No page is indexed (design 12.5); on the public copy, each request knows its visitor;
        on Vercel, the token that signs in to Google with no key goes with it (llm/client.py)."""
        token = None
        if limits is not None and public_copy.plain_http(request.headers):
            return RedirectResponse(str(request.url.replace(scheme="https")), 301)
        if limits is not None:
            peer = request.client.host if request.client else None
            token = public_copy.visitor.set(
                public_copy.visitor_of(request.headers, peer, salt, settings.public_address_header)
            )
        oidc = request.headers.get("x-vercel-oidc-token")
        signed = vercel_token.set(oidc) if oidc else None
        try:
            response = await call_next(request)
        finally:
            if token is not None:
                public_copy.visitor.reset(token)
            if signed is not None:
                vercel_token.reset(signed)
        extra = public_copy.PUBLIC_HEADERS if limits is not None else {}
        for name, value in {**public_copy.HEADERS, **extra}.items():
            response.headers[name] = value
        return response

    @app.get("/health")
    def health() -> JSONResponse:
        """For whoever runs the site: whether it reaches its database and, when it signs in to
        Google with no key (llm/client.py), whether Google takes the sign-in. Nothing is paid: a
        sign-in is free, and no model is asked."""
        report: dict[str, bool | None] = {"database": False, "google": None}
        try:
            with psycopg.connect(database()) as conn:
                conn.execute("SELECT 1")
            report["database"] = True
        except (SettingsError, psycopg.Error):
            pass
        if settings.google_federation_audience and settings.google_federation_account:
            from google.auth.exceptions import GoogleAuthError
            from google.auth.transport.requests import Request as GoogleRequest

            signed = cache.get("signed") or credentials_of(settings)
            cache["signed"] = signed  # a pass lasts an hour: not asked again before
            try:
                if not signed.valid:
                    signed.refresh(GoogleRequest())
                report["google"] = True
            except GoogleAuthError:
                report["google"] = False
        return JSONResponse(report, status_code=200 if report["database"] else 503)

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots() -> str:
        return public_copy.ROBOTS

    @app.post("/person-check")
    async def person_check(request: Request) -> Response:
        """On the public copy with Turnstile: the token that its widget gave the page, spent here
        at once (web/turnstile.py). 204 when the visitor is a person, kept for PASS_HOURS; 403
        when Cloudflare says no, and the page asks the widget for a new token; 503 when
        Cloudflare or the database cannot answer."""
        if not asks_person or limits is None:
            raise StarletteHTTPException(404)
        body = (await request.body()).decode("utf-8", "replace")
        token = (parse_qs(body).get("token") or [""])[0]
        return await run_in_threadpool(person_kept, public_copy.visitor.get(), token)

    def person_kept(who: public_copy.Visitor | None, token: str) -> Response:
        if who is None or limits is None:
            return Response(status_code=403)
        if clients["turnstile"] is None:
            clients["turnstile"] = httpx.Client()
        secret = settings.turnstile_secret_key.get_secret_value()
        try:
            if not turnstile.is_person(clients["turnstile"], secret, token):
                return Response(status_code=403)
            limits.keep_pass(who)
        except turnstile.Unreachable as error:
            LOG.warning("Cloudflare's Turnstile did not answer: %s", error)
            return Response(status_code=503)
        except psycopg.Error as error:
            LOG.warning("the pass of a visitor was not kept: %s", type(error).__name__)
            return Response(status_code=503)
        return Response(status_code=204)

    def allowed(kind: str) -> bool:
        """On the public copy, whether the visitor of this request may do `kind` once more, out
        of an allowance that is never renewed; always on the laptop's own site."""
        return limits is None or limits.take(kind, public_copy.visitor.get())

    def ai_closed() -> bool:
        """On the public copy, a call to a model is refused while the AI is off; every caller
        then falls back as for a spent budget. What each visitor may still ask is counted by the
        meter, just before each call (public_copy.Limits.admit)."""
        return limits is not None and not limits.on(public_copy.AI)

    def used(kind: str, so: str = "") -> str:
        """The words for a visitor whose allowance of `kind` on the public copy is used."""
        return used_up(limits.allowance[kind] if limits is not None else 0, kind, so)

    def person() -> bool:
        """Whether the visitor of this request may have Gemini, GitHub or Hedera used for them:
        on the public copy with Turnstile, once Cloudflare found them to be a person
        (web/turnstile.py); always on the laptop's own site."""
        return limits is None or limits.passed(public_copy.visitor.get())

    def gemini_closed(idea: str) -> bool:
        """On the public copy, whether the visitor may no longer ask Gemini's order for `idea`: an
        ask counted before stays open, since its answers cost nothing more."""
        if limits is None:
            return False
        who, key = public_copy.visitor.get(), public_copy.press_key(idea, "order")
        return not limits.pressed(who, key) and limits.left(public_copy.AI, who) == 0

    templates = Jinja2Templates(directory=HERE / "templates")
    jobs = checks.CheckJobs()  # the checks that run while their page waits
    app.state.check_jobs = jobs
    rerank_given = llm.tagged(purpose="rerank") if llm is not None else None
    clients: dict[str, Any] = {"google": google, "llm": llm, "rerank": rerank_given,
                               "github": github_client, "mirrors": mirrors,
                               "writer": register_writer, "stand_in": stand_in_client,
                               "turnstile": turnstile_client}  # fmt: skip
    if gate is not None:  # on the public copy, every model passes the visitor's gate
        for name in ("google", "llm", "rerank", "stand_in"):
            if clients[name] is not None:
                clients[name] = clients[name].gated(gate)
    breaker = stand_in.Breaker()  # Gemini's failures in a row (design 8.2)
    answers = Answers(github.raw_dir(settings))  # GitHub's newest answers (design 7.3)
    app.state.breaker = breaker
    cache: dict[str, Any] = {"facts": None, "at": 0.0}
    graphs: dict[tuple, tuple[float, Any]] = {}  # the groups of a list, with when they were made

    def database() -> str:
        return make_conninfo(settings.database_conninfo(), connect_timeout=CONNECT_SECONDS)

    def client(name: str, purpose: str, press: str | None = None) -> Any:
        """The client `name`, counted under `purpose`. On the public copy, it carries the ask of
        Gemini that it answers (public_copy.press_key), which the visitor's gate counts once."""
        if ai_closed():
            raise BudgetExceeded("The AI is turned off on this public copy.")
        if clients[name] is None:
            from hackathon_memory.finops.meter import metered_client

            clients[name] = metered_client(settings, purpose, gate=gate)
        if limits is None:
            return clients[name]
        return clients[name].tagged(purpose=purpose, item_ref=press)

    def standing_in(purpose: str, press: str | None = None) -> Any:
        """The client of the stand-in of the search model, counted under `purpose`, with the ask
        of Gemini that it answers in its place."""
        if ai_closed():
            raise BudgetExceeded("The AI is turned off on this public copy.")
        if clients["stand_in"] is None:
            from hackathon_memory.llm.open_models import open_models

            clients["stand_in"] = open_models(settings, purpose, gate=gate)
        if limits is None:
            return clients["stand_in"].tagged(purpose=purpose)
        return clients["stand_in"].tagged(purpose=purpose, item_ref=press)

    def told(words: str) -> str:
        """A message about Gemini and its stand-in, with the numbers of the switch."""
        left = breaker.left()
        return words.format(seconds=RERANK_SECONDS, left=left, s="s" if left != 1 else "",
                            stand_in=stand_in.NAME, failures=stand_in.FAILURES,
                            minutes=int(stand_in.SECONDS // 60))  # fmt: skip

    def project_facts(conninfo: str) -> list[filtering.Facts]:
        """The facts of every project for the filters, read at most once a minute."""
        if cache["facts"] is None or time.monotonic() - cache["at"] > FACTS_SECONDS:
            cache["facts"] = filtering.facts(
                conninfo, model=settings.gemini_rewrite_model, version=INSTRUCTIONS_VERSION
            )
            cache["at"] = time.monotonic()
        return cache["facts"]

    def card_of(conninfo: str, project_id: int) -> data.ProjectCard | None:
        return data.project_card(conninfo, project_id, model=settings.gemini_rewrite_model,
                                 version=INSTRUCTIONS_VERSION,
                                 raw_dir=data_paths(settings).raw_dir)  # fmt: skip

    def readme_idea(repo: str) -> str:
        """The words of the README that the check of a repository saved, or "" when there is
        none. Nothing is asked of GitHub here."""
        repository = submission.repository_link(repo[:300])
        if repository is None:
            return ""
        readme = saved_readme(answers, repository)
        if readme is None or readme.status != README_FOUND:
            return ""
        return submission.readme_words(readme.text)

    def linked_to(conninfo: str, project_id: int) -> list[tuple[str, Any]]:
        """The projects linked to one project (design 8.4): each with why, and its name."""
        found = seen.links_of(conninfo, project_id)
        named = data.members(conninfo, [[pid] for pid, _ in found])
        return [(by, group[0]) for (_, by), group in zip(found, named, strict=True) if group]

    def kept_comparisons(conninfo: str, idea: str, ids: list[int]) -> dict[int, Any]:
        """The comparisons of the last day for this idea, by project, for those of `ids` that
        have one: never asked here."""
        if not idea or not ids:
            return {}
        items = comparing.items_for(conninfo, ids, model=settings.gemini_rewrite_model,
                                    version=INSTRUCTIONS_VERSION)  # fmt: skip
        if not items:
            return {}
        return AnswerStore(conninfo).comparisons(
            idea_fingerprint(idea),
            {item.project_id: comparing.input_fingerprint(item) for item in items},
            settings.gemini_search_model, settings.gemini_search_thinking_level,
            comparing.INSTRUCTIONS_VERSION,
        )  # fmt: skip

    def kept_comparison(conninfo: str, idea: str, project_id: int) -> Any:
        """The comparison of the last day for this idea and project, or None: never asked here."""
        return kept_comparisons(conninfo, idea, [project_id]).get(project_id)

    def render(request: Request, name: str, status: int = 200, **values: Any) -> HTMLResponse:
        if asks_person and limits is not None and not name.startswith("_"):  # a whole page
            # the box of Cloudflare's Turnstile, until the visitor is found to be a person
            values.setdefault("person_check", None if person() else settings.turnstile_site_key)
        return templates.TemplateResponse(request, name, values, status_code=status)

    def facts_of(conninfo: str, ids: list[int] | None) -> list[filtering.Facts]:
        """The facts of the projects of `ids`, in the order of the tables, or of every project."""
        rows = project_facts(conninfo)
        if ids is None:
            return rows
        wanted = set(ids)
        return [row for row in rows if row.project_id in wanted]

    def charts_of(
        conninfo: str, ids: list[int] | None
    ) -> tuple[charts.Charts, list, insights.Insights]:
        """The charts of the projects of `ids` (every project when None), those of them that are
        linked across events, by name, and the insights of the same list (design 12.1, S5)."""
        found = counting.tally(facts_of(conninfo, ids))
        built = charts.build(found, data.event_pages(conninfo))
        groups = seen.came_back(conninfo)
        if ids is not None:
            wanted = set(ids)
            groups = [group for group in groups if wanted.intersection(group)]
        members = data.members(conninfo, groups[:20])
        prize = {row.project_id: row.prize for row in project_facts(conninfo)}
        return built, members, insights.build(found, members, prize)

    def graph_of(
        conninfo: str, ids: list[int] | None, idea: str = ""
    ) -> tuple[graph.Graph | None, str | None, dict[int, dict[str, Any]]]:
        """The graph of the projects of `ids` (design 8.6, S7), closest first when there is an
        idea, with what each dot shows; or, in place of a graph, why there is none, in plain
        words. The embedding of the idea is the one that the search keeps for a day; without
        Google, the places in the list stand in for the distances in meaning."""
        if ids is None:  # no idea and no filter: the whole collection
            ids = [row.project_id for row in project_facts(conninfo)]
        if len(ids) > graph.MOST:
            return None, GRAPH_TOO_MANY.format(count=len(ids), most=graph.MOST), {}
        model = settings.gemini_embedding_model
        kept = closeness.with_embedding(conninfo, ids, model=model)
        order = [pid for pid in ids if pid in kept]
        if len(order) < 2:
            return None, GRAPH_TOO_FEW, {}
        found, centres, nearest, typical = grouped(conninfo, order, model)
        rows = {row.project_id: row for row in facts_of(conninfo, order)}
        (members,) = data.members(conninfo, [order])
        named = {member.project_id: member for member in members}
        lines = data.summaries(conninfo, order, model=settings.gemini_rewrite_model,
                               version=INSTRUCTIONS_VERSION)  # fmt: skip
        distance = None
        if idea:
            store = EmbeddingStore(conninfo)
            try:
                values = engine.idea_embedding(store, client("google", "embed_query"), idea,
                                               model=model)  # fmt: skip
                distance = dict(store.nearest(values, model, limit=len(order), only=order))
            except (*FAILED_CALLS, BudgetExceeded):
                distance = None
        built = graph.build(
            order, found, ranked=bool(idea), distance=distance, typical=typical,
            nearest=nearest, centres=centres,
            categories={pid: row.category for pid, row in rows.items()},
            names={pid: member.name for pid, member in named.items()},
            linked=seen.came_back(conninfo), left_out=len(ids) - len(order),
            listed={pid for pid, row in rows.items() if row.entry_kind == "winner_entry"},
            won={pid for pid, row in rows.items() if row.prize == "hedera_prize"},
            proven={pid for pid, row in rows.items() if row.proof == PROOF_FOUND},
        )  # fmt: skip
        about = {pid: {"name": named[pid].name, "event": named[pid].event,
                       "line": lines[pid].text if pid in lines else "",
                       "proof": rows[pid].proof if pid in rows else None,
                       "prize": rows[pid].prize if pid in rows else None}
                 for pid in order if pid in named}  # fmt: skip
        return built, None, about

    def grouped(conninfo: str, order: list[int], model: str) -> tuple:
        """The groups of the projects of `order` (design 8.6), their most central projects, the
        closest project of each, and how close each is to the most central one of its group.
        Kept for GRAPH_SECONDS under the list and the model."""
        key = (model, tuple(order))
        kept = graphs.get(key)
        if kept is not None and time.monotonic() - kept[0] < GRAPH_SECONDS:
            return kept[1]
        pairs = closeness.similarities(conninfo, order, model=model)
        found = closeness.groups(order, pairs, graph.group_count(len(order)))
        centres = [closeness.central(group, pairs) for group in found]
        typical = {pid: closeness.similarity(pairs, pid, centre)
                   for group, centre in zip(found, centres, strict=True)
                   for pid in group if pid != centre}  # fmt: skip
        made = (found, centres, closeness.nearest(order, pairs), typical)
        while len(graphs) >= GRAPHS_KEPT:
            graphs.pop(next(iter(graphs)))  # the oldest first
        graphs[key] = (time.monotonic(), made)
        return made

    def results_of(conninfo: str, ids: list[int], idea: str, words: bool) -> list[tuple]:
        """The card facts, the sentence, the marked sentence and the words found, of each id."""
        found = listing.cards(conninfo, [engine.Hit(pid, 0.0, None, None) for pid in ids])
        summaries = data.summaries(conninfo, ids, model=settings.gemini_rewrite_model,
                                   version=INSTRUCTIONS_VERSION)  # fmt: skip
        lines = {pid: one.text for pid, one in summaries.items() if one.text}
        marked = data.marked_lines(conninfo, lines, idea) if idea else {}
        snippets = data.matched_words(conninfo, ids, idea) if idea and words else {}
        return [(card, summaries.get(card.hit.project_id), marked.get(card.hit.project_id),
                 snippets.get(card.hit.project_id)) for card in found]  # fmt: skip

    def ranking_of(
        conninfo: str,
        idea: str,
        mode: str,
        only: list[int] | None,
        with_ai: bool,
        chosen: filtering.Filters,
        notes: list[str],
    ) -> tuple[list[int], str | None, str | None]:
        """The projects closest to the idea, closest first, at most SHOWN; where the model's
        order came from when it was asked for (search/rerank.py); and the name of the model
        that gave it: Gemini, or after its failures its stand-in (search/stand_in.py). When
        Google cannot be reached, the words.

        A filter keeps the projects of the SHOWN closest that have its values (design 8.2), so
        the number next to a value of a filter is the number of projects it leaves."""
        allowed = None if only is None else set(only)

        def narrowed(ids: list[int]) -> list[int]:
            return ids if allowed is None else [pid for pid in ids if pid in allowed]

        try:
            if only == []:
                return [], None, None
            if mode == WORDS:
                return narrowed(engine.by_words(conninfo, idea, limit=SHOWN)), None, None
            if not EmbeddingStore(conninfo).counts(settings.gemini_embedding_model)["embeddings"]:
                notes.append(NO_PAGE_EMBEDDINGS)
                return narrowed(engine.by_words(conninfo, idea, limit=SHOWN)), None, None
            ranking = narrowed(engine.by_meaning(
                EmbeddingStore(conninfo), client("google", "embed_query"), idea,
                model=settings.gemini_embedding_model, limit=SHOWN,
            ))  # fmt: skip
            if not (with_ai and ranking):
                return ranking, None, None
            pool, rest = ranking[: rerank.POOL], ranking[rerank.POOL :]
            scope = scope_of(chosen.chosen(), FILTERS)
            ask = public_copy.press_key(idea, "order")  # counted once on the public copy

            def spent() -> str:
                if gemini_closed(idea):
                    return used(public_copy.AI, "these results are in the search order")
                return AI_SPENT

            if not breaker.standing_in():
                order, how = rerank.order_pool(
                    conninfo, client("rerank", "rerank", ask), idea, pool,
                    model=settings.gemini_search_model,
                    level=settings.gemini_search_thinking_level, scope=scope,
                    timeout_seconds=RERANK_SECONDS,
                )  # fmt: skip
                if how in rerank.ORDERED:
                    if how == rerank.ASKED:
                        breaker.answered()
                    return order + rest, how, "Gemini"
                if how == rerank.SPENT:
                    notes.append(spent())
                    return ranking, how, None
                if not breaker.failed():
                    notes.append(told(AI_LATE if how == rerank.LATE else AI_FAILED))
                    return ranking, how, None
            order, how = rerank.order_pool(
                conninfo, standing_in("rerank", ask), idea, pool, model=stand_in.MODEL,
                level=STAND_IN_LEVEL, scope=scope, timeout_seconds=STAND_IN_RERANK_SECONDS,
            )  # fmt: skip
            if how in rerank.ORDERED:
                notes.append(told(STAND_IN_USED))
                return order + rest, how, stand_in.NAME
            notes.append(spent() if how == rerank.SPENT else told(BOTH_FAILED))
            return ranking, how, None
        except (*FAILED_CALLS, BudgetExceeded) as error:
            # the kind of error only, for whoever runs the site: an expired sign-in to Google
            # (RefreshError) needs a new one, which the page cannot ask for
            LOG.warning("the search by meaning fell back to the words: %s", type(error).__name__)
            if isinstance(error, public_copy.Refused):
                notes.append(used(public_copy.EMBED, "these are keyword results"))
            else:
                notes.append(MEANING_SPENT if isinstance(error, BudgetExceeded) else GOOGLE_AWAY)
            return narrowed(engine.by_words(conninfo, idea, limit=SHOWN)), None, None

    def search_offer(conninfo: str, idea: str, mode: str, ranking: list[int],
                     only: list[int] | None, every: filtering.Choices,
                     chosen: filtering.Filters) -> filtering.Choices:  # fmt: skip
        """What the filters offer for a search: the counts of its closest projects without the
        filters, so that each value says how many of them it would keep. The embedding of the
        idea is kept for a day, so this costs nothing more. A chosen value stays offered."""
        if only == []:  # no project matches the filters: nothing is searched, Google is not asked
            return every
        if only is None:
            ids = ranking
        else:
            ids, _, _ = ranking_of(conninfo, idea, mode, None, False, filtering.Filters(), [])
        return filtering.keep_chosen(filtering.choices(facts_of(conninfo, ids)), every, chosen)

    @app.get("/", response_class=HTMLResponse)
    def search(
        request: Request,
        idea: str = "",
        mode: str = "",
        ai: str = "",
        event: str = "",
        year: str = "",
        category: str = "",
        proof: str = "",
        life: str = "",
        winner: str = "",
        open: str = "",  # noqa: A002  (the name in the address)
        page: str = "1",
        view: str = "",
    ) -> HTMLResponse:
        idea = " ".join(idea.split())
        cut = len(idea) > LONGEST_IDEA
        idea = idea[:LONGEST_IDEA]
        if mode == "ai":  # the address of the second version of the page
            mode, ai = MEANING, "1"
        if not mode and ai == "1":  # Gemini orders the semantic results; an address of before
            mode = MEANING  # 28 October 2026 asked for its order with no mode
        mode = mode if mode in MODES else DEFAULT_MODE
        with_ai = ai == "1" and mode == MEANING and bool(idea)
        # The public copy with its AI off searches by keyword, and says so (design 12.5). So does a
        # visitor whose searches by meaning are used; one whose asks of Gemini are used keeps the
        # search order.
        ai_off = (limits is not None and bool(idea) and mode == MEANING
                  and not limits.on(public_copy.AI))  # fmt: skip
        public_note = PUBLIC_AI_OFF if ai_off else None
        if ai_off:
            mode, with_ai = WORDS, False
        elif limits is not None and idea and mode == MEANING:
            if limits.left(public_copy.EMBED, public_copy.visitor.get()) == 0:
                mode, with_ai = WORDS, False
                public_note = used(public_copy.EMBED, "these are keyword results")
            elif with_ai and not person():  # the search by meaning needs no pass; Gemini does
                with_ai = False
                public_note = PERSON_FIRST
            elif with_ai and gemini_closed(idea):
                with_ai = False
                public_note = used(public_copy.AI, "these results are in the search order")
        view = CHARTS if view in (CHARTS, "overview") else view if view in VIEWS else ""
        page_number = int(page) if page.isdigit() and int(page) > 0 else 1
        open_id = int(open) if open.isdigit() else None
        asked = filtering.Filters(event, year, category, proof, life, winner)
        base = {"idea": idea, "mode": mode, "with_ai": with_ai, "view": view, "open_id": open_id,
                "elapsed": None, "compare_ids": [], "notes": []}  # fmt: skip
        down = {**base, "problem": DATABASE_DOWN, "results": [], "offer": None, "chosen": asked,
                "panel_card": None, "panel_problem": None, "search_query": ""}  # fmt: skip
        try:
            conninfo = database()
            every = filtering.choices(project_facts(conninfo))
        except (SettingsError, psycopg.OperationalError):
            if not idea:  # the start page needs no database; the list waits for it
                return render(request, "search.html", asked=False, **down)
            return render(request, "search.html", 503, asked=True, **down)
        notes = [public_note] if public_note else []
        unknown = [name for name, value in asked.chosen().items() if not every.knows(name, value)]
        if unknown:
            notes.append("No project has the value given for "
                         + " or ".join(FILTER_WORDS[name] for name in unknown)
                         + ", so that filter was left out.")  # fmt: skip
        chosen = filtering.Filters(**{k: v for k, v in asked.chosen().items() if k not in unknown})
        values = {"idea": idea, "mode": mode, "ai": "1" if with_ai else "", "view": view,
                  **chosen.chosen()}  # fmt: skip
        only = filtering.allowed(project_facts(conninfo), chosen)
        shown = {**base, "chosen": chosen, "search_query": search_query(values),
                 "quick_query": search_query(values, drop=("ai",)),
                 "ai_query": search_query({**values, "ai": "1", "mode": MEANING}),
                 "unfiltered_query": search_query(values, drop=FILTERS),
                 "cards_query": search_query(values, drop=("view",)),
                 "charts_query": search_query({**values, "view": CHARTS}),
                 "graph_query": search_query({**values, "view": GRAPH}),
                 "check_events": data.dated_events(conninfo), "all_projects": every.projects,
                 "shown_limit": SHOWN,
                 "with_category": every.with_category, "notes": notes}  # fmt: skip
        try:
            panel_card = card_of(conninfo, open_id) if open_id else None
            shown["panel_linked"] = linked_to(conninfo, open_id) if panel_card else []
            # a link to a project that is not in the collection opens the window with that sentence
            shown["panel_problem"] = NO_SUCH_PROJECT if open_id and panel_card is None else None
            if not idea:
                total = len(only) if only is not None else every.projects
                if view == CHARTS:
                    built, groups, said = charts_of(conninfo, only)
                    return render(request, "search.html", asked=False, results=[], total=total,
                                  charts=built, came_back=groups, insights=said, offer=every,
                                  panel_card=panel_card, **shown)  # fmt: skip
                if view == GRAPH:
                    drawn, why, about = graph_of(conninfo, only)
                    return render(request, "search.html", asked=False, results=[], total=total,
                                  graph=drawn, graph_problem=why, graph_about=about,
                                  offer=every, panel_card=panel_card, **shown)  # fmt: skip
                ids, total = data.browse(conninfo, only, offset=(page_number - 1) * PAGE_SIZE,
                                         limit=PAGE_SIZE)  # fmt: skip
                results = results_of(conninfo, ids, "", False)
                first = (page_number - 1) * PAGE_SIZE + 1
                return render(request, "search.html", asked=False, results=results, offer=every,
                              panel_card=panel_card, total=total, page=page_number,
                              pages=math.ceil(total / PAGE_SIZE), first_shown=first,
                              last_shown=first + len(results) - 1, **shown)  # fmt: skip
            began = time.perf_counter()
            ranking, how, sorted_by = ranking_of(conninfo, idea, mode, only, with_ai, chosen,
                                                 notes)  # fmt: skip
            elapsed = time.perf_counter() - began
            offer = search_offer(conninfo, idea, mode, ranking, only, every, chosen)
            if cut:
                notes.append(IDEA_CUT)
            ordered = how in rerank.ORDERED
            shown["sorted_by"] = sorted_by
            if limits is not None and not ai_off and mode == MEANING:  # after this search's ask
                shown["gemini_left"] = limits.left(public_copy.AI, public_copy.visitor.get())
            none_close = bool(only) and not ranking  # the filters match, but none is close
            if view == CHARTS:
                built, groups, said = charts_of(conninfo, ranking)
                return render(request, "search.html", asked=True, results=[], total=len(ranking),
                              charts=built, came_back=groups, insights=said, offer=offer,
                              nothing_matches=only == [], none_close=none_close,
                              panel_card=panel_card,
                              **{**shown, "elapsed": elapsed, "with_ai": ordered})  # fmt: skip
            if view == GRAPH:
                drawn, why, about = graph_of(conninfo, ranking, idea)
                return render(request, "search.html", asked=True, results=[], total=len(ranking),
                              graph=drawn, graph_problem=why, graph_about=about, offer=offer,
                              nothing_matches=only == [], none_close=none_close,
                              panel_card=panel_card,
                              **{**shown, "elapsed": elapsed, "with_ai": ordered})  # fmt: skip
            total = len(ranking)
            pages = max(1, math.ceil(total / PAGE_SIZE))
            page_number = min(page_number, pages)
            first = (page_number - 1) * PAGE_SIZE
            results = results_of(conninfo, ranking[first : first + PAGE_SIZE], idea, mode == WORDS)
            # a comparison kept for this idea shows on its card, wherever it was asked
            shown_ids = [card.hit.project_id for card, *_ in results]
            kept_compared = kept_comparisons(conninfo, idea, shown_ids)
        except (SettingsError, psycopg.OperationalError):
            return render(request, "search.html", 503, asked=True, **down)
        # Gemini compares the ten that it put first, on the first page only.
        compare_ids = [card.hit.project_id for card, *_ in results] if ordered else []
        compare_ids = compare_ids if page_number == 1 else []
        return render(request, "search.html", asked=True, results=results, total=total,
                      pages=pages, page=page_number, first_shown=first + 1,
                      last_shown=first + len(results), nothing_matches=only == [],
                      none_close=none_close, panel_card=panel_card, offer=offer,
                      kept_compared=kept_compared,
                      **{**shown, "elapsed": elapsed, "with_ai": ordered,
                         "compare_ids": compare_ids})  # fmt: skip

    def github_or_why() -> tuple[Any, str | None]:
        """The client that asks GitHub, or None with the reason in plain words."""
        if clients["github"] is None:
            if not settings.collect_github:
                return None, "GitHub may not be asked now: the switch COLLECT_GITHUB is off."
            try:
                clients["github"] = github.github_client(settings)
            except CollectorRefused as refused:
                return None, f"GitHub may not be asked now. {refused}"
        return clients["github"], None

    def mirror_nodes() -> Mapping[str, Any]:
        if clients["mirrors"] is None:
            clients["mirrors"] = {
                name: MirrorNode(name, timeout=MIRROR_SECONDS, pauses=MIRROR_PAUSES)
                for name in MIRROR_URLS
            }
        return clients["mirrors"]

    def event_days(conninfo: str, event: str, starts: str, ends: str) -> tuple[Any, str | None]:
        """The hackathon that a submission was sent to, with what went wrong in plain words.
        (None, None) when none is given: it is optional, since the tool is a memory of past
        hackathons and not a live view (design 12.1, S3)."""
        if not event:
            return None, None
        if event == "other":
            days = submission.typed_days(starts, ends)
            return (submission.event_of_days(*days), None) if days else (None, NO_DAYS)
        one = listed.listed(event)
        if one is not None:
            first = datetime(*one.first.timetuple()[:3], tzinfo=UTC) if one.first else None
            return submission.EventDays(one.name, first, one.last, key=one.key), None
        if not event.isdigit():
            return None, NO_EVENT
        with psycopg.connect(conninfo) as conn:
            row = conn.execute("SELECT name, starts_at, ends_on, site, slug FROM events "
                               "WHERE id = %s", (int(event),)).fetchone()  # fmt: skip
        if row is None:
            return None, NO_EVENT
        name, starts_at, ends_on, site, slug = row
        return submission.EventDays(name, starts_at, ends_on,
                                    key=registry.event_key(site, slug)), None  # fmt: skip

    def register_view(repository: str, days: submission.EventDays) -> RegisterView:
        """The register's records of this code, read from the mirror node (design 9.2)."""
        topic = settings.hedera_topic_id.strip()
        if not topic or settings.hedera_network != "testnet":
            return RegisterView(open=False)
        view = RegisterView(True, settings.hedera_network, topic,
                            registry.code_fingerprint(repository), days.key)  # fmt: skip
        view.line = registry.readme_line(view.event, view.code)
        try:
            found = registry.registrations(mirror_nodes()[view.network], topic)
        except MirrorError:
            view.problem = REGISTER_UNREAD
            return view
        view.earlier = [one for one in found if one.code == view.code]
        view.same_event = next((one for one in view.earlier if one.event == view.event), None)
        return view

    def refresh_work(
        projects: set[int] | None,
        older_than: timedelta,
        limit: int | None,
        step: Callable[[str], None],
    ) -> None:
        """Read again what is older than `older_than`, for `projects` (the button of a card) or for
        all (a round), and say each step to `step` (design 7.3)."""
        client, _ = github_or_why()
        conninfo = database()
        with recorded_run(conninfo, refresh_step.STEP) as run:
            refresh_step.refresh(conninfo, answers, client, mirror_nodes(), run,
                                 collector=f"{settings.collector_name.strip()}/{__version__}",
                                 older_than=older_than, limit=limit, projects=projects,
                                 source=readings.BUTTON if projects else readings.ROUND,
                                 step=step)  # fmt: skip

    age = timedelta(hours=settings.refresh_after_hours)
    reader = refreshing.Refresher(refresh_work, older_than=age,
                                  inline=refresh_inline or serverless)  # fmt: skip
    app.state.refresher = reader
    if settings.refresh_in_background and not serverless:
        reader.start_rounds()

    def writer_or_why() -> tuple[Any, str | None]:
        """What writes to the register, or None with the reason in plain words."""
        if clients["writer"] is None:
            try:
                node = mirror_nodes()[settings.hedera_network]
                clients["writer"] = registry.writer(settings, node)
            except (RegisterError, MirrorError) as error:
                return None, f"The register cannot be written now. {error}"
        return clients["writer"], None

    def closest_to(conninfo: str, check: submission.SubmissionCheck) -> tuple[list, str | None]:
        """The past projects closest in meaning to the README, without those seen before."""
        words = submission.readme_words(check.readme_text)
        if not words:
            return [], NO_README_TO_SEARCH
        try:
            ranking = engine.by_meaning(
                EmbeddingStore(conninfo), client("google", "embed_query"), words,
                model=settings.gemini_embedding_model, limit=CLOSEST + len(check.seen),
            )  # fmt: skip
        except public_copy.Refused:
            return [], used(public_copy.EMBED, "the most similar past projects cannot be shown")
        except BudgetExceeded:
            return [], CHECK_SPENT
        except FAILED_CALLS:
            return [], GOOGLE_AWAY_CHECK
        known = {one.project_id for one in check.seen}
        ids = [pid for pid in ranking if pid not in known][:CLOSEST]
        return results_of(conninfo, ids, "", False), None

    def check_answer(
        conninfo: str,
        repository: str,
        days: submission.EventDays | None,
        asked: dict[str, str],
        progress: checks.Progress = lambda step, state: None,
    ) -> tuple[int, dict[str, Any]]:
        """What the page of a check shows: its status, and the values of its template.
        `progress` hears each step start and end (web/checks.py)."""
        try:
            asker, why = github_or_why()
            result = submission.check_submission(
                conninfo, repository, days, client=asker,
                store=answers,
                collector=f"{settings.collector_name.strip()}/{__version__}",
                mirrors=mirror_nodes(), problems=[why] if why else [], progress=progress,
            )  # fmt: skip
            if result.code is not None and result.code.status == CODE_GONE and not result.seen:
                return 404, {"problem": submission.NO_SUCH_CODE}
            progress(checks.COLLECTION, checks.RUNNING)
            closest, note = closest_to(conninfo, result)
            groups = [[one.project_id] for one in result.seen]
            members = [group[0] for group in data.members(conninfo, groups)]
            progress(checks.COLLECTION, checks.DONE)
        except (SettingsError, psycopg.OperationalError):
            return 503, {"problem": DATABASE_DOWN}
        found = result.code is not None and result.code.status == CODE_FOUND
        listed_one = days is not None and not days.typed
        view = register_view(repository, days) if found and listed_one else None
        if view is not None and view.open:
            view.line_found = registry.carries_line(result.readme_text or "", view.line)
        seen_before = list(zip(result.seen, members, strict=True))
        # With no hackathon given: the hackathons where the collection holds the same code, so
        # that the team can register it for one of them at once.
        offers = []
        for one, member in seen_before:
            offer = (member.event_id, member.event)
            if one.by == "repository" and member.event_id is not None and offer not in offers:
                offers.append(offer)
        ends_on = days.ends_on if days is not None else None
        return 200, {
            "result": result, "closest": closest, "closest_note": note,
            "life_after": data.life_line(ends_on),
            "event_over": not (result.life and result.life.why == NOT_OVER),
            "seen_before": seen_before, "register": view, "register_offers": offers,
            "hedera_code": code_reading.view_of_read(repository, result.hedera_code),
            "readme_lines": (data.said_lines(submission.readme_prose(result.readme_text))
                             if result.story else []),  # fmt: skip
            "asked": asked,
        }  # fmt: skip

    @app.get("/check", response_class=HTMLResponse)
    def check(
        request: Request,
        repo: str = "",
        event: str = "",
        starts: str = "",
        ends: str = "",
        progress: str = "",
    ) -> HTMLResponse:
        """S3: the check of one submission (design 12.1), in the window over the page, or as a
        page of its own without JavaScript. Programs read every fact; no model writes. Asked by
        the page's script with progress=1, it runs in a thread of its own, and the window shows
        its steps until the answer is there (/check/progress)."""
        name = "_check.html" if request.headers.get("HX-Request") == "true" else "check.html"
        repository = submission.repository_link(repo[:300])
        if repository is None:
            return render(request, name, 400, problem=NOT_A_REPOSITORY)
        try:
            conninfo = database()
            days, wrong = event_days(conninfo, event, starts, ends)
        except (SettingsError, psycopg.OperationalError):
            return render(request, name, 503, problem=DATABASE_DOWN)
        if wrong:
            return render(request, name, 400, problem=wrong)
        if not person():
            return render(request, name, 403, problem=PERSON_FIRST)
        if not allowed(public_copy.CHECK):
            return render(request, name, 429, problem=used(public_copy.CHECK))
        asked = {"event": event, "starts": starts, "ends": ends}
        if name == "_check.html" and progress == "1" and not serverless:
            job = jobs.start(lambda report: check_answer(conninfo, repository, days, asked, report))
            return render(request, "_check_progress.html", view=jobs.view(job, announce=False),
                          repository=repository, event_name=days.name if days else None,
                          step_notes=evidence.check_notes())  # fmt: skip
        status, shown = check_answer(conninfo, repository, days, asked)
        return render(request, name, status, **shown)

    @app.get("/check/progress", response_class=HTMLResponse)
    def check_progress(request: Request, job: str = "") -> HTMLResponse:
        """The steps of a check that runs, or its answer in their place once it is there."""
        running = jobs.get(job[:40])
        if running is None:
            return in_window(render(request, "_check.html", 404, problem=CHECK_LOST))
        if running.answer is None:
            return render(request, "_check_steps.html", view=jobs.view(running),
                          step_notes=evidence.check_notes())  # fmt: skip
        jobs.forget(running.id)
        status, shown = running.answer
        return in_window(render(request, "_check.html", status, **(shown or
                                {"problem": SERVER_FAILED})))  # fmt: skip

    def in_window(response: HTMLResponse) -> HTMLResponse:
        """The answer takes the place of the whole window, not only of the steps."""
        response.headers["HX-Retarget"] = "#viewer-body"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    @app.post("/register", response_class=HTMLResponse)
    async def register_page(request: Request) -> HTMLResponse:
        """S4: write the record of a checked submission to the register on Hedera (design 9.2),
        read it back from the mirror node, and show the receipt."""
        body = (await request.body()).decode("utf-8", "replace")
        form = {key: values[0] for key, values in parse_qs(body).items()}
        return await run_in_threadpool(registered, request, form)

    def registered(request: Request, form: dict[str, str]) -> HTMLResponse:
        name = "_register.html" if request.headers.get("HX-Request") == "true" else "register.html"
        if limits is not None and not limits.on(public_copy.REGISTER):
            return render(request, name, 503, problem=PUBLIC_REGISTER_OFF)
        if not person():
            return render(request, name, 403, problem=PERSON_FIRST)
        if not allowed(public_copy.REGISTER):
            return render(request, name, 429, problem=used(public_copy.REGISTER))
        repository = submission.repository_link(form.get("repo", "")[:300])
        if repository is None:
            return render(request, name, 400, problem=NOT_A_REPOSITORY)
        # The team's own signature (design 9.6): its account, how its wallet signed, the
        # signature, and the commit that the signed text named.
        signer_text, scheme = form.get("signer", "").strip(), form.get("scheme", "").strip()
        signature, signed_commit = form.get("signature", "").strip(), form.get("signed_commit", "")
        signs = bool(signer_text or scheme or signature)
        signer = signing.account_of(signer_text) if signs else None
        if signs and signer is None:
            return render(request, name, 400, problem=NOT_AN_ACCOUNT)
        if signs and (scheme not in signing.SCHEMES or not signature):
            return render(request, name, 400, problem=NOT_SIGNED_RIGHT)
        try:
            days, wrong = event_days(database(), form.get("event", ""), form.get("starts", ""),
                                     form.get("ends", ""))  # fmt: skip
        except (SettingsError, psycopg.OperationalError):
            return render(request, name, 503, problem=DATABASE_DOWN)
        if days is None:
            return render(request, name, 400, problem=wrong or EVENT_FOR_REGISTER)
        if days.typed:
            return render(request, name, 400, problem=NOT_LISTED)
        code = saved_facts(answers, repository)
        if code is None or code.status != CODE_FOUND:
            return render(request, name, 400, problem=CHECK_FIRST)
        view = register_view(repository, days)
        if not view.open or view.problem:
            return render(request, name, 503, problem=view.problem or REGISTER_CLOSED)
        values = {"view": view, "network": view.network, "topic_id": view.topic_id}
        if view.same_event is not None:  # never written twice: the first record stands
            return render(request, name, done=view.same_event, already=True, **values)
        # The README and the version, read again now: the team's line must be in the README, and
        # the newest version is stamped. Each read is saved as the newest answer, with no answer
        # replaced (collect/answers.py).
        asker, why = github_or_why()
        if asker is None:
            return render(request, name, 503, problem=why)
        readme, version, problems = submission.read_again(
            asker, answers, repository,
            collector=f"{settings.collector_name.strip()}/{__version__}",
        )  # fmt: skip
        if problems:
            return render(request, name, 503, problem=problems[0])
        readme_text = readme.text if readme and readme.status == README_FOUND else ""
        if not registry.carries_line(readme_text, view.line):
            return render(request, name, 400, problem=NO_LINE.format(line=view.line))
        if version is None or version.status != VERSION_FOUND or version.sha is None:
            return render(request, name, 400, problem=NO_VERSION)
        payload = registry.record(view.event, view.code, version.sha)
        if signer is not None:  # checked against the key that the ledger shows for the account
            if signed_commit.strip() != version.sha:
                return render(request, name, 400, problem=SIGNED_OLD_COMMIT)
            try:
                key = signing.account_key(mirror_nodes()[view.network], signer)
                if key is None:
                    return render(request, name, 400, problem=NO_SUCH_SIGNER.format(account=signer))
                raw = signing.raw_signature(scheme, signature)
                text = signing.signed_text(view.event, view.code, version.sha, signer)
                signing.check(scheme, text, raw, key)
            except signing.SignatureError as error:
                return render(request, name, 400, problem=str(error))
            except MirrorError:
                return render(request, name, 503, problem=REGISTER_UNREAD)
            payload = registry.signed_record(
                view.event, view.code, version.sha, signer, scheme, raw
            )
        write, why = writer_or_why()
        if write is None:
            return render(request, name, 503, problem=why)
        try:
            done = registry.register_submission(write, mirror_nodes()[view.network],
                                                view.topic_id, payload)  # fmt: skip
        except RegisterError as error:
            why = (
                REGISTER_REFUSED.get(error.status, "the network refused the message")
                if error.status
                else "the site could not write the record"
            )
            LOG.warning("the register refused a record: %s", error)
            return render(request, name, 503, problem=REGISTER_FAILED.format(why=why))
        except MirrorError:
            return render(request, name, 202, problem=NOT_YET_VISIBLE)
        return render(request, name, done=done, already=False, **values)

    @app.get("/register/account")
    def register_account(address: str = "") -> JSONResponse:
        """The Hedera account of a MetaMask address, which the text that the team signs names
        (design 9.6). MetaMask knows only the address; the mirror node gives the account."""
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
            return JSONResponse({"problem": "This is not an address of MetaMask."}, 400)
        try:
            key = signing.account_key(mirror_nodes()["testnet"], address.lower())
        except MirrorError:
            return JSONResponse({"problem": REGISTER_UNREAD}, 503)
        if key is None:
            return JSONResponse({"problem": NO_ACCOUNT_FOR_ADDRESS}, 404)
        return JSONResponse({"account": key.account, "key": key.key_type})

    @app.get("/project/{project_id}", response_class=HTMLResponse)
    def project(request: Request, project_id: int) -> HTMLResponse:
        back = search_query(dict(request.query_params))
        try:
            conninfo = database()
            card = card_of(conninfo, project_id)
            linked = linked_to(conninfo, project_id) if card else []
        except (SettingsError, psycopg.OperationalError):
            return render(request, "project.html", 503, card=None, back_query=back,
                          problem=DATABASE_DOWN)  # fmt: skip
        if card is None:
            return render(request, "project.html", 404, card=None, back_query=back,
                          problem=NO_SUCH_PROJECT)  # fmt: skip
        return render(request, "project.html", card=card, back_query=back, idea="", linked=linked)

    @app.get("/project/{project_id}/panel", response_class=HTMLResponse)
    def project_panel(request: Request, project_id: int, idea: str = "") -> HTMLResponse:
        """The card of a project as a part of the search page, for the window over the list. With
        the idea, the comparison of the last day, when there is one; none is asked for here."""
        idea = " ".join(idea.split())[:LONGEST_IDEA]
        back = search_query(dict(request.query_params))
        try:
            conninfo = database()
            card = card_of(conninfo, project_id)
            kept = kept_comparison(conninfo, idea, project_id) if card and idea else None
            linked = linked_to(conninfo, project_id) if card else []
        except (SettingsError, psycopg.OperationalError):
            return render(request, "_problem.html", 503, problem=DATABASE_DOWN)
        if card is None:
            return render(request, "_problem.html", 404, problem=NO_SUCH_PROJECT)
        return render(request, "_panel.html", card=card, back_query=back, idea=idea,
                      kept_comparison=kept, linked=linked)  # fmt: skip

    def read_again_shown(
        request: Request, project_id: int, state: refreshing.State | None
    ) -> HTMLResponse:
        """The line of a card that reads its project again (design 7.3, S2): while it runs, it
        asks again every 2 seconds; when it is done, the card shows itself again, in its window,
        or as its page."""
        query = search_query(dict(request.query_params))
        if state is not None and state.status == refreshing.DONE:
            if request.query_params.get("page") == "1":
                done = HTMLResponse("")
                done.headers["HX-Refresh"] = "true"
                return done
            shown = project_panel(request, project_id, request.query_params.get("idea", ""))
            return in_window(shown)
        return render(request, "_read_again.html", project_id=project_id, state=state,
                      query=query, page=request.query_params.get("page") == "1")  # fmt: skip

    @app.post("/project/{project_id}/read-again", response_class=HTMLResponse)
    def read_again_now(request: Request, project_id: int) -> HTMLResponse:
        """S2: read GitHub and the mirror node again for one project, before the next round."""
        if not person():
            return HTMLResponse(f'<p class="hm-small">{escape(PERSON_FIRST)}</p>', 403)
        if not allowed(public_copy.REFRESH):
            words = used(public_copy.REFRESH)
            return HTMLResponse(f'<p class="hm-small">{escape(words)}</p>', 429)
        return read_again_shown(request, project_id, reader.ask(project_id))

    @app.get("/project/{project_id}/read-again", response_class=HTMLResponse)
    def read_again_state(request: Request, project_id: int) -> HTMLResponse:
        return read_again_shown(request, project_id, reader.state(project_id))

    @app.get("/compare", response_class=HTMLResponse)
    def comparison(
        request: Request,
        idea: str = "",
        ids: str = "",
        one: str = "",
        place: str = "",
        repo: str = "",
    ) -> HTMLResponse:
        """What is the same and what differs, for the first results of an idea (design 8.3), for
        one project in its window (`one`), or for the closest past projects of a checked
        submission (`place=check`), whose README stands for the idea: the address names the
        repository (`repo`), and the README is the one that the check saved, so its words never
        travel in the address. Kept from the last day, or asked now and kept."""
        if place == "check":
            idea = readme_idea(repo)
        idea = " ".join(idea.split())[:LONGEST_IDEA]
        try:
            project_ids = [int(part) for part in ids.split(",") if part.strip()][:PAGE_SIZE]
        except ValueError:
            project_ids = []
        place = {"one_place": one == "1", "check_place": place == "check",
                 "prefix": "check-compare-" if place == "check" else "compare-"}  # fmt: skip
        if not idea or not project_ids:
            return render(request, "_compare.html", 400, found={}, failed=True, asked_ids=[],
                          **place)  # fmt: skip
        if not person():
            return render(request, "_compare.html", 403, found={}, failed=True,
                          asked_ids=project_ids, refused=PERSON_FIRST, **place)  # fmt: skip
        failures = (SettingsError, psycopg.OperationalError, comparing.CompareError,
                    BudgetExceeded, *FAILED_CALLS, *rerank.NOT_ORDERED)  # fmt: skip
        # On the public copy, the comparison of the first ten counts with Gemini's order; a
        # project's own window and a check count once each.
        button = ("check" if place["check_place"] else
                  f"one:{project_ids[0]}" if place["one_place"] else "order")  # fmt: skip
        ask = public_copy.press_key(idea, button)

        def compared(conninfo: str, items: list, by_stand_in: bool) -> tuple[dict, int]:
            if by_stand_in:
                return comparing.kept_or_compared(
                    conninfo, standing_in("compare", ask), idea, items, model=stand_in.MODEL,
                    thinking_level=STAND_IN_LEVEL, timeout_seconds=STAND_IN_COMPARE_SECONDS,
                )  # fmt: skip
            return comparing.kept_or_compared(
                conninfo, client("llm", "compare", ask), idea, items,
                model=settings.gemini_search_model,
                thinking_level=settings.gemini_search_thinking_level,
                timeout_seconds=COMPARE_SECONDS,
            )  # fmt: skip

        by_stand_in = breaker.standing_in()
        try:
            conninfo = database()
            items = comparing.items_for(conninfo, project_ids, model=settings.gemini_rewrite_model,
                                        version=INSTRUCTIONS_VERSION)  # fmt: skip
            try:
                found, asked = compared(conninfo, items, by_stand_in)
                if asked and not by_stand_in:
                    breaker.answered()
            except (comparing.CompareError, *rerank.NOT_ORDERED) as error:
                # A failure of Gemini counts toward its stand-in (design 8.2); the one that ends
                # its turn hands the comparison to the stand-in at once.
                if by_stand_in or isinstance(error, BudgetExceeded) or not breaker.failed():
                    raise
                by_stand_in = True
                found, _ = compared(conninfo, items, by_stand_in)
        except public_copy.Refused:
            return render(request, "_compare.html", 429, found={}, failed=True,
                          asked_ids=project_ids, refused=used(public_copy.AI), **place)  # fmt: skip
        except failures:
            return render(request, "_compare.html", 503, found={}, failed=True,
                          asked_ids=project_ids, **place)  # fmt: skip
        return render(request, "_compare.html", found=found, failed=False, asked_ids=project_ids,
                      compared_by=stand_in.NAME if by_stand_in else "Gemini", **place)  # fmt: skip

    def about(request: Request, name: str) -> HTMLResponse:
        """A window of the bottom of the page: a part of a page for htmx, a whole page without."""
        if name not in SHEETS:
            return render(request, "_problem.html", 404, problem=UNKNOWN_SHEET)
        title, part = SHEETS[name]
        values = {"modes": evidence.measured_modes(), "test1": evidence.newest("test1-card-form-2"),
                  "test2": evidence.newest("test2"), "test3": evidence.newest("test3"),
                  "measured": evidence.newest("search-modes"),
                  "about_title": title, "about_part": part}  # fmt: skip
        if request.headers.get("HX-Request") == "true":
            return render(request, part, **values)
        return render(request, "about.html", **values)

    @app.get("/about/{name}", response_class=HTMLResponse)
    def about_page(request: Request, name: str) -> HTMLResponse:
        return about(request, name)

    @app.get("/method", response_class=HTMLResponse)
    def method(request: Request) -> HTMLResponse:
        """How the search works, and what the tests measured (design 12.1, S6)."""
        return about(request, "how")

    @app.exception_handler(StarletteHTTPException)
    def no_such_page(request: Request, error: StarletteHTTPException) -> HTMLResponse:
        """An address that the website does not have, or a method that it does not take: a page
        in plain words, not the framework's JSON."""
        name = "_problem.html" if request.headers.get("HX-Request") == "true" else "problem.html"
        problem = NO_SUCH_PAGE if error.status_code == 404 else SERVER_FAILED
        return render(request, name, error.status_code, problem=problem)

    @app.exception_handler(Exception)
    def unexpected(request: Request, error: Exception) -> HTMLResponse:
        """An error that no route answers in its own words. The page says so in plain words and
        never shows the error; Starlette 1.8.0 raises it again after this answer, so the server
        still writes it with its trace in its log (starlette/middleware/errors.py)."""
        del error
        name = "_problem.html" if request.headers.get("HX-Request") == "true" else "problem.html"
        return render(request, name, 500, problem=SERVER_FAILED)

    templates.env.filters["day"] = day
    templates.env.filters["moment"] = moment
    templates.env.filters["iso_day"] = iso_day
    templates.env.filters["said"] = data.said
    templates.env.filters["casefold"] = str.casefold
    templates.env.globals |= {
        "READING_BY": READING_BY,
        "READING_STEPS": list(refresh_step.STEPS),
        "READING_STEP_WORDS": READING_STEP_WORDS,
        "READING_PROBLEMS": READING_PROBLEMS,
        "PRIZE_WORDS": listing.PRIZE_WORDS,
        "STATUS_WORDS": listing.STATUS_WORDS,
        "PROOF_SHORT": PROOF_SHORT,
        "CODE_WORDS": listing.CODE_WORDS,
        "WINNER_ENTRY": "winner_entry",
        "NOT_ASKED": submission.NOT_ASKED,
        "CONFIRMED": seen.CONFIRMED,
        "MAX_IDS": submission.MAX_IDS,
        "RERANK_SECONDS": RERANK_SECONDS,
        # the model that orders the closest now: Gemini, or its stand-in (search/stand_in.py)
        "ordering_model": lambda: stand_in.NAME if breaker.standing_in() else "Gemini",
        "LONGEST_IDEA": LONGEST_IDEA,
        "EXAMPLES": EXAMPLES,
        "REFS": references.BY_KEY,
        "REF_NUMBER": references.NUMBER,
        "REFERENCES": references.REFERENCES,
        "hashscan": data.hashscan,
        "file_link": code_reading.file_link,
        "judged_of": data.judged_of,
        "strip_view": strips.strip_view,
        "hashscan_moment": hashscan_transaction,
        "rehearsal_topic": settings.hedera_topic_id.strip() if rehearsal else "",
        "WALLETCONNECT_PROJECT_ID": settings.walletconnect_project_id.strip(),
        "REFRESH_IN_BACKGROUND": settings.refresh_in_background,
        "PUBLIC_COPY": public,
        "reason_of": data.reason_of,
        "static_url": static_url,
        "lines_to_show": data.lines_to_show,
        "NETWORK_WORDS": data.NETWORK_WORDS,
        "ACTION_WORDS": data.ACTION_WORDS,
        "KIND_WORDS": data.KIND_WORDS,
        "SERVICE_NAMES": data.SERVICE_NAMES,
        "SERVICE_SUBJECTS": data.SERVICE_SUBJECTS,
        "SERVICE_TRANSACTIONS": data.SERVICE_TRANSACTIONS,
        "MAX_EVENTS": MAX_EVENTS,
        "read_only": data.read_only,
        "stopped_at": data.stopped_at,
        "hashscan_topic": hashscan_topic,
        "hackathon_groups": lambda collected: hackathons.groups(
            collected, listed.LISTED, datetime.now(UTC).date()
        ),
        "github_reads": github_reads,
        "page_numbers": page_numbers,
        "measured_mode": evidence.mode_named,
        "compare_numbers": lambda: evidence.compare_numbers(settings.gemini_search_thinking_level),
        "TEXT_WORDS": {
            "name": "the name",
            "short_line": "the short line",
            "page_text": "the project's text",
            **data.FIELD_TITLES,
        },
    }
    return app
