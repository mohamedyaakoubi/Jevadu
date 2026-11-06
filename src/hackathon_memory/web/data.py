"""What the pages show, read from the tables (design 4.1).

A card has three sources, and the page keeps them apart:

* the page, copied word for word by the parser: the name, the short line, the texts, the links,
  the event and the prize;
* the code host and the ledger, read by code: the repository, its dates, what its code says
  about Hedera, each Hedera ID and what the mirror node said about it, the proof status, the
  life status, and the ledger story, which sets the services of the page, the code and the
  ledger side by side;
* the model: the fields of the card of the instructions in use, each with its label and the
  quotes that the program found in the page.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path

import psycopg
from markupsafe import Markup, escape

from hackathon_memory.check.depth import Depth
from hackathon_memory.check.history import (
    CONSENSUS,
    CONTRACTS,
    FILES,
    HBAR,
    MAX_EVENTS,
    SCHEDULED,
    TOKENS,
)
from hackathon_memory.check.life import AFTER_THE_EVENT
from hackathon_memory.check.proof import (
    ANOTHER_KIND,
    CANNOT_BE_CHECKED,
    DATES_DO_NOT_FIT,
    FOUND_BUT_EMPTY,
    NOT_FOUND,
    PROOF_FOUND,
    WINDOW_NOT_KNOWN,
    Window,
    window_of,
)
from hackathon_memory.check.story import (
    Stop,
    Story,
    places_in,
    services_in_code,
    set_up_in_code,
)
from hackathon_memory.collect import devfolio
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.card_choice import CARD_OF_PROJECT
from hackathon_memory.db.history import depth_of_project, story_of_project
from hackathon_memory.db.public_services import NamedService, public_services_of
from hackathon_memory.db.read_again import free_from, of_project
from hackathon_memory.db.readings import Reading, latest_reading
from hackathon_memory.parse.hedera_code import PACKAGE
from hackathon_memory.read.quotes import FIELDS, KEPT
from hackathon_memory.search import listing
from hackathon_memory.search.engine import LANGUAGE, Hit
from hackathon_memory.search.listing import STATUS_WORDS, LedgerLine, ResultCard
from hackathon_memory.web.code_reading import CodeView, view_of_repository

FIELD_TITLES = {
    "what_it_does": "What it does",
    "how_it_works": "How it works",
    "for_whom": "For whom",
    "hedera_services": "Hedera services",
    "category": "Category",
    "problem": "Problem",
    "solution": "Solution",
}
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
# HashScan has a page for each of these kinds; a number of another kind, or not found, gets none.
HASHSCAN_KINDS = frozenset({"account", "contract", "topic", "token", "transaction", "schedule"})
# A kind of ID in the words of a person, where they differ from the name of the kind.
KIND_WORDS = {"schedule": "scheduled transaction"}
NETWORK_WORDS = {"testnet": "test network", "mainnet": "main network",
                 "previewnet": "preview network"}  # fmt: skip
# A network that a message of a topic names (CAIP-2), in words. Read on 1 November 2026: Base's
# "Network information" (8453 is Base, 84532 Base Sepolia) and Hedera's JSON-RPC relay (295 is its
# main network, 296 its test network). Another network is shown by its code.
CAIP2_NAMES = {
    "eip155:8453": "Base",
    "eip155:84532": "Base Sepolia",
    "eip155:295": "Hedera's main network",
    "eip155:296": "Hedera's test network",
    "hedera:mainnet": "Hedera's main network",
    "hedera:testnet": "Hedera's test network",
}
# The kinds of action of a transaction that the mirror node names, in plain words. Another kind is
# shown as the node writes it.
ACTION_WORDS = {
    "CRYPTOTRANSFER": "transfer",
    "CRYPTOCREATEACCOUNT": "account created",
    "TOKENCREATION": "token created",
    "TOKENMINT": "token minted",
    "TOKENASSOCIATE": "token associated with an account",
    "CONSENSUSCREATETOPIC": "topic created",
    "CONSENSUSSUBMITMESSAGE": "message submitted to a topic",
    "CONTRACTCREATEINSTANCE": "smart contract deployed",
    "CONTRACTCALL": "smart contract call",
    "ETHEREUMTRANSACTION": "Ethereum transaction (from an EVM wallet)",
    "SCHEDULECREATE": "scheduled transaction created",
    "ATOMICBATCH": "atomic batch of transactions",  # 3 of the 223 transactions, 18 October 2026
}
NETWORKS = frozenset({"mainnet", "testnet", "previewnet"})
# The Hedera services of the ledger story (design 7.5), in the words of the card: the name of a
# row, as "Hedera in the code" names the service; the service in a sentence; its transactions.
SERVICE_NAMES = {
    CONSENSUS: "Consensus Service (topics)",
    TOKENS: "Token Service",
    CONTRACTS: "Smart contracts",
    SCHEDULED: "Scheduled transactions",
    FILES: "File Service",
    HBAR: "Accounts and HBAR transfers",
}
SERVICE_SUBJECTS = {
    CONSENSUS: "the Consensus Service",
    TOKENS: "the Token Service",
    CONTRACTS: "smart contracts",
    SCHEDULED: "scheduled transactions",
    FILES: "the File Service",
}
SERVICE_TRANSACTIONS = {  # plural; the singular drops the last letter
    CONSENSUS: "Consensus Service transactions",
    TOKENS: "Token Service transactions",
    CONTRACTS: "smart contract transactions",
    SCHEDULED: "scheduled transactions",
    FILES: "File Service transactions",
    HBAR: "HBAR and account transactions",
}


def read_only(cut_off: Sequence[Stop]) -> str:
    """Where the limit of the reading stopped, in plain words, for the card and its strip
    (29 October 2026): "Jevadu read only the first 2,000 transactions of its contract 0.0.5,
    up to 5 July 2024"."""
    said = [(f"its {stop.kind or 'ID'} {stop.entity_id}", f"{stop.day.day} {stop.day:%B} "
             f"{stop.day.year}") for stop in cut_off]  # fmt: skip
    if len(said) == 1:
        where = "{}, up to {}".format(*said[0])
    else:
        where = " and of ".join(f"{place} (up to {day})" for place, day in said)
    return f"Jevadu read only the first {MAX_EVENTS:,} transactions of {where}"


