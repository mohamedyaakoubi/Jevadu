"""The website: the search (S1), the card of a project over it (S2), the check of a submission
(S3) and its registration on Hedera (S4), the charts of a list (S5) and the method (S6), on one
page (design 12.1, fourth version, on Tabler).

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
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.conninfo import make_conninfo
from starlette.concurrency import run_in_threadpool

from hackathon_memory import __version__
from hackathon_memory.check import submission
from hackathon_memory.collect import github
from hackathon_memory.collect.ethglobal import data_paths
from hackathon_memory.collect.github_commits import FOUND as VERSION_FOUND
from hackathon_memory.collect.github_facts import FOUND as CODE_FOUND
from hackathon_memory.collect.github_facts import saved_facts
from hackathon_memory.collect.github_readmes import FOUND as README_FOUND
from hackathon_memory.collect.github_readmes import saved_readme
from hackathon_memory.collect.polite import CollectorRefused
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.embeddings import EmbeddingStore, idea_fingerprint
from hackathon_memory.db.idea_answers import AnswerStore, scope_of
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.hedera import listed, registry
from hackathon_memory.hedera.mirror import MIRROR_URLS, MirrorError, MirrorNode, hashscan_topic
from hackathon_memory.hedera.register import RegisterError
from hackathon_memory.llm.card_form import INSTRUCTIONS_VERSION
from hackathon_memory.pipeline.embed import FAILED_CALLS
from hackathon_memory.search import compare as comparing
from hackathon_memory.search import counts as counting
from hackathon_memory.search import engine, listing, rerank, seen
from hackathon_memory.search import filters as filtering
from hackathon_memory.settings import Settings, SettingsError
from hackathon_memory.web import charts, data, evidence, hackathons, references

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
    "window_not_known": "end of the event not known yet",
    "dates_do_not_fit": "dates do not fit",
    "found_but_empty": "ID empty",
    "another_kind": "another kind of ID",
    "cannot_be_checked": "cannot be checked",
    "not_found": "ID not found",
    "no_id_given": "no ID given",
    filtering.NOT_CHECKED: "not checked yet",
    submission.NOT_ASKED: "the ledger did not answer",
    "dates_not_judged": "found, dates not judged",
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
GOOGLE_AWAY_CHECK = (
    "Google could not be asked about the meaning of the README just now, so the closest past "
    "projects are not shown. Try again later."
)
NO_PAGE_EMBEDDINGS = (
    "The projects have no embeddings yet, so only the words of the idea were searched."
)
UNKNOWN_SHEET = "There is no such page. Close this window."
NOT_A_REPOSITORY = (
    "This is not the link of a repository on GitHub. Paste a link such as "
    "github.com/owner/project, then press the button again."
)
NO_EVENT = (
    "There is no such hackathon in the list. Choose one from the list, or no hackathon, and "
    "press the button again."
)
NO_DAYS = (
    "Type the first and the last day of the hackathon; the last day may not come before the "
    "first. Or choose no hackathon: the check then shows the dates without judging them."
)
NO_VERSION = (
    "The version of the code could not be read on GitHub, so it cannot be registered. Check "
    "the repository again in a moment."
)
EVENT_FOR_REGISTER = (
    "A registration names its hackathon. Check the repository again with its hackathon, then "
    "write it to the register."
)
CLOSEST = 5  # the closest past projects that the check of a submission shows
NO_README_TO_SEARCH = (
    "The repository has no README to read, so no past project can be found by its meaning. "
    "Type its idea in the search box instead."
)
NOT_AN_ACCOUNT = (
    "A Hedera account looks like 0.0.12345. Leave the box empty to register without one."
)
CHECK_FIRST = "Check the repository first: only code that GitHub shows can be registered."
NO_LINE = (
    "The README of the repository on GitHub does not carry the line {line} yet. Add it to the "
    "README of the default branch, then press the button again. It shows that the code is "
    "yours, and that you agree to the record."
)
NOT_LISTED = (
    "A registration names a hackathon of the list, so that all the teams of one hackathon name it "
    "the same way. Choose it in the list. Days typed by hand can be checked, but not registered."
)
REGISTER_CLOSED = (
    "The public register is not open yet: its topic on Hedera's test network has not been created."
)
REGISTER_UNREAD = (
    "The register could not be read from the mirror node just now, so nothing can be written. "
    "Try again in a moment."
)
NOT_YET_VISIBLE = (
    "The record was sent to Hedera, but the mirror node does not show it yet. Check the "
    "repository again in a minute: the record will be listed among its registrations."
)
# The mirror node for a page: one more try after 2 seconds, not three over a minute.
MIRROR_SECONDS = 10.0
MIRROR_PAUSES = (2.0,)
IDEA_CUT = f"The idea was longer than {LONGEST_IDEA:,} characters, so it was cut."
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
        days.setdefault(code.fetched_at[:10], []).append("its facts")
    if readme is not None and readme.status == "found":
        name = f" ({readme.name})" if readme.name else ""
        days.setdefault(readme.fetched_at[:10], []).append(f"its README{name}")
    if version is not None and version.status == "found":
        days.setdefault(version.fetched_at[:10], []).append("the version")

    def joined(items: list[str]) -> str:
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]

    if len(days) == 1:
        ((when, items),) = days.items()
        return f"Read from GitHub on {iso_day(when)}: {joined(items)}."
    each = [f"{joined(items)} on {iso_day(when)}" for when, items in sorted(days.items())]
    return f"Read from GitHub: {', '.join(each)}." if each else ""


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


def create_app(
    settings: Settings | None = None,
    google: Any = None,
    llm: Any = None,
    *,
    github_client: Any = None,
    mirrors: Mapping[str, Any] | None = None,
    register_writer: Any = None,
) -> FastAPI:
    """The website. `google` is the client for the embeddings and `llm` the one for the search
    model; by default each is made, counted by the meter, when it is first needed. The check of
    a submission asks GitHub with `github_client` and the ledger with `mirrors`; by default they
    are made when first needed, with the promises of collect/github.py. `register_writer` writes
    one record to the register (hedera/registry.py); by default it is made when first needed."""
    settings = settings or Settings()
    app = FastAPI(title="Hackathon Memory", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    rerank_given = llm.tagged(purpose="rerank") if llm is not None else None
    clients: dict[str, Any] = {"google": google, "llm": llm, "rerank": rerank_given,
                               "github": github_client, "mirrors": mirrors,
                               "writer": register_writer}  # fmt: skip
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

    def readme_idea(repo: str) -> str:
        """The words of the README that the check of a repository saved, or "" when there is
        none. Nothing is asked of GitHub here."""
        repository = submission.repository_link(repo[:300])
        if repository is None:
            return ""
        readme = saved_readme(RawStore(github.raw_dir(settings)), repository)
        if readme is None or readme.status != README_FOUND:
            return ""
        return submission.readme_words(readme.text)

    def linked_to(conninfo: str, project_id: int) -> list[tuple[str, Any]]:
        """The projects linked to one project (design 8.4): each with why, and its name."""
        found = seen.links_of(conninfo, project_id)
        named = data.members(conninfo, [[pid] for pid, _ in found])
        return [(by, group[0]) for (_, by), group in zip(found, named, strict=True) if group]

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
        order came from when it was asked for. When Google cannot be reached, the words.

        A filter keeps the projects of the SHOWN closest that have its values (design 8.2), so
        the number next to a value of a filter is the number of projects it leaves."""
        allowed = None if only is None else set(only)

        def narrowed(ids: list[int]) -> list[int]:
            return ids if allowed is None else [pid for pid in ids if pid in allowed]

        try:
            if only == []:
                return [], None
            if mode == WORDS:
                return narrowed(engine.by_words(conninfo, idea, limit=SHOWN)), None
            if not EmbeddingStore(conninfo).counts(settings.gemini_embedding_model)["embeddings"]:
                notes.append(NO_PAGE_EMBEDDINGS)
                return narrowed(engine.by_words(conninfo, idea, limit=SHOWN)), None
            ranking = narrowed(engine.by_meaning(
                EmbeddingStore(conninfo), client("google", "embed_query"), idea,
                model=settings.gemini_embedding_model, limit=SHOWN,
            ))  # fmt: skip
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
            return narrowed(engine.by_words(conninfo, idea, limit=SHOWN)), None

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
                 "check_events": data.dated_events(conninfo), "all_projects": every.projects,
                 "shown_limit": SHOWN,
                 "with_category": every.with_category, "notes": notes}  # fmt: skip
        try:
            panel_card = card_of(conninfo, open_id) if open_id else None
            shown["panel_linked"] = linked_to(conninfo, open_id) if panel_card else []
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
            none_close = bool(only) and not ranking  # the filters match, but none is close
            if view == CHARTS:
                built, groups = charts_of(conninfo, ranking)
                return render(request, "search.html", asked=True, results=[], total=len(ranking),
                              charts=built, came_back=groups, offer=offer,
                              nothing_matches=only == [], none_close=none_close,
                              panel_card=panel_card,
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
                      none_close=none_close, panel_card=panel_card, offer=offer,
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
        except (BudgetExceeded, *FAILED_CALLS):
            return [], GOOGLE_AWAY_CHECK
        known = {one.project_id for one in check.seen}
        ids = [pid for pid in ranking if pid not in known][:CLOSEST]
        return results_of(conninfo, ids, "", False), None

    @app.get("/check", response_class=HTMLResponse)
    def check(
        request: Request, repo: str = "", event: str = "", starts: str = "", ends: str = ""
    ) -> HTMLResponse:
        """S3: the check of one submission (design 12.1), in the window over the page, or as a
        page of its own without JavaScript. Programs read every fact; no model writes."""
        name = "_check.html" if request.headers.get("HX-Request") == "true" else "check.html"
        repository = submission.repository_link(repo[:300])
        if repository is None:
            return render(request, name, 400, problem=NOT_A_REPOSITORY)
        try:
            conninfo = database()
            days, wrong = event_days(conninfo, event, starts, ends)
            if wrong:
                return render(request, name, 400, problem=wrong)
            asker, why = github_or_why()
            result = submission.check_submission(
                conninfo, repository, days, client=asker,
                store=RawStore(github.raw_dir(settings)),
                collector=f"{settings.collector_name.strip()}/{__version__}",
                mirrors=mirror_nodes(), problems=[why] if why else [],
            )  # fmt: skip
            closest, note = closest_to(conninfo, result)
            groups = [[one.project_id] for one in result.seen]
            members = [group[0] for group in data.members(conninfo, groups)]
        except (SettingsError, psycopg.OperationalError):
            return render(request, name, 503, problem=DATABASE_DOWN)
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
        return render(request, name, result=result, closest=closest, closest_note=note,
                      seen_before=seen_before, register=view, register_offers=offers,
                      asked={"event": event, "starts": starts, "ends": ends})  # fmt: skip

    @app.post("/register", response_class=HTMLResponse)
    async def register_page(request: Request) -> HTMLResponse:
        """S4: write the record of a checked submission to the register on Hedera (design 9.2),
        read it back from the mirror node, and show the receipt."""
        body = (await request.body()).decode("utf-8", "replace")
        form = {key: values[0] for key, values in parse_qs(body).items()}
        return await run_in_threadpool(registered, request, form)

    def registered(request: Request, form: dict[str, str]) -> HTMLResponse:
        name = "_register.html" if request.headers.get("HX-Request") == "true" else "register.html"
        repository = submission.repository_link(form.get("repo", "")[:300])
        if repository is None:
            return render(request, name, 400, problem=NOT_A_REPOSITORY)
        typed = form.get("account", "").strip()
        account = registry.account_of(typed) if typed else None
        if typed and account is None:
            return render(request, name, 400, problem=NOT_AN_ACCOUNT)
        try:
            days, wrong = event_days(database(), form.get("event", ""), form.get("starts", ""),
                                     form.get("ends", ""))  # fmt: skip
        except (SettingsError, psycopg.OperationalError):
            return render(request, name, 503, problem=DATABASE_DOWN)
        if days is None:
            return render(request, name, 400, problem=wrong or EVENT_FOR_REGISTER)
        if days.typed:
            return render(request, name, 400, problem=NOT_LISTED)
        store = RawStore(github.raw_dir(settings))
        code = saved_facts(store, repository)
        if code is None or code.status != CODE_FOUND:
            return render(request, name, 400, problem=CHECK_FIRST)
        view = register_view(repository, days)
        if not view.open or view.problem:
            return render(request, name, 503, problem=view.problem or REGISTER_CLOSED)
        values = {"view": view, "network": view.network, "topic_id": view.topic_id}
        if view.same_event is not None:  # never written twice: the first record stands
            return render(request, name, done=view.same_event, already=True, **values)
        # The README and the version, read again now: the team's line must be in the README, and
        # the newest version is stamped. Each read goes to a new folder; nothing saved is replaced.
        asker, why = github_or_why()
        if asker is None:
            return render(request, name, 503, problem=why)
        when = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        readme, version, problems = submission.read_again(
            asker, RawStore(github.raw_dir(settings) / "register" / when), repository,
            collector=f"{settings.collector_name.strip()}/{__version__}",
        )  # fmt: skip
        if problems:
            return render(request, name, 503, problem=problems[0])
        readme_text = readme.text if readme and readme.status == README_FOUND else ""
        if not registry.carries_line(readme_text, view.line):
            return render(request, name, 400, problem=NO_LINE.format(line=view.line))
        if version is None or version.status != VERSION_FOUND or version.sha is None:
            return render(request, name, 400, problem=NO_VERSION)
        write, why = writer_or_why()
        if write is None:
            return render(request, name, 503, problem=why)
        account_print = registry.account_fingerprint(account) if account else None
        payload = registry.record(view.event, view.code, version.sha, account_print)
        try:
            done = registry.register_submission(write, mirror_nodes()[view.network],
                                                view.topic_id, payload)  # fmt: skip
        except RegisterError as error:
            return render(request, name, 503, problem=f"Nothing was registered. {error}")
        except MirrorError:
            return render(request, name, 202, problem=NOT_YET_VISIBLE)
        return render(request, name, done=done, already=False, **values)

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
    templates.env.filters["moment"] = moment
    templates.env.filters["iso_day"] = iso_day
    templates.env.globals |= {
        "PRIZE_WORDS": listing.PRIZE_WORDS,
        "STATUS_WORDS": listing.STATUS_WORDS,
        "PROOF_SHORT": PROOF_SHORT,
        "CODE_WORDS": listing.CODE_WORDS,
        "WINNER_ENTRY": "winner_entry",
        "NOT_ASKED": submission.NOT_ASKED,
        "CONFIRMED": seen.CONFIRMED,
        "MAX_IDS": submission.MAX_IDS,
        "RERANK_SECONDS": RERANK_SECONDS,
        "LONGEST_IDEA": LONGEST_IDEA,
        "EXAMPLES": EXAMPLES,
        "REFS": references.BY_KEY,
        "REF_NUMBER": references.NUMBER,
        "REFERENCES": references.REFERENCES,
        "hashscan": data.hashscan,
        "ACTION_WORDS": data.ACTION_WORDS,
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
