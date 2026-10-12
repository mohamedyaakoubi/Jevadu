"""Three invented projects and a stand-in Google, for the tests of the embeddings and the search.

The real google-genai library runs, with the network faked (googlefake.py). A vector here says
which invented topic a text is about, so that "close in meaning" can be tested.
"""

from __future__ import annotations

import psycopg

from fakes import project_page
from googlefake import FakeGoogle
from hackathon_memory.db.embeddings import EmbeddingStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import Run, recorded_run
from hackathon_memory.finops.calls import MemoryStore
from hackathon_memory.finops.meter import Meter, MeteredClient, Tags
from hackathon_memory.llm.embeddings import SEARCH_MODEL
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.pipeline import embed

TOPICS = ("vendor", "parcel", "ballot")
PAGES = {
    "pebble-pay": ("Pebble Pay", "<p>A street vendor takes a coin.</p>"),
    "cedar-post": ("Cedar Post", "<p>Every parcel is logged when it moves.</p>"),
    "fern-vote": ("Fern Vote", "<p>A ballot for a small club, counted in the open.</p>"),
}


def vector_for(text: str) -> list[float]:
    values = [0.0] * 3072
    for place, topic in enumerate(TOPICS):
        if topic in text.lower():
            values[place] = 1.0
    if not any(values):
        values[3071] = 1.0
    return values


def three_projects(empty_database: str) -> str:
    """The database, with its tables and the three invented projects."""
    migrate(empty_database)
    store = ProjectStore(empty_database)
    for slug, (name, text) in PAGES.items():
        html = project_page(name=name, slug=slug, short_line=f"{name}, invented.", description=text)
        page = f"https://ethglobal.com/showcase/{slug}-x1y2z"
        store.save(read_project_page(html, page), "a" * 64)
    return empty_database


def google() -> tuple[MeteredClient, FakeGoogle, MemoryStore]:
    """A counted client over the stand-in Google, and the ledger of its calls."""
    fake = FakeGoogle()
    fake.vector_for = vector_for
    calls = MemoryStore()
    meter = Meter(calls, "test", location="global")
    return MeteredClient(fake.client(), meter, Tags(purpose="embed_document")), fake, calls


def embed_all(database: str, client: MeteredClient) -> Run:
    with recorded_run(database, embed.STEP) as run:
        embed.embed_pages(EmbeddingStore(database), client, run, model=SEARCH_MODEL)
    return run


def ids_of(database: str) -> dict[str, int]:
    with psycopg.connect(database) as conn:
        return {name: number for number, name in conn.execute("SELECT id, name FROM projects")}