def stopped_at(cut_off: Sequence[Stop], *, on_day: bool = True) -> str:
    """The same, short, for the lines of the card after the note that names the IDs: "the reading
    of its contract stopped at its limit of 2,000 transactions, on 5 July 2024"; without the day,
    "stopped there", for a sentence that has just said it."""
    things = " and ".join(f"its {stop.kind or 'ID'}" for stop in cut_off)
    first = cut_off[0].day
    one = len(cut_off) == 1
    subject = f"the reading{'' if one else 's'} of {things} stopped"
    limit = f"at {'its' if one else 'their'} limit of {MAX_EVENTS:,} transactions"
    if not on_day:
        return f"{subject} {'there' if one else 'from then on'}, {limit}"
    day = f"{first.day} {first:%B} {first.year}"
    return f"{subject} {limit}, {'on' if one else 'the first on'} {day}"


@dataclass(frozen=True)
class Judged:
    """What a card says about how its marks were judged (design 12.1, S2): the window of the
    event, in "On the ledger", and the day after which a sign counts as a sign of life, in the
    activity line of the code."""

    window: Window | None
    life_after: datetime | None


def a_or_an(word: str) -> str:
    """The word with its article: "an account", "a topic"."""
    return f"{'an' if word[:1].lower() in 'aeiou' else 'a'} {word}"


# The results of an ID that the ledger knows on the network that was asked.
KNOWN_THERE = frozenset({PROOF_FOUND, DATES_DO_NOT_FIT, ANOTHER_KIND, FOUND_BUT_EMPTY,
                         WINDOW_NOT_KNOWN})  # fmt: skip


def lines_to_show(ledger: Sequence[LedgerLine]) -> list[LedgerLine]:
    """The lines of "On the ledger" (design 12.1, S2): each network that was asked about an ID,
    but not the "not found" of an ID that its page or README names with no network, when the
    other network knows it. Both networks were asked only because the network was not said."""
    known = {line.entity_id for line in ledger if line.status in KNOWN_THERE}

    def left_out(line: LedgerLine) -> bool:
        return line.status == NOT_FOUND and line.named_network is None and line.entity_id in known

    return [line for line in ledger if line.network and not left_out(line)]


