"""The website: the search (S1), the card of a project over it (S2), the charts of a list (S5)
and the method (S6), on one page (design 12.1, fourth version, on Tabler).

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

import math
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
from hackathon_memory.db.embeddings import EmbeddingStore, idea_fingerprint
from hackathon_memory.db.idea_answers import AnswerStore, scope_of
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.pipeline.embed import FAILED_CALLS
from hackathon_memory.search import compare as comparing
from hackathon_memory.search import counts as counting
from hackathon_memory.search import engine, listing, rerank, seen
from hackathon_memory.search import filters as filtering
from hackathon_memory.settings import Settings, SettingsError
from hackathon_memory.web import charts, data, evidence, references

HERE = Path(__file__).parent
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
MEANING, WORDS = engine.MEANING, engine.WORDS
MODES = (MEANING, WORDS)
FILTERS = ("event", "year", "category", "proof", "life")
SEARCH_PARAMS = ("idea", "mode", "ai", *FILTERS, "view")
CHARTS = "charts"
FILTER_WORDS = {"event": "the event", "year": "the year", "category": "the category",
                "proof": "the Hedera proof", "life": "the life"}  # fmt: skip
EXAMPLES = ("limits on what an AI agent may spend", "tracking coffee from the farm to the cup",
            "a ticket market without scalpers")  # fmt: skip
PROOF_SHORT = {
    "proof_found": "found",
    "window_not_known": "end of the event not typed in",
    "dates_do_not_fit": "dates do not fit",
    "found_but_empty": "ID empty",
    "another_kind": "another kind of ID",
    "cannot_be_checked": "cannot be checked",
    "not_found": "ID not found",
    "no_id_given": "no ID given",
    filtering.NOT_CHECKED: "not checked yet",
}
NO_SUCH_PROJECT = "There is no project with this number. Close this window and search again."
DATABASE_DOWN = (
    "The database is not running, so nothing can be searched. Start Docker Desktop, then run "
    '"docker compose up -d --wait db" in the folder of the project, and load this page again.'
)
AI_LATE = (
    "Gemini did not answer in time, so the projects are in the order of meaning. Press the "
    "button again in a moment for its order."
)
GOOGLE_AWAY = (
    "Google could not be asked about the meaning of the idea just now, so only its words were "
    "searched. Try again later for the search by meaning."
)
NO_PAGE_EMBEDDINGS = (
    "The projects have no embeddings yet, so only the words of the idea were searched."
)
UNKNOWN_SHEET = "There is no such page. Close this window."
IDEA_CUT = f"The idea was longer than {LONGEST_IDEA:,} characters, so it was cut."
SHEETS = {"how": ("How it works", "_about_how.html"),
          "questions": ("Common questions", "_about_questions.html"),
          "sources": ("Sources and references", "_about_sources.html")}  # fmt: skip


def day(value: date) -> str:
    """A date as the pages write it: 6 July 2025."""
    return f"{value.day} {value:%B %Y}"


def iso_day(value: str) -> str:
    """A date written 2026-10-14 in a result file, as the pages write it: 14 October 2026."""
    try:
        return day(date.fromisoformat(value))
    except (TypeError, ValueError):
        return value


def search_query(values: dict[str, str], *, drop: tuple[str, ...] = ()) -> str:
    """The part of an address that repeats a search: the idea, the way, Gemini's order when it was
    asked for, the filters and the view. The defaults need no word in the address."""
    kept = {k: v for k, v in values.items() if k in SEARCH_PARAMS and v and k not in drop}
    if kept.get("mode") == MEANING:
        del kept["mode"]
    if kept.get("ai") != "1":
        kept.pop("ai", None)
    if kept.get("view") != CHARTS:
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


def create_app(settings: Settings | None = None, google: Any = None, llm: Any = None) -> FastAPI:
    """The website. `google` is the client for the embeddings and `llm` the one for the search
    model; by default each is made, counted by the meter, when it is first needed."""
    settings = settings or Settings()
    app = FastAPI(title="Hackathon Memory", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    rerank_given = llm.tagged(purpose="rerank") if llm is not None else None
    clients: dict[str, Any] = {"google": google, "llm": llm, "rerank": rerank_given}
    cache: dict[str, Any] = {"facts": None, "at": 0.0}

    def database() -> str:
        return make_conninfo(settings.database_conninfo(), connect_timeout=CONNECT_SECONDS)

    def client(name: str, purpose: str) -> Any:
        if clients[name] is None:
            from hackathon_memory.finops.meter import metered_client

            clients[name] = metered_client(settings, purpose)
        return clients[name]

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

    def kept_comparison(conninfo: str, idea: str, project_id: int) -> Any:
        """The comparison of the last day for this idea and project, or None: never asked here."""
        items = comparing.items_for(conninfo, [project_id], model=settings.gemini_rewrite_model,
                                    version=INSTRUCTIONS_VERSION)  # fmt: skip
        if not idea or not items:
            return None
        kept = AnswerStore(conninfo).comparisons(
            idea_fingerprint(idea), {project_id: comparing.input_fingerprint(items[0])},
            settings.gemini_search_model, settings.gemini_search_thinking_level,
            comparing.INSTRUCTIONS_VERSION,
        )  # fmt: skip
        return kept.get(project_id)

    def render(request: Request, name: str, status: int = 200, **values: Any) -> HTMLResponse:
        return templates.TemplateResponse(request, name, values, status_code=status)

    def facts_of(conninfo: str, ids: list[int] | None) -> list[filtering.Facts]:
        """The facts of the projects of `ids`, in the order of the tables, or of every project."""
        rows = project_facts(conninfo)
        if ids is None:
            return rows
        wanted = set(ids)
        return [row for row in rows if row.project_id in wanted]

    def charts_of(conninfo: str, ids: list[int] | None) -> tuple[charts.Charts, list]:
        """The charts of the projects of `ids` (every project when None), and those of them that
        are linked across events, by name (design 12.1, S5)."""
        built = charts.build(counting.tally(facts_of(conninfo, ids)), data.event_pages(conninfo))
        groups = seen.came_back(conninfo)
        if ids is not None:
            wanted = set(ids)
            groups = [group for group in groups if wanted.intersection(group)]
        return built, data.members(conninfo, groups[:20])

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
    ) -> tuple[list[int], str | None]:
        """The projects closest to the idea, closest first, at most SHOWN, and where Gemini's
        order came from when it was asked for. When Google cannot be reached, the words."""
        try:
            if only == []:
                return [], None
            if mode == WORDS:
                return engine.by_words(conninfo, idea, limit=SHOWN, only=only), None
            if not EmbeddingStore(conninfo).counts(settings.gemini_embedding_model)["embeddings"]:
                notes.append(NO_PAGE_EMBEDDINGS)
                return engine.by_words(conninfo, idea, limit=SHOWN, only=only), None
            ranking = engine.by_meaning(
                EmbeddingStore(conninfo), client("google", "embed_query"), idea,
                model=settings.gemini_embedding_model, limit=SHOWN, only=only,
            )  # fmt: skip
            if not (with_ai and ranking):
                return ranking, None
            order, how = rerank.order_pool(
                conninfo, client("rerank", "rerank"), idea, ranking[: rerank.POOL],
                model=settings.gemini_search_model, level=settings.gemini_search_thinking_level,
                scope=scope_of(chosen.chosen(), FILTERS), timeout_seconds=RERANK_SECONDS,
            )  # fmt: skip
            if how == rerank.LATE:
                notes.append(AI_LATE)
            return order + ranking[rerank.POOL :], how
        except (*FAILED_CALLS, BudgetExceeded):
            notes.append(GOOGLE_AWAY)
            return engine.by_words(conninfo, idea, limit=SHOWN, only=only), None

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
            ids, _ = ranking_of(conninfo, idea, mode, None, False, filtering.Filters(), [])
        return filtering.keep_chosen(filtering.choices(facts_of(conninfo, ids)), every, chosen)

    @app.get("/", response_class=HTMLResponse)
    def search(
        request: Request,
        idea: str = "",
        mode: str = MEANING,
        ai: str = "",
        event: str = "",
        year: str = "",
        category: str = "",
        proof: str = "",
        life: str = "",
        open: str = "",  # noqa: A002  (the name in the address)
        page: str = "1",
        view: str = "",
    ) -> HTMLResponse:
        idea = " ".join(idea.split())
        cut = len(idea) > LONGEST_IDEA
        idea = idea[:LONGEST_IDEA]
        if mode == "ai":  # the address of the second version of the page
            mode, ai = MEANING, "1"
        mode = mode if mode in MODES else MEANING
        with_ai = ai == "1" and mode == MEANING and bool(idea)
        view = CHARTS if view in (CHARTS, "overview") else ""
        page_number = int(page) if page.isdigit() and int(page) > 0 else 1
        open_id = int(open) if open.isdigit() else None
        asked = filtering.Filters(event, year, category, proof, life)
        base = {"idea": idea, "mode": mode, "with_ai": with_ai, "view": view, "open_id": open_id,
                "elapsed": None, "compare_ids": [], "notes": []}  # fmt: skip
        down = {**base, "problem": DATABASE_DOWN, "results": [], "offer": None, "chosen": asked,
                "panel_card": None, "search_query": ""}  # fmt: skip
        try:
            conninfo = database()
            every = filtering.choices(project_facts(conninfo))
        except (SettingsError, psycopg.OperationalError):
            if not idea:  # the start page needs no database; the list waits for it
                return render(request, "search.html", asked=False, **down)
            return render(request, "search.html", 503, asked=True, **down)
        notes = []
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
                 "check_events": every.event, "all_projects": every.projects,
                 "with_category": every.with_category, "notes": notes}  # fmt: skip
        try:
            panel_card = card_of(conninfo, open_id) if open_id else None
            if not idea:
                total = len(only) if only is not None else every.projects
                if view == CHARTS:
                    built, groups = charts_of(conninfo, only)
                    return render(request, "search.html", asked=False, results=[], total=total,
                                  charts=built, came_back=groups, offer=every,
                                  panel_card=panel_card, **shown)  # fmt: skip
                ids, total = data.browse(conninfo, only, offset=(page_number - 1) * PAGE_SIZE,
                                         limit=PAGE_SIZE)  # fmt: skip
                results = results_of(conninfo, ids, "", False)
                first = (page_number - 1) * PAGE_SIZE + 1
                return render(request, "search.html", asked=False, results=results, offer=every,
                              panel_card=panel_card, total=total, page=page_number,
                              pages=math.ceil(total / PAGE_SIZE), first_shown=first,
                              last_shown=first + len(results) - 1, **shown)  # fmt: skip
            began = time.perf_counter()
            ranking, how = ranking_of(conninfo, idea, mode, only, with_ai, chosen, notes)
            elapsed = time.perf_counter() - began
            offer = search_offer(conninfo, idea, mode, ranking, only, every, chosen)
            if cut:
                notes.append(IDEA_CUT)
            ordered = how in (rerank.KEPT, rerank.ASKED)
            if view == CHARTS:
                built, groups = charts_of(conninfo, ranking)
                return render(request, "search.html", asked=True, results=[], total=len(ranking),
                              charts=built, came_back=groups, offer=offer,
                              nothing_matches=only == [], panel_card=panel_card,
                              **{**shown, "elapsed": elapsed, "with_ai": ordered})  # fmt: skip
            total = len(ranking)
            pages = max(1, math.ceil(total / PAGE_SIZE))
            page_number = min(page_number, pages)
            first = (page_number - 1) * PAGE_SIZE
            results = results_of(conninfo, ranking[first : first + PAGE_SIZE], idea, mode == WORDS)
        except (SettingsError, psycopg.OperationalError):
            return render(request, "search.html", 503, asked=True, **down)
        # Gemini compares the ten that it put first, on the first page only.
        compare_ids = [card.hit.project_id for card, *_ in results] if ordered else []
        compare_ids = compare_ids if page_number == 1 else []
        return render(request, "search.html", asked=True, results=results, total=total,
                      pages=pages, page=page_number, first_shown=first + 1,
                      last_shown=first + len(results), nothing_matches=only == [],
                      panel_card=panel_card, offer=offer,
                      **{**shown, "elapsed": elapsed, "with_ai": ordered,
                         "compare_ids": compare_ids})  # fmt: skip

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
        return render(request, "project.html", card=card, back_query=back, idea="")

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
        except (SettingsError, psycopg.OperationalError):
            return render(request, "_problem.html", 503, problem=DATABASE_DOWN)
        if card is None:
            return render(request, "_problem.html", 404, problem=NO_SUCH_PROJECT)
        return render(request, "_panel.html", card=card, back_query=back, idea=idea,
                      kept_comparison=kept)  # fmt: skip

    @app.get("/compare", response_class=HTMLResponse)
    def comparison(request: Request, idea: str = "", ids: str = "", one: str = "") -> HTMLResponse:
        """What is the same and what differs, for the first results of an idea (design 8.3), or
        for one project in its window (`one`): kept from the last day, or asked now and kept."""
        idea = " ".join(idea.split())[:LONGEST_IDEA]
        try:
            project_ids = [int(part) for part in ids.split(",") if part.strip()][:PAGE_SIZE]
        except ValueError:
            project_ids = []
        place = {"one_place": one == "1"}
        if not idea or not project_ids:
            return render(request, "_compare.html", 400, found={}, failed=True, asked_ids=[],
                          **place)  # fmt: skip
        failures = (SettingsError, psycopg.OperationalError, comparing.CompareError,
                    BudgetExceeded, *FAILED_CALLS)  # fmt: skip
        try:
            conninfo = database()
            items = comparing.items_for(conninfo, project_ids, model=settings.gemini_rewrite_model,
                                        version=INSTRUCTIONS_VERSION)  # fmt: skip
            found, _ = comparing.kept_or_compared(
                conninfo, client("llm", "compare"), idea, items,
                model=settings.gemini_search_model,
                thinking_level=settings.gemini_search_thinking_level,
                timeout_seconds=COMPARE_SECONDS,
            )  # fmt: skip
        except failures:
            return render(request, "_compare.html", 503, found={}, failed=True,
                          asked_ids=project_ids, **place)  # fmt: skip
        return render(request, "_compare.html", found=found, failed=False, asked_ids=project_ids,
                      **place)  # fmt: skip

    def about(request: Request, name: str) -> HTMLResponse:
        """A window of the bottom of the page: a part of a page for htmx, a whole page without."""
        if name not in SHEETS:
            return render(request, "_problem.html", 404, problem=UNKNOWN_SHEET)
        title, part = SHEETS[name]
        values = {"modes": evidence.measured_modes(), "test1": evidence.newest("test1-card-form-2"),
                  "test2": evidence.newest("test2"), "measured": evidence.newest("search-modes"),
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

    templates.env.filters["day"] = day
    templates.env.filters["iso_day"] = iso_day
    templates.env.globals |= {
        "PRIZE_WORDS": listing.PRIZE_WORDS,
        "STATUS_WORDS": listing.STATUS_WORDS,
        "PROOF_SHORT": PROOF_SHORT,
        "CODE_WORDS": listing.CODE_WORDS,
        "WINNER_ENTRY": "winner_entry",
        "RERANK_SECONDS": RERANK_SECONDS,
        "LONGEST_IDEA": LONGEST_IDEA,
        "EXAMPLES": EXAMPLES,
        "REFS": references.BY_KEY,
        "REF_NUMBER": references.NUMBER,
        "REFERENCES": references.REFERENCES,
        "hashscan": data.hashscan,
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
