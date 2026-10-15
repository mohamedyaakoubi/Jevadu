"""The website: S1, the search with its filters, and S2, the project card (design 12.1).

Every page also has the states of design 12.1: nothing asked yet, nothing found, and something
failed, each in plain words with what to do. When Google cannot be reached, the search still
runs on the words of the idea and says so.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.conninfo import make_conninfo

from hackathon_memory.collect.ethglobal import data_paths
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.pipeline.embed import FAILED_CALLS
from hackathon_memory.search import compare as comparing
from hackathon_memory.search import engine, listing
from hackathon_memory.search import filters as filtering
from hackathon_memory.settings import Settings, SettingsError
from hackathon_memory.web import data

HERE = Path(__file__).parent
FIRST = 10
# Without a limit, a connection to a database that does not answer waits 130 seconds (the
# default of psycopg, measured on 15 October 2026): a page would hang that long before it says
# that the database is not running.
CONNECT_SECONDS = 5
LONGEST_IDEA = 1000  # letters; a longer idea is cut, and the page says so
FACTS_SECONDS = 60  # the facts of the filters are read again after a minute
SEARCH_PARAMS = ("idea", "event", "year", "category", "proof", "life")
FILTER_WORDS = {"event": "the event", "year": "the year", "category": "the category",
                "proof": "the Hedera proof", "life": "the life"}  # fmt: skip
NO_SUCH_PROJECT = "There is no project with this number. Go back to the search."
DATABASE_DOWN = (
    "The database is not running, so nothing can be searched. Start Docker Desktop, then run "
    '"docker compose up -d --wait db" in the folder of the project, and load this page again.'
)


def search_query(values: dict[str, str]) -> str:
    """The part of an address that repeats a search: the idea and the chosen filters."""
    return urlencode({k: v for k, v in values.items() if k in SEARCH_PARAMS and v})


def create_app(settings: Settings | None = None, google: Any = None, llm: Any = None) -> FastAPI:
    """The website. `google` is the client for the embeddings and `llm` the one for the
    comparison; by default each is made, counted by the meter, when it is first needed."""
    settings = settings or Settings()
    app = FastAPI(title="Hackathon Memory", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    clients: dict[str, Any] = {"google": google, "llm": llm}
    cache: dict[str, Any] = {"facts": None, "at": 0.0}

    def database() -> str:
        return make_conninfo(settings.database_conninfo(), connect_timeout=CONNECT_SECONDS)

    def google_client() -> Any:
        if clients["google"] is None:
            from hackathon_memory.finops.meter import metered_client

            clients["google"] = metered_client(settings, "embed_query")
        return clients["google"]

    def llm_client() -> Any:
        if clients["llm"] is None:
            from hackathon_memory.finops.meter import metered_client

            clients["llm"] = metered_client(settings, "compare")
        return clients["llm"]

    def project_facts(conninfo: str) -> list[filtering.Facts]:
        """The facts of every project for the filters, read at most once a minute."""
        if cache["facts"] is None or time.monotonic() - cache["at"] > FACTS_SECONDS:
            cache["facts"] = filtering.facts(
                conninfo, model=settings.gemini_rewrite_model, version=INSTRUCTIONS_VERSION
            )
            cache["at"] = time.monotonic()
        return cache["facts"]

    def page(request: Request, name: str, status: int = 200, **values: Any) -> HTMLResponse:
        return templates.TemplateResponse(request, name, values, status_code=status)

    @app.get("/", response_class=HTMLResponse)
    def search(
        request: Request,
        idea: str = "",
        event: str = "",
        year: str = "",
        category: str = "",
        proof: str = "",
        life: str = "",
    ) -> HTMLResponse:
        idea = " ".join(idea.split())
        cut = len(idea) > LONGEST_IDEA
        idea = idea[:LONGEST_IDEA]
        asked = filtering.Filters(event, year, category, proof, life)
        down = {"problem": DATABASE_DOWN, "results": [], "offer": None, "chosen": asked}
        try:
            conninfo = database()
            offer = filtering.choices(project_facts(conninfo))
        except (SettingsError, psycopg.OperationalError):
            if not idea:  # the start page needs no database; the filters wait for it
                return page(request, "search.html", idea="", asked=False, **down)
            return page(request, "search.html", 503, idea=idea, asked=True, **down)
        notes = []
        unknown = [name for name, value in asked.chosen().items() if not offer.knows(name, value)]
        if unknown:
            notes.append("No project has the value given for "
                         + " or ".join(FILTER_WORDS[name] for name in unknown)
                         + ", so that filter was left out.")  # fmt: skip
        chosen = filtering.Filters(**{k: v for k, v in asked.chosen().items() if k not in unknown})
        shown = {"chosen": chosen, "offer": offer,
                 "search_query": search_query({"idea": idea, **chosen.chosen()})}  # fmt: skip
        if not idea:
            return page(request, "search.html", idea="", results=[], asked=False, notes=notes,
                        **shown)  # fmt: skip
        only = filtering.allowed(project_facts(conninfo), chosen)
        try:
            model = settings.gemini_embedding_model
            try:
                hits = engine.search(conninfo, google_client(), idea, model=model, limit=FIRST,
                                     only=only)  # fmt: skip
            except (*FAILED_CALLS, BudgetExceeded):
                hits = engine.merge([], engine.by_words(conninfo, idea, limit=FIRST, only=only))
                notes.append(
                    "Google could not be asked about the meaning of the idea just now, so "
                    "only its words were searched. Try again later for the full search."
                )
            found = listing.cards(conninfo, hits)
            summaries = data.summaries(
                conninfo,
                [card.hit.project_id for card in found],
                model=settings.gemini_rewrite_model,
                version=INSTRUCTIONS_VERSION,
            )
        except (SettingsError, psycopg.OperationalError):
            return page(request, "search.html", 503, idea=idea, asked=True, **down)
        if cut:
            notes.append(f"The idea was longer than {LONGEST_IDEA} letters, so it was cut.")
        results = [(card, summaries.get(card.hit.project_id)) for card in found]
        return page(request, "search.html", idea=idea, results=results, asked=True, notes=notes,
                    nothing_matches=only == [], **shown)  # fmt: skip

    @app.get("/project/{project_id}", response_class=HTMLResponse)
    def project(request: Request, project_id: int, idea: str = "") -> HTMLResponse:
        try:
            card = data.project_card(
                database(),
                project_id,
                model=settings.gemini_rewrite_model,
                version=INSTRUCTIONS_VERSION,
                raw_dir=data_paths(settings).raw_dir,
            )
        except (SettingsError, psycopg.OperationalError):
            return page(request, "project.html", 503, card=None, idea=idea,
                        problem=DATABASE_DOWN)  # fmt: skip
        if card is None:
            return page(request, "project.html", 404, card=None, idea=idea,
                        problem=NO_SUCH_PROJECT)  # fmt: skip
        back = search_query(dict(request.query_params))
        return page(request, "project.html", card=card, idea=idea, back_query=back)

    @app.get("/compare", response_class=HTMLResponse)
    def comparison(request: Request, idea: str = "", ids: str = "") -> HTMLResponse:
        """What is the same and what differs, for the first results of an idea (design 8.3):
        a part of a page, asked for after the results are shown."""
        idea = " ".join(idea.split())[:LONGEST_IDEA]
        try:
            project_ids = [int(part) for part in ids.split(",") if part.strip()][:FIRST]
        except ValueError:
            project_ids = []
        if not idea or not project_ids:
            return page(request, "_compare.html", 400, found={}, failed=True)
        failures = (SettingsError, psycopg.OperationalError, comparing.CompareError,
                    BudgetExceeded, *FAILED_CALLS)  # fmt: skip
        try:
            items = comparing.items_for(
                database(), project_ids, model=settings.gemini_rewrite_model,
                version=INSTRUCTIONS_VERSION,
            )  # fmt: skip
            found = comparing.compare(
                llm_client(), idea, items, model=settings.gemini_search_model,
                thinking_level=settings.gemini_search_thinking_level,
            )  # fmt: skip
        except failures:
            return page(request, "_compare.html", 503, found={}, failed=True)
        return page(request, "_compare.html", found=found, failed=False)

    templates.env.globals |= {
        "PRIZE_WORDS": listing.PRIZE_WORDS,
        "STATUS_WORDS": listing.STATUS_WORDS,
        "CODE_WORDS": listing.CODE_WORDS,
        "WINNER_ENTRY": "winner_entry",
        "hashscan": data.hashscan,
        "TEXT_WORDS": {
            "name": "the name",
            "short_line": "the short line",
            "page_text": "the project's text",
            **data.FIELD_TITLES,
        },
    }
    return app
