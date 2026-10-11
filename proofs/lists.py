"""Gate A, proof 1: the ETHGlobal collector lists every project that the showcase ties to Hedera.

Design section 14.2. Run it from the project folder:  python -m proofs.lists

This proof sends NO request. A page of the site is read one time, so the proof does not read it
again: it checks what the walk and the run left on disk, and whether the rules of design 5.7 were
kept there.

The pages stay in the data folder, outside git. The result file holds counts and the names of
events. It holds no text of a page, no address of a project and nothing about a person.
"""

from __future__ import annotations

import statistics
import sys
from collections import Counter
from datetime import datetime

from hackathon_memory import __version__
from hackathon_memory.collect.ethglobal import (
    ETHGLOBAL_SHAPE,
    data_paths,
    pages_in_run_records,
    planned_pages,
    read_and_not_kept,
    request_count,
)
from hackathon_memory.collect.ethglobal_found import load_found
from hackathon_memory.collect.ethglobal_site import SITE
from hackathon_memory.collect.polite import PAUSE_SECONDS, CollectorRefused, StopCollecting
from hackathon_memory.collect.rawstore import RawStore, fingerprint
from hackathon_memory.collect.teamcut import CutFailed, cut_team
from hackathon_memory.parse.ethglobal_page import took_a_hedera_prize
from hackathon_memory.settings import Settings
from proofs.result import ProofResult

DOES_NOT_PROVE = [
    "That the showcase list is complete. It is the site's own list with its own filter "
    '"partner: Hedera". A project that the site left out of it is not found.',
    "That the name of the tool and the contact address were in each request. The tests of the "
    "polite client prove that on an invented site. Nothing on disk can prove it afterwards.",
    "That the parser can read these pages. That is the next phase.",
    "Anything about the other sites. Only ethglobal.com was read.",
]


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
    result.check(
        "every page of the list started with the row that the page before ended with",
        found.page_ends_not_shared == 0,
        f"{found.page_ends_not_shared} page end(s) where it did not: the list stood still",
    )

    # --- which sponsor id is Hedera, and the plan that follows
    try:
        planned = planned_pages(paths)
    except CollectorRefused as unsure:
        result.check("the pages seen by hand say which sponsor id is Hedera", False, str(unsure))
        return result.finish()
    result.check(
        "the pages seen by hand say which sponsor id is Hedera",
        True,
        f"{planned.by_hand} page(s) seen by hand, and they share exactly one sponsor id",
    )
    plan, in_the_list, winners = set(planned.pages), planned.in_the_list, planned.hedera_in_the_list

    # --- every page of the plan was read once, and nothing else was saved
    store = RawStore(paths.raw_dir)
    try:
        not_kept = read_and_not_kept(paths.runs_dir)
        not_found = pages_in_run_records(paths.runs_dir, "pages_not_found")
    except CollectorRefused as refusal:
        result.check("the records of the runs can be read", False, str(refusal))
        return result.finish()
    metas = [page.meta for page in store.saved()]  # the project pages, not robots.txt
    saved = {meta["source_url"] for meta in metas}
    accounted = (not_kept | not_found) - saved
    not_read = plan - saved - accounted
    result.check(
        "every page of the plan was read",
        not not_read,
        f"{len(plan)} planned: {len(saved & plan)} saved, {len(accounted & plan)} read and not "
        f"kept or gone from the site, {len(not_read)} not read yet",
    )
    result.check(
        "every project of the Hedera list is saved",
        in_the_list <= saved | accounted,
        f"{len(in_the_list & saved)} of {len(in_the_list)} saved, "
        f"{len(in_the_list & accounted)} read and not kept or gone from the site",
    )
    result.check(
        "no page outside the plan is saved",
        saved <= plan,
        f"{len(saved - plan)} page(s) outside the plan",
    )

    # --- each saved page: not edited, as the list says, no person, the tool named
    edited = differ = unsafe = other_tool = 0
    sizes: list[int] = []
    for meta in metas:
        url = meta["source_url"]
        page = store.load(url)
        body = page.read() if page else b""
        sizes.append(len(body))
        edited += fingerprint(body) != meta["sha256"]
        # A page of the list shows a Hedera prize exactly when the list names one. A page that
        # is not in the list is kept only when it shows one.
        differ += took_a_hedera_prize(body) != (url in winners if url in in_the_list else True)
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
        'the list and the "Winner of" block of each saved page agree about a Hedera prize',
        bool(metas) and differ == 0,
        f"{differ} of {len(metas)} page(s) differ",
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
    count = request_count(paths)
    try:
        sent = count.sent()
        result.check(
            "the requests to the site, over all commands, stay inside the limit of the site",
            0 < sent <= count.limit,
            f"{sent} of {count.limit}",
        )
    except StopCollecting as stop:
        sent = None
        result.check("the count of requests can be read", False, str(stop))

    # --- numbers for the reader: counts and names of events only
    event_of = {project.page: project.event for project in found.projects}
    with_prize = {project.page for project in found.with_prize}
    by_event: dict[str, Counter[str]] = {event: Counter() for event in found.listed_by_event}
    for page, event in event_of.items():
        kind = (
            "with_a_hedera_prize"
            if page in winners
            else "with_a_prize_of_another_sponsor_only"
            if page in with_prize
            else "with_no_prize"
        )
        by_event[event].update(["in_the_list", kind] + (["pages_saved"] if page in saved else []))
    kinds = (
        "in_the_list",
        "with_a_hedera_prize",
        "with_a_prize_of_another_sponsor_only",
        "with_no_prize",
        "pages_saved",
    )
    result.measurements.update(
        {
            "site": SITE,
            "list_pages_read": found.pages_read,
            "projects_in_the_list": found.listed,
            "projects_with_a_hedera_prize": len(winners),
            "projects_with_a_prize_of_another_sponsor_only": len(with_prize - winners),
            "projects_with_no_prize": found.listed - len(with_prize),
            "pages_seen_by_hand": planned.by_hand,
            "pages_planned": len(plan),
            "pages_saved": len(metas),
            "pages_read_and_not_kept_or_gone": len(accounted & plan),
            "pages_where_the_list_and_the_page_differ": differ,
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
                event: {kind: counts.get(kind, 0) for kind in kinds}
                for event, counts in by_event.items()
            },
        }
    )
    return result.finish()


if __name__ == "__main__":
    sys.exit(run())
