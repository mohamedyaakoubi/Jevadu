"""Devfolio's saved projects in the parse step (31 October 2026), on a real PostgreSQL: a saved
answer becomes a project with its event's dates, and a second run reads nothing again. Every name
and text is invented."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg
import pytest

from hackathon_memory.collect.devfolio import (
    SITE,
    SUFFIX,
    Event,
    Found,
    Track,
    project_address,
)
from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import recorded_run
from hackathon_memory.pipeline.parse_pages import STEP, parse_devfolio

pytestmark = pytest.mark.integration

EVENT = Event("sample-hack", "sample-hack", "Sample Hack 2025", "2025-02-23T17:00:00+00:00",
              "2025-03-01T17:30:00+00:00", (Track("h1", "Hedera Builder", "Hedera"),))  # fmt: skip
FOUND = Found("2026-10-31T20:00:00Z", 1, {"sample-hack": EVENT}, {"pebble-pay-a1": "sample-hack"},
              {"pebble-pay-a1": ("h1",)})  # fmt: skip
PAGE = "https://devfolio.co/projects/pebble-pay-a1"


def save_project(folder: Path) -> RawStore:
    """The saved answer of one invented project, without its members, as the read saves it."""
    project = {"slug": "pebble-pay-a1", "name": "Pebble Pay", "tagline": "Pay with a coin.",
               "description": [{"title": "The problem it solves",
                                "content": "Vendors wait. Our topic: 0.0.3456781 on testnet."}],
               "links": "https://github.com/sample-org/pebble-pay", "video_url": "",
               "prizes": [{"uuid": "p1", "name": "First Prize: Hedera Builder"}],
               "prize_tracks": [], "hashtags": []}  # fmt: skip
    event = {"name": "Sample Hack 2025", "slug": "sample-hack"}
    body = json.dumps({"project": project, "hackathon": event}).encode()
    url = project_address("pebble-pay-a1")
    store = RawStore(folder)
    fetch = FetchResult(url, url, 200, body, "application/json", "2026-10-31T20:05:00Z")
    store.save(fetch, body, received=body, collector="TestTool/0.1.0",
               team_cut={"members_cut": 2}, suffix=SUFFIX)  # fmt: skip
    return store


def test_a_saved_devfolio_project_becomes_a_project_with_its_events_dates(
    empty_database: str, tmp_path: Path
) -> None:
    migrate(empty_database)
    store = save_project(tmp_path / "raw" / SITE)
    with recorded_run(empty_database, STEP) as run:
        parse_devfolio(store, FOUND, ProjectStore(empty_database), run)
    assert run.counts["new"] == 1 and run.counts["event_ends_written"] == 1
    with psycopg.connect(empty_database) as conn:
        (pid, site, prize, starts, ends, name) = conn.execute(
            "SELECT p.id, p.site, p.prize_state, e.starts_at, e.ends_on, e.name FROM projects p "
            "JOIN events e ON e.id = p.event_id WHERE p.page_url = %s",
            (PAGE,),
        ).fetchone()
        sponsor = conn.execute("SELECT sponsor FROM prizes WHERE project_id = %s",
                               (pid,)).fetchone()[0]  # fmt: skip
    assert (site, prize, name) == (SITE, "hedera_prize", "Sample Hack 2025")
    assert (starts, ends, sponsor) == (datetime(2025, 2, 23, 17, tzinfo=UTC), date(2025, 3, 1),
                                       "Hedera")  # fmt: skip
    with recorded_run(empty_database, STEP) as run:  # read again: nothing changed
        parse_devfolio(store, FOUND, ProjectStore(empty_database), run)
    assert run.counts["same"] == 1 and run.counts["new"] == 0
    with recorded_run(empty_database, STEP) as run:  # no find yet: nothing to do
        parse_devfolio(store, None, ProjectStore(empty_database), run)
    assert run.counts["pages"] == 0
