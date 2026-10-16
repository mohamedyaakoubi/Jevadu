"""The website: S1, the search with its filters, S2, the project card beside it, and the method.

One page holds the search: the idea at the top, the filters, the list, and the card of the chosen
project beside the list (over it, on a phone). With JavaScript, htmx loads each part in place and
keeps the address up to date, so the back button and a shared link work; without it, every link
and form loads a whole page that shows the same thing (design 12.1).

Every page also has the states of design 12.1: nothing asked yet, nothing found, and something
failed, each in plain words with what to do. When Google cannot be reached, the search still
runs on the words of the idea and says so.
"""

from __future__ import annotations

import time
from datetime import date
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
from hackathon_memory.web import data, evidence

HERE = Path(__file__).parent
FIRST = 10
PAGE_SIZE = 20  # projects in one page of the list when no idea is given
# Without a limit, a connection to a database that does not answer waits 130 seconds (the
# default of psycopg, measured on 15 October 2026): a page would hang that long before it says
# that the database is not running.
CONNECT_SECONDS = 5
# The longest idea, from its cost. Each 1,000 characters add about 250 tokens to the embedding of
# the idea (0.20 dollars a million) and to the comparison at the level LOW (0.75 dollars a
# million): about 0.024 cent a search. A search costs about 0.45 cent (the comparison, measured
# on 15 October 2026), so 4,000 characters, a whole description of a project, keep it within
# about 0.1 cent of a one-line idea. The embedding model reads about 30,000 characters, and the
# server takes addresses of up to 64 KB (__main__.py), so neither limit is reached first.
LONGEST_IDEA = 4000
FACTS_SECONDS = 60  # the facts of the filters are read again after a minute
# The comparison is given up after this time. At the level LOW it took 7.5 s in the middle,
# but the service is sometimes much slower (35 to 200 s, measured on 16 October 2026).
COMPARE_SECONDS = 30
SEARCH_PARAMS = ("idea", "mode", "event", "year", "category", "proof", "life")
FILTER_WORDS = {"event": "the event", "year": "the year", "category": "the category",
                "proof": "the Hedera proof", "life": "the life"}  # fmt: skip
NO_WORD_FOUND = (
    "No word of your idea was found in the projects searched, so these are only the closest "
    "in meaning. Check the spelling, or describe the idea in other words."
)
NO_SUCH_PROJECT = "There is no project with this number. Go back to the search."
DATABASE_DOWN = (
    "The database is not running, so nothing can be searched. Start Docker Desktop, then run "
    '"docker compose up -d --wait db" in the folder of the project, and load this page again.'
)
GOOGLE_AWAY = (
    "Google could not be asked about the meaning of the idea just now, so only its words were "
    "searched. Try again later for the full search."
)


def day(value: date) -> str:
    """A date as the pages write it: 6 July 2025."""
    return f"{value.day} {value:%B %Y}"


def iso_day(value: str) -> str:
    """A date written 2026-10-14 in a result file, as the pages write it: 14 October 2026."""
    try:
        return day(date.fromisoformat(value))
    except (TypeError, ValueError):
        return value