def reason_of(line: LedgerLine, window: Window | None) -> str:
    """Why the result of one ID is what it is, from its facts, in plain words."""
    where = "README" if line.found_in == "readme" else "page"
    if line.status == PROOF_FOUND:
        return ("made inside the window" if window is not None and window.holds(line.created_at)
                else "used inside the window")  # fmt: skip
    if line.status == DATES_DO_NOT_FIT:
        return "made and used outside the window"
    if line.status == ANOTHER_KIND:
        known = KIND_WORDS.get(line.kind, line.kind or "")
        return (f"the {where} calls it {a_or_an(line.said_kind or '')}, but the ledger knows it "
                f"as {a_or_an(known)}")  # fmt: skip
    if line.status == FOUND_BUT_EMPTY:
        return ("nothing in it: a topic with no message, a token with no unit, a deleted contract "
                "or a failed transaction")  # fmt: skip
    if line.status == NOT_FOUND:
        return f"the {NETWORK_WORDS.get(line.network, line.network)} does not know it"
    if line.status == CANNOT_BE_CHECKED:
        return "the test network was emptied on 1 February 2024, after this event"
    if line.status == WINDOW_NOT_KNOWN:
        return "found; its dates wait for the end of the event"
    return STATUS_WORDS.get(line.status, line.status or "not checked yet")


def life_line(ended: date | None) -> datetime | None:
    """The moment after which a sign counts as a sign of life (design 7.4), or None."""
    return datetime.combine(ended, time.max, tzinfo=UTC) + AFTER_THE_EVENT if ended else None


def judged_of(facts: ResultCard) -> Judged:
    """The facts behind the proof and the activity of a project, for its card."""
    return Judged(window_of(facts.event_starts_at, facts.event_ends_on),
                  life_line(facts.event_ends_on))  # fmt: skip


def hashscan(network: str | None, kind: str | None, entity_id: str) -> str | None:
    """The page of an ID on HashScan, where anybody can see what the mirror node says."""
    if network not in NETWORKS or kind not in HASHSCAN_KINDS:
        return None
    return f"https://hashscan.io/{network}/{kind}/{entity_id}"


# A Hedera ID inside a sentence of the card or of the main network's window: "0.0.731861".
LEDGER_ID = re.compile(r"\b0\.0\.\d+\b")
# The word before an ID that names its kind: "its token 0.0.5", "the topics 0.0.6".
_KIND_BEFORE = re.compile(r"\b(account|token|topic|contract|schedule)s?\s+$")
_ID_LINK = Markup(
    '<a class="id" href="{}" rel="noopener" target="_blank">{}<span '
    'class="visually-hidden"> on HashScan (opens in a new tab)</span></a>'
)


def ids_in(text: str | None) -> list[str]:
    """The Hedera IDs that a text names, in their order."""
    return LEDGER_ID.findall(text or "")


def id_links(
    text: str | None,
    known: Mapping[str, tuple[str | None, str | None]] | None = None,
    network: str | None = None,
    kind: str = "account",
) -> Markup:
    """A sentence with each Hedera ID in it as a link to its page on HashScan, as every other ID
    of the site is (3 November 2026: the main network's window named a token by its symbol
    alone, and the card's sentences gave their IDs as plain text). An ID of `known` has its own
    network and kind; another has the network of the ID before it in the sentence, or
    `network`, and the kind that the word before it names, or `kind`. An ID whose network is
    not known stays as it is."""
    text, known = text or "", known or {}
    parts: list[Markup] = []
    last = 0
    for found in LEDGER_ID.finditer(text):
        entity, before = found.group(), text[last : found.start()]
        on, what = known.get(entity, (None, None))
        named = _KIND_BEFORE.search(before)
        network = on or network
        link = hashscan(network, what or (named.group(1) if named else kind), entity)
        parts += [escape(before), _ID_LINK.format(link, entity) if link else escape(entity)]
        last = found.end()
    parts.append(escape(text[last:]))
    return Markup("").join(parts)


def ledger_ids(story: Story | None) -> dict[str, tuple[str, str | None]]:
    """The own IDs of a ledger story, each with its network and kind, for id_links."""
    return {one.entity_id: (one.network, one.kind) for one in story.ids} if story else {}


