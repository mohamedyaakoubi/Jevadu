"""Gate A, proof 1: the ETHGlobal collector lists every project with a Hedera prize.

Design section 14.2. Run it from the project folder:  python -m proofs.lists

This proof sends NO request. The site was promised that its pages are read one time, so the proof
does not read them again: it checks what the walk and the run left on disk, and whether the
promises of design 5.7 were kept there.

The pages stay in the data folder, outside git. The result file holds counts and the names of
events. It holds no text of a page, no address of a project and nothing about a person.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from datetime import datetime

from hackathon_memory import __version__
from hackathon_memory.collect.ethglobal import (
    ETHGLOBAL_SHAPE,
    data_paths,
    load_project_pages,
    planned_pages,
    read_and_not_kept,
    took_a_hedera_prize,
)
from hackathon_memory.collect.ethglobal_found import (
    SponsorNotKnown,
    hedera_sponsor,
    load_found,
    winners_of,
)
from hackathon_memory.collect.ethglobal_site import SITE
from hackathon_memory.collect.polite import (
    PAUSE_SECONDS,
    CollectorRefused,
    RequestCount,
    StopCollecting,
)
from hackathon_memory.collect.rawstore import RawStore, fingerprint
from hackathon_memory.collect.teamcut import CutFailed, cut_team
from hackathon_memory.settings import Settings
from proofs.result import ProofResult

DOES_NOT_PROVE = [
    "That the showcase list is complete. It is the site's own list with its own filter "
    '"partner: Hedera". A project with a Hedera prize that the site left out of it is not found.',
    "That the name of the tool and the contact address were in each request. The tests of the "
    "polite client prove that on an invented site. Nothing on disk can prove it afterwards.",
    "That the parser can read these pages. That is the next phase.",
    "Anything about the other sites. Only ethglobal.com was read.",
]


def _saved_pages(store: RawStore) -> list[dict]:
    """The small file of every saved project page (not of robots.txt)."""
    metas = []
    for meta_path in sorted(store.folder.glob("*.meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if store.has(meta["source_url"]):  # a page saved as .html
            metas.append(meta)
    return metas


def _seconds(stamp: str) -> float:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z").timestamp()


def run(settings: Settings | None = None) -> int:
    settings = settings or Settings()
    result = ProofResult(proof="lists")
    result.does_not_prove.extend(DOES_NOT_PROVE)
    paths = data_paths(settings)

    # --- the walk through the Hedera list
    try:
        found = load_found(paths.found_list)
    except CollectorRefused as refusal:
        result.check("the file of the walk can be read", False, str(refusal))
        return result.finish()
    if not result.check(
        "a walk through the Hedera list of the showcase was made",
        found is not None,
        "" if found else "no walk yet: python -m hackathon_memory.collect ethglobal --find",
    ):
        return result.finish()
    result.check(
        "the walk reached the last page of the list",
        found.complete,
        f"{found.pages_read} pages, {found.listed} projects in {len(found.listed_by_event)} events",
    )
    if found.last_row:
        result.check(
            "every page of the list started with the row that the page before ended with",
            found.page_ends_not_shared == 0,
            f"{found.page_ends_not_shared} page end(s) where it did not: the list stood still",
        )
    else:
        result.does_not_prove.append(
            "That the list stood still while it was read. This walk was made before the tool "
            "noted, at each page end, whether the next page started with the same row. One page "
            "end was compared by hand, and the number of rows that came twice fits."
        )

    # --- which sponsor id is Hedera, and the plan that follows
    try:
        by_hand = load_project_pages(paths.page_list)
        sponsor = hedera_sponsor(found, by_hand)
        planned = planned_pages(paths).pages
    except (CollectorRefused, SponsorNotKnown) as unsure:
        result.check("the pages seen by hand say which sponsor id is Hedera", False, str(unsure))
        return result.finish()
    winners = winners_of(found, sponsor)
    seen = sum(1 for project in found.with_prize if project.page in set(by_hand))
    result.check(
        "the pages seen by hand say which sponsor id is Hedera",
        True,
        f"{seen} page(s) seen by hand are in the walk, and they share exactly one sponsor id",
    )

    # --- every page of the plan was read once, and nothing else was saved
    store = RawStore(paths.raw_dir)
    try:
        not_kept = read_and_not_kept(paths.runs_dir)
    except CollectorRefused as refusal:
        result.check("the records of the runs can be read", False, str(refusal))
        return result.finish()
    metas = _saved_pages(store)
    saved = {meta["source_url"] for meta in metas}
    not_read = [page for page in planned if page not in saved and page not in not_kept]
    result.check(
        "every page of the plan was read",
        not not_read,
        f"{len(planned)} planned: {len(saved & set(planned))} saved, "
        f"{len(not_kept & set(planned))} read and not kept, {len(not_read)} not read yet",
    )
    result.check(
        "every winner of a Hedera prize that the walk found is saved",
        all(page in saved for page in winners),
        f"{sum(1 for page in winners if page in saved)} of {len(winners)}",
    )
    result.check(
        "no page outside the plan is saved",
        saved <= set(planned),
        f"{len(saved - set(planned))} page(s) outside the plan",
    )

    # --- each saved page: not edited, a Hedera prize, no person, the tool named
    edited = no_prize = unsafe = other_tool = 0
    sizes: list[int] = []
    for meta in metas:
        page = store.load(meta["source_url"])
        body = page.read() if page else b""
        sizes.append(len(body))
        edited += fingerprint(body) != meta["sha256"]
        no_prize += not took_a_hedera_prize(body)
        try:
            _, cut = cut_team(body, ETHGLOBAL_SHAPE.project_cut)
            unsafe += bool(cut.elements_removed or cut.json_keys_removed or cut.strings_guarded)
        except CutFailed:
            unsafe += 1
        other_tool += meta.get("collector") != f"{settings.collector_name}/{__version__}"
    result.check(
        "no saved page was edited after it was saved (fingerprints)",
        edited == 0,
        f"{edited} edited",
    )
    result.check(
        'every saved page shows a Hedera prize in its "Winner of" block',
        bool(metas) and no_prize == 0,
        f"{len(metas) - no_prize} of {len(metas)}",
    )
    result.check(
        "no saved page holds a personal tag, a profile link, an avatar or a data key for people",
        unsafe == 0,
        f"{unsafe} page(s) where the team cut would still find something",
    )
    result.check(
        "every saved page names this tool as the one that fetched it",
        other_tool == 0,
        f"{other_tool} page(s) fetched by something else",
    )

    # --- the pause and the limit
    times = sorted(_seconds(meta["fetched_at"]) for meta in metas)
    gaps = [later - earlier for earlier, later in zip(times, times[1:], strict=False)]
    smallest = min(gaps) if gaps else None
    result.check(
        "two saved pages were never fetched less than two seconds apart",
        smallest is None or smallest >= PAUSE_SECONDS,
        f"the smallest gap is {smallest:.0f} s" if smallest is not None else "one page only",
    )
    count = RequestCount(paths.request_count, SITE)
    try:
        sent = count.sent()
        result.check(
            "the requests to the site, over all commands, stay inside the limit",
            0 < sent <= count.limit,
            f"{sent} of {count.limit}",
        )
    except StopCollecting as stop:
        sent = None
        result.check("the count of requests can be read", False, str(stop))

    # --- numbers for the reader: counts and names of events only
    event_of = {project.page: project.event for project in found.with_prize}
    with_prize = Counter(project.event for project in found.with_prize)
    hedera = Counter(event_of[page] for page in winners)
    kept = Counter(event_of[page] for page in saved if page in event_of)
    result.measurements.update(
        {
            "site": SITE,
            "list_pages_read": found.pages_read,
            "projects_in_the_list": found.listed,
            "projects_with_a_prize_of_some_sponsor": len(found.with_prize),
            "projects_with_a_hedera_prize": len(winners),
            "pages_seen_by_hand": len(by_hand),
            "pages_planned": len(planned),
            "pages_saved": len(metas),
            "pages_read_and_not_kept": len(not_kept & set(planned)),
            "requests_sent_over_all_commands": sent,
            "request_limit": count.limit,
            "smallest_gap_between_two_saved_pages_s": smallest,
            "saved_page_bytes": (
                {
                    "smallest": min(sizes),
                    "median": int(statistics.median(sizes)),
                    "largest": max(sizes),
                    "total": sum(sizes),
                }
                if sizes
                else {}
            ),
            "by_event": {
                event: {
                    "in_the_list": listed,
                    "with_a_prize_of_some_sponsor": with_prize.get(event, 0),
                    "with_a_hedera_prize": hedera.get(event, 0),
                    "pages_saved": kept.get(event, 0),
                }
                for event, listed in found.listed_by_event.items()
            },
        }
    )
    return result.finish()


if __name__ == "__main__":
    sys.exit(run())