def search_query(values: dict[str, str]) -> str:
    """The part of an address that repeats a search: the idea, the mode and the filters."""
    kept = {k: v for k, v in values.items() if k in SEARCH_PARAMS and v}
    if kept.get("mode") == engine.BOTH:
        del kept["mode"]  # the default needs no word in the address
    return urlencode(kept)


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

    def card_of(conninfo: str, project_id: int) -> data.ProjectCard | None:
        return data.project_card(conninfo, project_id, model=settings.gemini_rewrite_model,
                                 version=INSTRUCTIONS_VERSION,
                                 raw_dir=data_paths(settings).raw_dir)  # fmt: skip

    def render(request: Request, name: str, status: int = 200, **values: Any) -> HTMLResponse:
        return templates.TemplateResponse(request, name, values, status_code=status)

    @app.get("/", response_class=HTMLResponse)
    def search(
        request: Request,
        idea: str = "",
        mode: str = engine.BOTH,
        event: str = "",
        year: str = "",
        category: str = "",
        proof: str = "",
        life: str = "",
        open: str = "",  # noqa: A002  (the name in the address)
        page: str = "1",
    ) -> HTMLResponse:
        idea = " ".join(idea.split())
        cut = len(idea) > LONGEST_IDEA
        idea = idea[:LONGEST_IDEA]
        mode = mode if mode in engine.MODES else engine.BOTH
        page_number = int(page) if page.isdigit() and int(page) > 0 else 1
        open_id = int(open) if open.isdigit() else None
        asked = filtering.Filters(event, year, category, proof, life)
        base = {"idea": idea, "mode": mode, "modes": evidence.search_modes(), "open_id": open_id,
                "nav": "search", "LONGEST_IDEA": LONGEST_IDEA, "elapsed": None}  # fmt: skip
        down = {**base, "problem": DATABASE_DOWN, "results": [], "offer": None, "chosen": asked,
                "panel_card": None, "search_query": ""}  # fmt: skip
        try:
            conninfo = database()
            offer = filtering.choices(project_facts(conninfo))
        except (SettingsError, psycopg.OperationalError):
            if not idea:  # the start page needs no database; the list waits for it
                return render(request, "search.html", asked=False, **down)
            return render(request, "search.html", 503, asked=True, **down)
        notes = []
        unknown = [name for name, value in asked.chosen().items() if not offer.knows(name, value)]
        if unknown:
            notes.append("No project has the value given for "
                         + " or ".join(FILTER_WORDS[name] for name in unknown)
                         + ", so that filter was left out.")  # fmt: skip
        chosen = filtering.Filters(**{k: v for k, v in asked.chosen().items() if k not in unknown})
        query = search_query({"idea": idea, "mode": mode, **chosen.chosen()})
        only = filtering.allowed(project_facts(conninfo), chosen)
        shown = {**base, "chosen": chosen, "offer": offer, "search_query": query}
        try:
            panel_card = card_of(conninfo, open_id) if open_id else None
            if not idea:
                ids, total = data.browse(conninfo, only, offset=(page_number - 1) * PAGE_SIZE,
                                         limit=PAGE_SIZE)  # fmt: skip
                found = listing.cards(conninfo, [engine.Hit(pid, 0.0, None, None) for pid in ids])
                summaries = data.summaries(conninfo, ids, model=settings.gemini_rewrite_model,
                                           version=INSTRUCTIONS_VERSION)  # fmt: skip
                results = [(card, summaries.get(card.hit.project_id), None, None)
                           for card in found]  # fmt: skip
                first = (page_number - 1) * PAGE_SIZE + 1
                return render(request, "search.html", asked=False, notes=notes, results=results,
                            panel_card=panel_card, total=total, page=page_number,
                            page_size=PAGE_SIZE, first_shown=first,
                            last_shown=first + len(results) - 1, **shown)  # fmt: skip
            began = time.perf_counter()
            try:
                hits = engine.search(conninfo, google_client(), idea, mode=mode, limit=FIRST,
                                     model=settings.gemini_embedding_model, only=only)  # fmt: skip
            except (*FAILED_CALLS, BudgetExceeded):
                hits = engine.merge([], engine.by_words(conninfo, idea, limit=FIRST, only=only))
                notes.append(GOOGLE_AWAY)
            elapsed = time.perf_counter() - began
            if hits and mode != engine.MEANING and all(hit.words_rank is None for hit in hits):
                notes.append(NO_WORD_FOUND)
            found = listing.cards(conninfo, hits)
            ids = [card.hit.project_id for card in found]
            summaries = data.summaries(conninfo, ids, model=settings.gemini_rewrite_model,
                                       version=INSTRUCTIONS_VERSION)  # fmt: skip
            lines = {pid: one.text for pid, one in summaries.items() if one.text}
            marked = data.marked_lines(conninfo, lines, idea)
            # The part of the page where the words stand, when the search is by words only.
            snippets = data.matched_words(conninfo, ids, idea) if mode == engine.WORDS else {}
        except (SettingsError, psycopg.OperationalError):
            return render(request, "search.html", 503, asked=True, **down)
        if cut:
            notes.append(f"The idea was longer than {LONGEST_IDEA:,} characters, so it was cut.")
        results = [(card, summaries.get(card.hit.project_id), marked.get(card.hit.project_id),
                    snippets.get(card.hit.project_id)) for card in found]  # fmt: skip
        return render(request, "search.html", asked=True, results=results, notes=notes,
                    nothing_matches=only == [], panel_card=panel_card,
                    **{**shown, "elapsed": elapsed})  # fmt: skip

    @app.get("/project/{project_id}", response_class=HTMLResponse)
    def project(request: Request, project_id: int) -> HTMLResponse:
        back = search_query(dict(request.query_params))
        try:
            card = card_of(database(), project_id)
        except (SettingsError, psycopg.OperationalError):
            return render(request, "project.html", 503, card=None, back_query=back,
                        problem=DATABASE_DOWN)  # fmt: skip
        if card is None:
            return render(request, "project.html", 404, card=None, back_query=back,
                        problem=NO_SUCH_PROJECT)  # fmt: skip
        return render(request, "project.html", card=card, back_query=back)

    @app.get("/project/{project_id}/panel", response_class=HTMLResponse)
    def project_panel(request: Request, project_id: int) -> HTMLResponse:
        """The card of a project as a part of the search page, for the panel beside the list."""
        back = search_query(dict(request.query_params))
        try:
            card = card_of(database(), project_id)
        except (SettingsError, psycopg.OperationalError):
            return render(request, "_problem.html", 503, problem=DATABASE_DOWN)
        if card is None:
            return render(request, "_problem.html", 404, problem=NO_SUCH_PROJECT)
        return render(request, "_panel.html", card=card, back_query=back)

    @app.get("/compare", response_class=HTMLResponse)
    def comparison(request: Request, idea: str = "", ids: str = "") -> HTMLResponse:
        """What is the same and what differs, for the first results of an idea (design 8.3):
        a part of a page, asked for after the results are shown. Each part replaces the
        waiting words of its result."""
        idea = " ".join(idea.split())[:LONGEST_IDEA]
        try:
            project_ids = [int(part) for part in ids.split(",") if part.strip()][:FIRST]
        except ValueError:
            project_ids = []
        if not idea or not project_ids:
            return render(request, "_compare.html", 400, found={}, failed=True, asked_ids=[])
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
                timeout_seconds=COMPARE_SECONDS,
            )  # fmt: skip
        except failures:
            return render(request, "_compare.html", 503, found={}, failed=True,
                        asked_ids=project_ids)  # fmt: skip
        return render(request, "_compare.html", found=found, failed=False, asked_ids=project_ids)

    @app.get("/method", response_class=HTMLResponse)
    def method(request: Request) -> HTMLResponse:
        """How the search works, and what the tests measured (design 12.1, S6)."""
        return render(request, "method.html", nav="method", modes=evidence.search_modes(),
                    test1=evidence.newest("test1-card-form-2"), test2=evidence.newest("test2"),
                    measured=evidence.newest("search-modes"))  # fmt: skip

    templates.env.filters["day"] = day
    templates.env.filters["iso_day"] = iso_day
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