def one_network(story: Story | None) -> str | None:
    """The network of the own IDs of a story when they all share one, for an ID of a sentence
    that no ID before it places, such as the account that made several of them."""
    networks = {one.network for one in story.ids} if story else set()
    return networks.pop() if len(networks) == 1 else None


@dataclass(frozen=True)
class Summary:
    """The one sentence that a result shows, and where it comes from."""

    text: str
    source: str  # "model" or "page"
    label: str | None  # the label of the model's field, when it comes from the model


@dataclass(frozen=True)
class Section:
    title: str
    body: str


@dataclass(frozen=True)
class PageLink:
    kind: str
    url: str
    label: str


@dataclass(frozen=True)
class Prize:
    sponsor: str
    track: str | None
    award: str | None


@dataclass(frozen=True)
class ModelField:
    name: str
    title: str
    label: str
    state: str  # kept, dropped or not_found (design 6.3)
    value: str | list[str]
    quotes: tuple[str, ...]


@dataclass(frozen=True)
class ModelCard:
    model: str
    instructions_version: str
    made_at: datetime
    fields: tuple[ModelField, ...]


@dataclass(frozen=True)
class ProjectCard:
    facts: ResultCard  # the event, the prize, the proof, the life, the ledger, the repository
    short_line: str
    sections: tuple[Section, ...]
    links: tuple[PageLink, ...]
    prizes: tuple[Prize, ...]
    parsed_at: datetime | None
    collected_at: datetime | None  # when the page was saved from its site
    language: str | None
    card: ModelCard | None
    event_link: str | None = None  # the page of the event (event_page)
    code_reading: CodeView | None = None  # what the code says about Hedera (design 7.3)
    story: Story | None = None  # the ledger story (design 7.5), or None when it has none
    depth: Depth | None = None  # the depth of use of its own IDs (design 7.5), or None
    reading: Reading | None = None  # its newest reading, whoever made it (design 7.3)
    # the public services that it names, which are not its own (design 8.4, 29 October 2026)
    public: tuple[NamedService, ...] = ()
    read_again_from: datetime | None = None  # when its button can be pressed again (design 7.3)


def first_sentence(text: str) -> str:
    return next((part.strip() for part in _SENTENCE_END.split(text or "") if part.strip()), "")


