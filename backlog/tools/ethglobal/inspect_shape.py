"""The shape of the saved project pages, for the parser. No request, no text of a page.

It prints counts, tag names, key names of the page data and the kinds of their values. A label of
a link or a title is printed only when it stands on many pages, so that it is a word of the site
and not a word of a team.

    .venv/Scripts/python.exe backlog/tools/ethglobal/inspect_shape.py
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from hackathon_memory.parse.pagedata import objects_with_key, page_data_text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RAW = Path.cwd() / "data" / "raw" / "ethglobal.com"
SECTIONS = ("project description", "how it's made")
KNOWN_H3 = ("created at", "winner of", *SECTIONS, "get the latest news and update")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
HOSTS = (
    ("github.com", "github"),
    ("gitlab.com", "gitlab"),
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
    ("hashscan.io", "hashscan"),
    ("vercel.app", "vercel"),
    ("netlify.app", "netlify"),
    ("ethglobal.com", "ethglobal"),
    ("ethglobal.b-cdn.net", "ethglobal cdn"),
)


def squash(text: str) -> str:
    return " ".join(text.split())


def host_kind(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return "inside the site"
    for end, kind in HOSTS:
        if host == end or host.endswith("." + end):
            return kind
    return "other"


def kind_of(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        if ISO_DATE.match(value):
            return "date text"
        if value.startswith(("http://", "https://")):
            return "link text"
        return "text" if value else "empty text"
    return type(value).__name__


def label_of(tag: Tag) -> str:
    return tag.name + "".join(f".{c}" for c in (tag.get("class") or [])[:2])


def next_tag(tag: Tag) -> Tag | None:
    sibling = tag.find_next_sibling()
    return sibling if isinstance(sibling, Tag) else None


pages = 0
h1_count: Counter[int] = Counter()
h1_parent: Counter[str] = Counter()
after_h1: Counter[str] = Counter()
name_agrees: Counter[str] = Counter()
data_objects: Counter[int] = Counter()
key_kinds: dict[str, Counter[str]] = defaultdict(Counter)
key_lengths: dict[str, list[int]] = defaultdict(list)
nested_keys: dict[str, Counter[str]] = defaultdict(Counter)
link_keys: dict[str, Counter[str]] = defaultdict(Counter)
header_link_labels: Counter[str] = Counter()
header_link_kinds: Counter[str] = Counter()
header_links_per_page: Counter[int] = Counter()
created_at_next: Counter[str] = Counter()
created_at_event_link: Counter[bool] = Counter()
section_container: dict[str, Counter[str]] = defaultdict(Counter)
section_children: dict[str, Counter[str]] = defaultdict(Counter)
section_own_titles_inside: dict[str, Counter[str]] = defaultdict(Counter)
section_text_agrees: dict[str, Counter[str]] = defaultdict(Counter)
section_link_kinds: Counter[str] = Counter()
other_h3_place: Counter[str] = Counter()
h3_order: Counter[tuple[str, ...]] = Counter()
media_tags: Counter[str] = Counter()
after_last_section: Counter[str] = Counter()

for meta_path in sorted(RAW.glob("*.meta.json")):
    body_path = meta_path.with_name(meta_path.name.replace(".meta.json", ".html"))
    if not body_path.exists():
        continue
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    soup = BeautifulSoup(body_path.read_bytes().decode("utf-8", errors="replace"), "lxml")
    pages += 1

    # --- the data of the page
    slug_and_id = urlsplit(meta["source_url"]).path.rsplit("/", 1)[-1]
    objects = [o for o in objects_with_key(page_data_text(soup), "tagline") if "slug" in o]
    data_objects[len(objects)] += 1
    data = objects[0] if objects else {}
    for key, value in data.items():
        kind = kind_of(value)
        key_kinds[key][kind] += 1
        if isinstance(value, str):
            key_lengths[key].append(len(value))
            if kind == "link text":
                link_keys[key][host_kind(value)] += 1
        elif isinstance(value, dict):
            nested_keys[key].update(value.keys())
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            nested_keys[key + "[]"].update(value[0].keys())
    if data:
        made = f"{data.get('slug')}-{data.get('uuid')}"
        name_agrees["the address is slug-uuid of the data"] += made == slug_and_id

    # --- the header
    h1s = soup.find_all("h1")
    h1_count[len(h1s)] += 1
    if h1s:
        h1 = h1s[0]
        h1_parent[label_of(h1.parent)] += 1
        following = next_tag(h1)
        after_h1[label_of(following) if following else "nothing"] += 1
        name = squash(h1.get_text())
        name_agrees["h1 is the name of the data"] += name == squash(str(data.get("name", "")))
        if following is not None:
            name_agrees["the tag after h1 is the tagline of the data"] += squash(
                following.get_text()
            ) == squash(str(data.get("tagline", "")))
        title = squash(soup.title.get_text()) if soup.title else ""
        name_agrees["the title starts with the name"] += title.startswith(name)
        h2 = soup.find("h2")
        name_agrees["the first h2 is the name"] += bool(h2) and squash(h2.get_text()) == name
        box = h1.parent
        for _ in range(3):
            if box is None or box.find("a", href=re.compile(r"^https?://")):
                break
            box = box.parent
        links = box.find_all("a", href=re.compile(r"^https?://")) if box is not None else []
        header_links_per_page[len(links)] += 1
        for link in links:
            header_link_labels[squash(link.get_text())[:40]] += 1
            header_link_kinds[host_kind(str(link["href"]))] += 1

    # --- the titles
    h3s = soup.find_all("h3")
    titles = [squash(h.get_text()).lower() for h in h3s]
    h3_order[tuple(t if t in KNOWN_H3 else "<a title of the team>" for t in titles)] += 1
    by_title = {squash(h.get_text()).lower(): h for h in h3s}

    created = by_title.get("created at")
    if created is not None:
        following = next_tag(created)
        created_at_next[label_of(following) if following else "nothing"] += 1
        has_event = following is not None and (
            (following.name == "a" and str(following.get("href", "")).startswith("/events/"))
            or following.find("a", href=re.compile(r"^/events/")) is not None
        )
        created_at_event_link[has_event] += 1

    containers: dict[str, Tag] = {}
    for title in SECTIONS:
        heading = by_title.get(title)
        if heading is None:
            section_container[title]["no such title"] += 1
            continue
        container = next_tag(heading)
        if container is None:
            section_container[title]["nothing after the title"] += 1
            continue
        containers[title] = container
        section_container[title][label_of(container)] += 1
        section_children[title].update(child.name for child in container.find_all(True))
        own = [h.name for h in container.find_all(re.compile(r"^h[1-6]$"))]
        section_own_titles_inside[title]["pages with titles of the team inside"] += bool(own)
        section_own_titles_inside[title].update(own)
        for link in container.find_all("a", href=True):
            section_link_kinds[host_kind(str(link["href"]))] += 1
        key = {"project description": "description", "how it's made": "howItsMade"}[title]
        if key in data:
            same = squash(container.get_text(" ")) == squash(str(data[key]))
            section_text_agrees[title]["the same as the data, spaces apart" if same else "differs"] += 1
        else:
            section_text_agrees[title][f"no key {key} in the data"] += 1

    for heading, title in zip(h3s, titles, strict=True):
        if title in KNOWN_H3:
            continue
        inside = [name for name, box in containers.items() if box in heading.parents]
        other_h3_place[f"inside the box of '{inside[0]}'" if inside else "outside both boxes"] += 1

    last = containers.get("how it's made")
    if last is not None:
        following = next_tag(last)
        after_last_section[label_of(following) if following else "nothing"] += 1

    media_tags.update(
        tag.name for tag in soup.find_all(["video", "iframe", "mux-player", "source", "audio"])
    )


def show(title: str, counter: Counter, limit: int = 12) -> None:
    print(f"{title}:")
    for value, count in counter.most_common(limit):
        print(f"  {count:4}  {value}")


def show_labels(title: str, counter: Counter) -> None:
    """A label is shown only when it stands on a tenth of the pages or more."""
    print(f"{title}:")
    rare = 0
    for value, count in counter.most_common():
        if count >= max(3, pages // 10):
            print(f"  {count:4}  {value!r}")
        else:
            rare += count
    print(f"  {rare:4}  <labels that stand on few pages, not shown>")


print(f"saved pages: {pages}")
show("objects of the page data with 'tagline' and 'slug', per page", data_objects)
show("number of h1 on a page", h1_count)
show("the parent of the first h1", h1_parent)
show("the tag after the first h1", after_h1)
show("agreements, in pages", name_agrees)
show("links in the header, per page", header_links_per_page)
show_labels("labels of the links in the header", header_link_labels)
show("where the links of the header go", header_link_kinds)
show("order of the h3 titles", h3_order, limit=8)
show("the tag after 'Created At'", created_at_next)
show("'Created At' is followed by a link to /events/", created_at_event_link)
for section in SECTIONS:
    show(f"the tag after '{section}'", section_container[section])
    show(f"tags inside the box of '{section}', over all pages", section_children[section], 25)
    show(f"titles of the team inside the box of '{section}'", section_own_titles_inside[section])
    show(f"the text of the box of '{section}' against the data", section_text_agrees[section])
show("an h3 that is not a title of the site stands", other_h3_place)
show("where the links inside the two texts go", section_link_kinds)
show("the tag after the box of 'how it's made'", after_last_section)
show("media tags in the page", media_tags)

print("keys of the project object: kinds of values, and how many pages")
for key in sorted(key_kinds):
    kinds = ", ".join(f"{kind} {count}" for kind, count in key_kinds[key].most_common())
    lengths = key_lengths.get(key)
    size = (
        f"; text length {min(lengths)} to {max(lengths)}, median {int(statistics.median(lengths))}"
        if lengths and not key.lower().startswith("auto")
        else ""
    )
    print(f"  {key}: {kinds}{size}")
print("keys inside the nested objects:")
for key in sorted(nested_keys):
    print(f"  {key}: {sorted(nested_keys[key])}")
print("keys of the project object that hold a link, and where it goes:")
for key in sorted(link_keys):
    print(f"  {key}: {dict(link_keys[key])}")


# ---------------------------------------------------------------- second pass: prizes, links, dates
def tree(value: object, path: str, into: Counter[str], depth: int = 0) -> None:
    """Key paths with the kind of each value. Never a value."""
    if depth > 6:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            tree(item, f"{path}.{key}", into, depth + 1)
    elif isinstance(value, list):
        into[f"{path}: list"] += 1
        for item in value[:1]:
            tree(item, f"{path}[]", into, depth + 1)
    else:
        into[f"{path}: {kind_of(value)}"] += 1


from hackathon_memory.parse.ethglobal_page import prize_lines  # noqa: E402

prize_tree: Counter[str] = Counter()
other_tree: Counter[str] = Counter()
line_agrees: Counter[str] = Counter()
lines_against_data: Counter[str] = Counter()
start_kinds: Counter[str] = Counter()
events: Counter[tuple[str, str]] = Counter()
source_link: Counter[str] = Counter()
demo_link: Counter[str] = Counter()
video_kinds: Counter[str] = Counter()
pool_prize: Counter[str] = Counter()
place_words: Counter[str] = Counter()
parts_in_h4: Counter[int] = Counter()

for meta_path in sorted(RAW.glob("*.meta.json")):
    body_path = meta_path.with_name(meta_path.name.replace(".meta.json", ".html"))
    if not body_path.exists():
        continue
    body = body_path.read_bytes()
    soup = BeautifulSoup(body.decode("utf-8", errors="replace"), "lxml")
    objects = [o for o in objects_with_key(page_data_text(soup), "tagline") if "slug" in o]
    if not objects:
        continue
    data = objects[0]
    for key in ("event", "video", "primaryRepository", "banner", "logo"):
        tree(data.get(key), key, other_tree)
    prizes = data.get("prizes") or []
    for prize in prizes:
        tree(prize, "prizes[]", prize_tree)
        pool_prize[kind_of(prize.get("poolPrize")) + f" {prize.get('poolPrize')!r}"[:14]] += 1
        place = str(prize.get("name") or "")
        # A place is a word of the site ("1st place", "Finalist"): shown when it repeats.
        place_words[place[:40]] += 1
    lines = prize_lines(body)
    lines_against_data["as many lines as prizes in the data" if len(lines) == len(prizes)
                       else "a different number"] += 1
    made = []
    for prize in prizes:
        inner = prize.get("prize") or {}
        sponsor = (inner.get("sponsor") or {}) if isinstance(inner, dict) else {}
        sponsor_name = sponsor.get("name") if isinstance(sponsor, dict) else None
        organization = sponsor.get("organization") if isinstance(sponsor, dict) else None
        if isinstance(organization, dict) and not sponsor_name:
            sponsor_name = organization.get("name")
        made.append(squash(f"{sponsor_name} - {inner.get('name') if isinstance(inner, dict) else ''} "
                           f"{prize.get('name') or ''}"))
    if prizes:
        line_agrees["every h4 line is 'sponsor - prize place' of the data"
                    if sorted(made) == sorted(lines) else "some line differs"] += 1
    for h3 in soup.find_all("h3"):
        if squash(h3.get_text()).lower() == "winner of":
            block = h3.find_next_sibling()
            for h4 in block.find_all("h4") if block else []:
                parts_in_h4[len([s for s in h4.strings if s.strip()])] += 1
    event = data.get("event") or {}
    start_kinds[kind_of(event.get("startTime"))] += 1
    events[(str(event.get("slug")), str(event.get("startTime"))[:10])] += 1

    header = soup.find("header")
    shown = {squash(a.get_text()): str(a["href"]) for a in header.find_all("a", href=True)}
    repo = (data.get("primaryRepository") or {}).get("url")
    source = shown.get("Source Code")
    if source is None:
        source_link["no 'Source Code' link"
                    + ("" if not (repo or data.get("sourceCodeUrl")) else ", but the data has one")] += 1
    elif source == data.get("sourceCodeUrl"):
        source_link["is sourceCodeUrl of the data"] += 1
    elif source == repo:
        source_link["is primaryRepository.url of the data"] += 1
    else:
        source_link["is neither"] += 1
    demo = shown.get("Live Demo")
    if demo is None:
        demo_link["no 'Live Demo' link" + ("" if not data.get("url") else ", but the data has one")] += 1
    else:
        demo_link["is url of the data" if demo == data.get("url") else "differs from the data"] += 1
    video = data.get("video") or {}
    video_kinds[", ".join(sorted(k for k, v in video.items() if v)) or "no video"] += 1

show("key paths of a prize in the data", prize_tree, 30)
show("key paths of event, video, repository, banner and logo", other_tree, 40)
show("poolPrize", pool_prize)
show_labels("the place of a prize (prizes[].name)", place_words)
show("prize lines of the page against the prizes of the data", lines_against_data)
show("each h4 line against the data", line_agrees)
show("text parts inside one h4 line", parts_in_h4)
show("the kind of event.startTime", start_kinds)
print("events: slug, day of startTime, saved pages")
for (slug, day), count in sorted(events.items(), key=lambda item: item[0][1]):
    print(f"  {count:4}  {slug}  {day}")
show("the 'Source Code' link of the header", source_link)
show("the 'Live Demo' link of the header", demo_link)
show("what the video object holds", video_kinds)
