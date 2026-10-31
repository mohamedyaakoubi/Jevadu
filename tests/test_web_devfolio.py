"""Devfolio's events and projects on the website (31 October 2026): the organiser of an event, its
own address, and the day a project was read. Every name and text is invented."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from test_pipeline_devfolio import FOUND, PAGE, save_project

from hackathon_memory.collect.devfolio import SITE
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import recorded_run
from hackathon_memory.pipeline.parse_pages import STEP, parse_devfolio
from hackathon_memory.search.filters import facts
from hackathon_memory.web.data import collected_at, event_page


@pytest.mark.integration
def test_the_organiser_of_a_devfolio_event_is_its_name_without_the_year(
    empty_database: str, tmp_path: Path
) -> None:
    migrate(empty_database)
    with recorded_run(empty_database, STEP) as run:
        parse_devfolio(save_project(tmp_path / "raw" / SITE), FOUND, ProjectStore(empty_database),
                       run)  # fmt: skip
    with psycopg.connect(empty_database) as conn:
        (pid,) = conn.execute("SELECT id FROM projects WHERE page_url = %s", (PAGE,)).fetchone()
    (row,) = [row for row in facts(empty_database, model="m", version="v") if row.project_id == pid]
    assert row.organiser == "Sample Hack"


def test_a_devfolio_event_and_project_have_their_own_addresses(tmp_path: Path) -> None:
    assert event_page(SITE, "sample-hack", PAGE) == "https://sample-hack.devfolio.co/"
    save_project(tmp_path / "raw" / SITE)
    ethglobal = tmp_path / "raw" / "ethglobal.com"  # the folder that the website is given
    assert collected_at(ethglobal, PAGE) == datetime(2026, 10, 31, 20, 5, tzinfo=UTC)