def summaries(
    conninfo: str, project_ids: Sequence[int], *, models: Sequence[str], version: str
) -> dict[int, Summary]:
    """For each project: the model's sentence "what it does" when its card keeps it, otherwise
    the short line, otherwise the first sentence of the first text of the page."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT p.id, coalesce(p.short_line, ''), "  # noqa: S608  (fixed text)
            "coalesce((SELECT s.body FROM sections s WHERE s.project_id = p.id "
            "ORDER BY s.position LIMIT 1), ''), c.fields -> 'what_it_does' "
            "FROM projects p " + CARD_OF_PROJECT + "WHERE p.id = ANY(%s)",
            (list(models), version, list(models), list(project_ids)),
        ).fetchall()
    found = {}
    for project_id, short_line, first_text, field in rows:
        if field and field.get("state") == KEPT and field.get("value"):
            found[project_id] = Summary(field["value"], "model", field.get("label"))
        else:
            found[project_id] = Summary(short_line.strip() or first_sentence(first_text), "page",
                                        None)  # fmt: skip
    return found


def project_card(
    conninfo: str,
    project_id: int,
    *,
    models: Sequence[str],
    version: str,
    raw_dir: Path | None = None,
    now: datetime | None = None,
) -> ProjectCard | None:
    """Everything that the card of one project shows, or None when there is no such project."""
    found = listing.cards(conninfo, [Hit(project_id, 0.0, None, None)], now=now)
    if not found:
        return None
    with psycopg.connect(conninfo) as conn:
        short_line, parsed_at, language, site, slug = conn.execute(
            "SELECT coalesce(p.short_line, ''), p.parsed_at, r.language, e.site, e.slug "
            "FROM projects p JOIN events e ON e.id = p.event_id "
            "LEFT JOIN repositories r ON r.id = p.repository_id WHERE p.id = %s",
            (project_id,),
        ).fetchone()
        sections = tuple(
            Section(title or "", body)
            for title, body in conn.execute(
                "SELECT title, body FROM sections WHERE project_id = %s ORDER BY position",
                (project_id,),
            ).fetchall()
        )
        links = tuple(
            PageLink(kind, url, label or "")
            for kind, url, label in conn.execute(
                "SELECT kind, url, label FROM links WHERE project_id = %s AND url IS NOT NULL "
                "ORDER BY position",
                (project_id,),
            ).fetchall()
        )
        prizes = tuple(
            Prize(sponsor or "", track, award)
            for sponsor, track, award in conn.execute(
                "SELECT sponsor, track, award FROM prizes WHERE project_id = %s ORDER BY position",
                (project_id,),
            ).fetchall()
        )
        row = conn.execute(
            "SELECT fields, made_at, model FROM cards WHERE project_id = %s AND model = ANY(%s) "
            "AND instructions_version = %s ORDER BY array_position(%s::text[], model) LIMIT 1",
            (project_id, list(models), version, list(models)),
        ).fetchone()
        repository = found[0].repository
        code_reading = view_of_repository(conn, repository) if repository else None
        words = "\n".join([short_line, *(one.body for one in sections)])
        story = story_of_project(conn, project_id, words=words, in_code=services_of(code_reading),
                                 set_up=set_up_of(code_reading))  # fmt: skip
        depth = depth_of_project(conn, project_id, story,
                                 in_code=services_of(code_reading),
                                 set_up=set_up_of(code_reading),
                                 has_package=has_a_package(code_reading))  # fmt: skip
        reading = latest_reading(conn, project_id)
        read_again_from = free_from(conn, of_project(project_id))
        public = public_services_of(conn, project_id)
    card = None
    if row is not None:
        fields, made_at, model = row  # the model that wrote this card
        card = ModelCard(model, version, made_at, tuple(
            ModelField(name, FIELD_TITLES[name], fields[name]["label"], fields[name]["state"],
                       fields[name]["value"], tuple(fields[name]["quotes"]))
            for name in FIELDS
        ))  # fmt: skip
    return ProjectCard(found[0], short_line, sections, links, prizes, parsed_at,
                       collected_at(raw_dir, found[0].page_url), language, card,
                       event_page(site, slug, found[0].page_url), code_reading, story,
                       depth, reading, public, read_again_from)  # fmt: skip


def said(text: str) -> Markup:
    """A text of the page with each place that names a Hedera service marked (design 7.5). The
    buttons of the ledger story show the marks of one word; until then they look like text."""
    parts: list[Markup] = []
    at = 0
    for start, end, service in places_in(text):
        word = text[start:end]
        parts.append(escape(text[at:start]))
        parts.append(Markup('<mark class="hm-said" data-said="{}" data-word="{}">{}</mark>')
                     .format(service, word.casefold(), word))  # fmt: skip
        at = end
    parts.append(escape(text[at:]))
    return Markup("").join(parts)


def said_lines(text: str) -> list[str]:
    """The lines of a text that the page does not show, such as a README, that name a Hedera
    service, in their order (design 7.5): every place of the ledger story's words is in them."""
    return [line.strip() for line in text.splitlines() if places_in(line)]


def services_of(view: CodeView | None) -> frozenset[str] | None:
    """The Hedera services that a reading of the code calls (design 7.5); None when the code was
    not read, or could not be read."""
    if view is None or view.status in ("gone", "blocked"):
        return None
    return services_in_code((one.kind, one.name) for one in view.found)


def has_a_package(view: CodeView | None) -> bool:
    """Whether a reading of the code found a Hedera package in a package file (design 7.3)."""
    if view is None or view.status in ("gone", "blocked"):
        return False
    return any(one.kind == PACKAGE for one in view.found)


def set_up_of(view: CodeView | None) -> frozenset[str]:
    """The services that a reading of the code only sets up for: an EVM project (design 7.5)."""
    if view is None or view.status in ("gone", "blocked"):
        return frozenset()
    return set_up_in_code((one.kind, one.name) for one in view.found)


