"""The winners of the Africa page become winner entries. The saved files here are invented."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from hackathon_memory.collect.polite import FetchResult
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.db.migrate import migrate
from hackathon_memory.db.projects import ProjectStore
from hackathon_memory.db.runs import recorded_run
from hackathon_memory.parse.africa_winners import EVENT, read_africa_winners
from hackathon_memory.parse.project import Link
from hackathon_memory.parse.winner_entries import WinnerEntriesError
from hackathon_memory.pipeline.parse_pages import STEP, parse_winner_entries

SITE = "hedera-hackathon.hashgraph.swiss"
PAGE = f"https://{SITE}/"
SCRIPT_URL = f"https://{SITE}/_next/static/chunks/bbb.js"
LINK = "https://dorahacks.io/buidl/{}"
PAY = (
    '{title:"Invented Pay",logo:H.pay,buidlUrl:"https://dorahacks.io/buidl/1",'
    'description:"Pays shops. Ask @quill_invented."}'
)
SCRIPT = (
    'var H={pay:h("/logo/pay.png")};u={onchain:"Invented finance.",cross:"Invented cross."},'
    'f=[{id:"cross",label:"Cross-Track"},{id:"onchain",label:"On-Chain Finance"},'
    '{id:"ai",label:"AI & DePIN"}],'
    f"m={{onchain:[{PAY},"
    '{title:"Invented Post",fallbackLogo:"/x.png",buidlUrl:"https://dorahacks.io/buidl/2",'
    'description:"Moves parcels."}],'
    'ai:[{title:"Invented Vote",logo:H.vote,buidlUrl:"https://dorahacks.io/buidl/3",'
    'description:"Counts ballots."}],'
    f"cross:[{PAY}]}};export default m;"
)


def save(raw: Path, url: str, body: bytes, suffix: str) -> None:
    fetch = FetchResult(url, url, 200, body, "text/plain", "2026-10-12T21:00:00Z")
    RawStore(raw / SITE).save(fetch, body, received=body, collector="TestTool/0.1.0", suffix=suffix)


def saved(tmp_path: Path, script: str = SCRIPT) -> Path:
    raw = tmp_path / "raw"
    save(raw, PAGE, b"<html><body>an invented winners page</body></html>", ".html")
    save(raw, SCRIPT_URL, script.encode(), ".js")
    return raw


def test_each_winning_project_becomes_one_entry_with_all_its_tracks(tmp_path: Path) -> None:
    entries = read_africa_winners(saved(tmp_path) / SITE)
    pages = [entry.page for entry in entries]
    assert [page.name for page in pages] == ["Invented Pay", "Invented Post", "Invented Vote"]
    assert [page.prizes[0].track for page in pages] == [
        "On-Chain Finance and Cross-Track",  # its own track first
        "On-Chain Finance",
        "AI & DePIN",
    ]
    pay = pages[0]
    assert pay.page == f"{PAGE}#invented-pay"
    assert pay.event.name == EVENT
    assert pay.links == (Link("other", LINK.format(1), "The project's page"),)
    text = pay.sections[0].blocks[0].text
    assert text.startswith("Pays shops.") and "quill_invented" not in text
    assert pay.people_words_hidden == 1


def test_no_saved_page_means_no_entries(tmp_path: Path) -> None:
    assert read_africa_winners(tmp_path / "raw" / SITE) == []


def test_a_saved_page_without_its_script_is_refused(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    save(raw, PAGE, b"<html></html>", ".html")
    with pytest.raises(WinnerEntriesError, match="one saved script was expected, 0 found"):
        read_africa_winners(raw / SITE)


def test_a_script_whose_winners_are_not_grouped_by_track_is_refused(tmp_path: Path) -> None:
    raw = saved(tmp_path, f"var x=[{PAY}];")
    with pytest.raises(WinnerEntriesError, match="not grouped by track"):
        read_africa_winners(raw / SITE)


@pytest.mark.integration
def test_the_parse_step_keeps_them_next_to_the_entries_copied_by_hand(
    empty_database: str, tmp_path: Path
) -> None:
    migrate(empty_database)
    raw = saved(tmp_path)
    with recorded_run(empty_database, STEP) as run:
        parse_winner_entries(tmp_path / "by-hand", ProjectStore(empty_database), run, saved=raw)
    assert run.counts["winner_entries"] == 3 and run.counts["winner_entries_new"] == 3
    with psycopg.connect(empty_database) as conn:
        rows = conn.execute(
            "SELECT p.site, p.entry_kind, l.url FROM projects p "
            "JOIN links l ON l.project_id = p.id ORDER BY p.name"
        ).fetchall()
    assert rows == [(SITE, "winner_entry", LINK.format(n)) for n in (1, 2, 3)]
