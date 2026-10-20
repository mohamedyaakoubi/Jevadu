"""The parser on every saved project page. Counts only: no text of a page, no address, no id.

It also compares what the parser reads with the walk through the Hedera list: a page takes a
Hedera prize exactly when the list names the sponsor id of Hedera for it.

    .venv/Scripts/python.exe backlog/tools/ethglobal/parse_all.py
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from hackathon_memory.collect.ethglobal import data_paths, planned_pages
from hackathon_memory.collect.ethglobal_found import load_found
from hackathon_memory.parse.ethglobal_page import PageShapeChanged, read_project_page
from hackathon_memory.parse.project import HEDERA_PRIZE, NO_PRIZE, OTHER_PRIZE
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
paths = data_paths(Settings())
planned = planned_pages(paths)
found = load_found(paths.found_list)
with_any_prize = {project.page for project in found.with_prize}
event_of = {project.page: project.event for project in found.projects}

pages = 0
shape: Counter[str] = Counter()
states: Counter[str] = Counter()
against_list: Counter[str] = Counter()
link_kinds: Counter[str] = Counter()
link_labels: Counter[str] = Counter()
code_hosts: Counter[str] = Counter()
hedera_sponsor_ids: Counter[str] = Counter()
prize_kinds: Counter[str] = Counter()
ids_per_page: Counter[int] = Counter()
id_facts: Counter[str] = Counter()
events: Counter[str] = Counter()
event_names_differ = 0
video = 0
no_start = 0
text_sizes: list[int] = []
both_texts: list[int] = []

for meta_path in sorted(paths.raw_dir.glob("*.meta.json")):
    body_path = meta_path.with_name(meta_path.name.replace(".meta.json", ".html"))
    if not body_path.exists():
        continue
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    url = meta["source_url"]
    pages += 1
    try:
        page = read_project_page(body_path.read_bytes(), url)
    except PageShapeChanged as changed:
        # The message of the parser names a rule, never a text of the page.
        shape[f"SHAPE: {str(changed)[:90]}"] += 1
        continue
    shape["read"] += 1
    states[page.prize_state] += 1
    listed = (
        HEDERA_PRIZE
        if url in planned.hedera_in_the_list
        else OTHER_PRIZE
        if url in with_any_prize
        else NO_PRIZE
    )
    against_list[
        "the same as the list" if listed == page.prize_state
        else f"the list says {listed}, the page says {page.prize_state}"
    ] += 1
    event_names_differ += event_of.get(url) != page.event.name
    events[f"{page.event.slug}  {str(page.event.starts_at)[:10]}"] += 1
    no_start += page.event.starts_at is None
    for link in page.links:
        link_kinds[link.kind] += 1
        link_labels[link.label if link.kind != "other" else "<another label>"] += 1
        if link.kind == "code":
            code_hosts[(urlsplit(link.url).hostname or "").lower()] += 1
    for prize in page.prizes:
        prize_kinds[f"{prize.kind}, pool {prize.pool}"] += 1
        if prize.sponsor.lower() == "hedera":
            hedera_sponsor_ids[str(prize.sponsor_id)] += 1
    video += page.has_video
    ids_per_page[len(page.hedera_ids)] += 1
    for found_id in page.hedera_ids:
        id_facts[
            ("EVM address" if found_id.entity_id.startswith("0x") else "id")
            + f", network {found_id.network}, kind {found_id.said_kind}, "
            + ("in a HashScan link" if found_id.in_hashscan_link else "in the text")
        ] += 1
    sizes = [len(section.text) for section in page.sections]
    text_sizes.extend(sizes)
    both_texts.append(sum(sizes))


def show(title: str, counter: Counter) -> None:
    print(f"{title}:")
    for value, count in sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))):
        print(f"  {count:4}  {value}")


print(f"saved pages: {pages}")
show("what the parser did", shape)
show("the prize of a project", states)
show("against the walk through the list", against_list)
print(f"pages whose event name differs from the list: {event_names_differ}")
print(f"pages with no start time of the event: {no_start}")
show("events (slug, day of the start)", events)
show("links of the header, by kind", link_kinds)
show("links of the header, by label", link_labels)
show("where the code links go", code_hosts)
show("the sponsor id of a prize whose sponsor is named Hedera", hedera_sponsor_ids)
show("kinds of prizes", prize_kinds)
print(f"pages with a video: {video}")
show("Hedera ids on a page", ids_per_page)
show("what the page says about an id", id_facts)
if both_texts:
    both_texts.sort()
    print(
        f"characters of the two texts of a page together: smallest {both_texts[0]}, median "
        f"{int(statistics.median(both_texts))}, largest {both_texts[-1]}, sum {sum(both_texts)}"
    )