def collected_at(raw_dir: Path | None, page_url: str) -> datetime | None:
    """When the page was saved from its site, from the record kept next to the saved page. A
    project of Devfolio is saved as the answer of its data service, in the folder of that site."""
    if raw_dir is not None and page_url.startswith(devfolio.project_page("")):
        name = page_url.removeprefix(devfolio.project_page(""))
        saved = RawStore(raw_dir.parent / devfolio.SITE).load(devfolio.project_address(name),
                                                                devfolio.SUFFIX)  # fmt: skip
    else:
        saved = RawStore(raw_dir).load(page_url) if raw_dir is not None else None
    fetched = saved.meta.get("fetched_at") if saved else None
    try:
        return datetime.fromisoformat(fetched.replace("Z", "+00:00")) if fetched else None
    except ValueError:
        return None


# ------------------------------------------------------------------ what the list shows

# Two characters that a page never uses mark the start and the end of a matched word. The text is
# escaped first, and only then are they turned into <mark>, so no text of a page can reach the
# browser as code (PostgreSQL's manual warns that ts_headline does not make its output safe).
_START, _STOP = "", ""
_MARK_OPEN, _MARK_CLOSE = Markup("<mark>"), Markup("</mark>")
_HEADLINE_OPTIONS = (
    f'StartSel="{_START}", StopSel="{_STOP}", MaxWords=24, MinWords=10, MaxFragments=1, '
    'FragmentDelimiter=" ... "'
)


# Words that stand in many ideas and say little about one, so a result does not mark them (the
# maintainer's review of 18 October 2026). How often a word appears is no guide: "payment" stands
# in 35% of the projects and "app" in 14%, and only "payment" tells why a project is close.
# PostgreSQL already leaves out the smallest words, such as "a", "the" and "that".
COMMON_WORDS = (
    "app apps application applications platform tool tools system solution project product "
    "user users people use uses using let lets allow allows help helps without within via "
    "make makes take takes get gets new simple easy way ways also every one thing things like"
)


def _idea_query(conn: psycopg.Connection, idea: str) -> str:
    """The words of the idea that are marked, as the text of a query that matches any one of
    them by its stem, the common words left out; empty when none is left."""
    rows = conn.execute(
        "SELECT word FROM unnest(tsvector_to_array(to_tsvector(%s, %s))) AS word "
        "EXCEPT SELECT unnest(tsvector_to_array(to_tsvector(%s, %s)))",
        (LANGUAGE, idea, LANGUAGE, COMMON_WORDS),
    ).fetchall()
    quoted = ("'" + word.replace("\\", "\\\\").replace("'", "''") + "'" for (word,) in sorted(rows))
    return " | ".join(quoted)


def matched_words(conninfo: str, project_ids: Sequence[int], idea: str) -> dict[int, Markup]:
    """For each project whose page has a word of the idea: the part of its short line and first
    text where those words stand, with each one marked. A project found only by meaning has
    none."""
    if not project_ids or not idea.strip():
        return {}
    with psycopg.connect(conninfo) as conn:
        query = _idea_query(conn, idea)
        rows = conn.execute(
            "WITH q AS (SELECT %(query)s::tsquery AS query), docs AS (SELECT p.id, "
            "concat_ws(' ', p.short_line, "
            "(SELECT s.body FROM sections s WHERE s.project_id = p.id ORDER BY s.position "
            "LIMIT 1)) AS document FROM projects p WHERE p.id = ANY(%(ids)s)) "
            "SELECT d.id, ts_headline(%(language)s, d.document, q.query, %(options)s) "
            "FROM docs d, q WHERE q.query::text <> '' "
            "AND to_tsvector(%(language)s, d.document) @@ q.query",
            {"language": LANGUAGE, "query": query, "ids": list(project_ids),
             "options": _HEADLINE_OPTIONS},
        ).fetchall()  # fmt: skip
    return {
        project_id: escape(" ".join(headline.split()))
        .replace(_START, _MARK_OPEN)
        .replace(_STOP, _MARK_CLOSE)
        for project_id, headline in rows
    }


def browse(
    conninfo: str, only: Sequence[int] | None, *, offset: int, limit: int
) -> tuple[list[int], int]:
    """The projects to list when no idea is given, newest events first, and how many there are
    in all. With `only`, the projects are those (the filters)."""
    ids = None if only is None else list(only)
    with psycopg.connect(conninfo) as conn:
        total = conn.execute(
            "SELECT count(*) FROM projects WHERE %s::bigint[] IS NULL OR id = ANY(%s)", (ids, ids)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT p.id FROM projects p JOIN events e ON e.id = p.event_id "
            "WHERE %s::bigint[] IS NULL OR p.id = ANY(%s) "
            "ORDER BY coalesce(e.ends_on, e.starts_at::date) DESC NULLS LAST, e.name, p.name, p.id "
            "OFFSET %s LIMIT %s",
            (ids, ids, offset, limit),
        ).fetchall()
    return [row[0] for row in rows], total


@dataclass(frozen=True)
class Member:
    """One project of a group linked across events (search/seen.py), as the charts name it."""

    project_id: int
    name: str
    event: str
    event_id: int | None = None


def event_page(site: str, slug: str, project_page: str | None) -> str | None:
    """The page of an event: on ETHGlobal, the page that its project pages link to
    (/events/<short name>, seen in the saved pages on 16 October 2026); on Devfolio, the event's
    own address, <short name>.devfolio.co (31 October 2026); for an event known from an
    organiser's list of winners, that list, which its projects link to."""
    if site == "ethglobal.com":
        return f"https://ethglobal.com/events/{slug}"
    if site == devfolio.SITE:
        return f"https://{slug}.{devfolio.SITE}/"
    return project_page.split("#", 1)[0] if project_page else None


def event_pages(conninfo: str) -> dict[str, tuple[str, str, str | None]]:
    """Each event by its number: its name, its year, and its page."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT e.id, e.name, coalesce(extract(year FROM e.ends_on), "
            "extract(year FROM e.starts_at), e.year)::int, e.site, e.slug, min(p.page_url) "
            "FROM events e LEFT JOIN projects p ON p.event_id = e.id GROUP BY e.id"
        ).fetchall()
    return {str(event_id): (name, str(year) if year else "", event_page(site, slug, page))
            for event_id, name, year, site, slug, page in rows}  # fmt: skip


def dated_events(conninfo: str) -> list[tuple[str, str, datetime, datetime]]:
    """The hackathons whose first and last day are known, the newest first: the number of each,
    its name and its two days, for the list of the GitHub check (design 12.1, S3)."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT id, name, starts_at::date, ends_on FROM events "
            "WHERE starts_at IS NOT NULL AND ends_on IS NOT NULL ORDER BY ends_on DESC, name"
        ).fetchall()
    return [(str(event_id), name, first, last) for event_id, name, first, last in rows]


def members(conninfo: str, groups: Sequence[Sequence[int]]) -> list[list[Member]]:
    """The name and the event of each project of the groups, in the order given."""
    ids = [pid for group in groups for pid in group]
    if not ids:
        return []
    with psycopg.connect(conninfo) as conn:
        names = {pid: (name, event, event_id) for pid, name, event, event_id in conn.execute(
            "SELECT p.id, p.name, e.name, e.id FROM projects p JOIN events e ON e.id = p.event_id "
            "WHERE p.id = ANY(%s)", (ids,)).fetchall()}  # fmt: skip
    return [[Member(pid, *names[pid]) for pid in group if pid in names] for group in groups]


def marked_lines(conninfo: str, lines: dict[int, str], idea: str) -> dict[int, Markup]:
    """Each line (the sentence that a result shows) with the words of the idea marked, for the
    lines that have one. The words count by their stem, as in the search by words."""
    if not lines or not idea.strip():
        return {}
    ids = list(lines)
    with psycopg.connect(conninfo) as conn:
        query = _idea_query(conn, idea)
        rows = conn.execute(
            "WITH q AS (SELECT %(query)s::tsquery AS query) "
            "SELECT t.id, ts_headline(%(language)s, t.line, q.query, %(options)s) "
            "FROM unnest(%(ids)s::bigint[], %(lines)s::text[]) AS t(id, line), q "
            "WHERE q.query::text <> '' AND to_tsvector(%(language)s, t.line) @@ q.query",
            {"language": LANGUAGE, "query": query, "ids": ids, "lines": [lines[i] for i in ids],
             "options": f'StartSel="{_START}", StopSel="{_STOP}", HighlightAll=true'},
        ).fetchall()  # fmt: skip
    return {
        project_id: escape(" ".join(line.split()))
        .replace(_START, _MARK_OPEN)
        .replace(_STOP, _MARK_CLOSE)
        for project_id, line in rows
    }
