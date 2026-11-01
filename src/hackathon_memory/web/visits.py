"""What the visitors of the public copy do (design 12.5, screen S9; 1 November 2026).

To learn what interests the visitors of the public copy, the jury of a hackathon above all, each
action of a visitor is one row: a search and its words, the filters, a card opened, the graph or
the charts, a check of a repository, a registration, a comparison by Gemini, a note read. A row
keeps the visitor's salted code (web/public.py), never an address or a name; the place that
Vercel finds for the address (its headers x-vercel-ip-country, -country-region and -city); the
other site that the visitor came from, without its query; and the browser and the system, in two
words. The copy's owner is left out. Only the copy's owner reads the rows, on /owner/visits, next
to what is left of the public budget, and deletes them when the event is over:

    python -m hackathon_memory.web.visits show          a summary in the terminal
    python -m hackathon_memory.web.visits delete --yes  every noted action, for good

Both work on the public copy's database (PUBLIC_DATABASE_URL), or with --laptop on the laptop's.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg.types.json import Jsonb

FILTERS = ("event", "year", "category", "proof", "life", "winner", "organiser", "mainnet")
# No action of its own: files, sign-ins, the copy's own pages, and the steps of a running check.
NOT_ACTIONS = ("/static/", "/_vercel/", "/owner", "/github/", "/health", "/robots.txt",
               "/person-check", "/check/progress")  # fmt: skip
TYPING = timedelta(seconds=20)  # searches typed one after another count as the last one
LONGEST = 300  # the characters kept of an address, a site, or the words of a search
_BROWSERS = (("edg/", "Edge"), ("opr/", "Opera"), ("firefox/", "Firefox"), ("chrome/", "Chrome"),
             ("safari/", "Safari"))  # fmt: skip
_SYSTEMS = (("android", "Android"), ("iphone", "iOS"), ("ipad", "iOS"), ("windows", "Windows"),
            ("mac os", "macOS"), ("linux", "Linux"))  # fmt: skip


@dataclass(frozen=True)
class Action:
    at: datetime
    action: str
    detail: dict


@dataclass
class Visit:
    """What one visitor did, its actions in their order."""

    visitor: str
    place: str
    referrer: str | None
    device: str
    actions: list[Action] = field(default_factory=list)

    @property
    def first(self) -> datetime:
        return self.actions[0].at

    @property
    def last(self) -> datetime:
        return self.actions[-1].at


def action_of(path: str, params: Mapping[str, str]) -> tuple[str, dict] | None:
    """What one request of a visitor did, and about what; None for a request that is no action
    of its own. `params` holds each parameter once, its values joined by |."""
    if any(path == one or path.startswith(one) for one in NOT_ACTIONS):
        return None
    parts = [part for part in path.split("/") if part]
    if path == "/":
        detail = {k: params[k][:LONGEST] for k in ("idea", "mode", "ai", "view", "page")
                  if params.get(k)}  # fmt: skip
        chosen = {k: params[k] for k in FILTERS if params.get(k)}
        if chosen:
            detail["filters"] = chosen
        if params.get("open", "").isdigit():
            return "card", {**detail, "project": int(params["open"])}
        if params.get("view") in ("graph", "charts", "overview", "mainnet"):
            view = params["view"]
            return (view if view in ("graph", "mainnet") else "charts"), detail
        if params.get("idea"):
            return ("gemini" if params.get("ai") == "1" else "search"), detail
        if chosen:
            return "filter", detail
        return ("list" if params.get("page", "1") not in ("", "1") else "home"), detail
    if len(parts) >= 2 and parts[0] == "project" and parts[1].isdigit():
        if parts[-1] == "read-again":
            return "read-again", {"project": int(parts[1])}
        return "card", {"project": int(parts[1])}
    if path == "/check" and params.get("repo"):
        return "check", {k: params[k][:LONGEST] for k in ("repo", "event", "starts", "ends")
                         if params.get(k)}  # fmt: skip
    if path == "/compare":
        return "compare", {k: v[:LONGEST] for k, v in params.items()}
    if parts and parts[0] == "register":
        return "register", {"step": parts[1] if len(parts) > 1 else "send"}
    if len(parts) == 2 and parts[0] == "about":
        return "about", {"note": parts[1][:60]}
    if path == "/method":
        return "about", {"note": "method"}
    return None


def place_of(headers: Mapping[str, str]) -> tuple[str | None, str | None, str | None]:
    """The place that Vercel finds for the visitor's address: its country (ISO 3166-1), region
    and city. The letters of a city beyond ASCII come escaped, as in an address."""

    def one(name: str) -> str | None:
        return unquote(headers.get(name, "").strip())[:80] or None

    return one("x-vercel-ip-country"), one("x-vercel-ip-country-region"), one("x-vercel-ip-city")


def referrer_of(headers: Mapping[str, str], host: str) -> str | None:
    """The other site that the visitor came from: its name and the path of its page, never its
    query; None for a page of the copy itself."""
    given = urlsplit(headers.get("referer", "").strip())
    if not given.netloc or given.netloc.lower() == host.lower():
        return None
    return (given.netloc + given.path)[:LONGEST]


def device_of(agent: str) -> str:
    """The browser and the system of a visitor, in two words; "robot" for a program."""
    text = agent.lower()
    if any(word in text for word in ("bot", "crawler", "spider", "headless")):
        return "robot"
    browser = next((name for key, name in _BROWSERS if key in text), "a browser")
    system = next((name for key, name in _SYSTEMS if key in text), "another system")
    return f"{browser} on {system}"


def record(conninfo: str, visitor: str, action: str, detail: dict, path: str,
           place: tuple[str | None, str | None, str | None], referrer: str | None,
           device: str) -> None:  # fmt: skip
    """One action of a visitor."""
    with psycopg.connect(conninfo, connect_timeout=5) as conn:
        conn.execute(
            "INSERT INTO visit_actions (visitor, action, detail, path, country, region, city, "
            "referrer, device) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (visitor, action, Jsonb(detail), path[:LONGEST], *place, referrer, device),
        )


def visits(conninfo: str) -> list[Visit]:
    """Every visitor's actions in their order, the visitor seen last first. Searches that a
    visitor typed one after another, each within TYPING of the one before, count as the last."""
    with psycopg.connect(conninfo, connect_timeout=10) as conn:
        rows = conn.execute(
            "SELECT visitor, at, action, detail, country, city, referrer, device "
            "FROM visit_actions ORDER BY visitor, at"
        ).fetchall()
    found: dict[str, Visit] = {}
    for visitor, at, action, detail, country, city, referrer, device in rows:
        visit = found.setdefault(visitor, Visit(visitor, "", None, device or "a browser"))
        place = ", ".join(one for one in (city, country) if one)
        if place:
            visit.place = place
        if referrer and visit.referrer is None:
            visit.referrer = referrer
        one = Action(at, action, detail or {})
        last = visit.actions[-1] if visit.actions else None
        if (last is not None and action == last.action and action in ("search", "gemini")
                and at - last.at <= TYPING):  # fmt: skip
            visit.actions[-1] = one
        else:
            visit.actions.append(one)
    return sorted(found.values(), key=lambda visit: visit.last, reverse=True)


def summary(found: Sequence[Visit]) -> dict[str, list[tuple[object, int]]]:
    """The places, the sites, the projects, the searches, the checks and the actions that come
    most, at most 15 of each."""
    actions = [one for visit in found for one in visit.actions]
    counted = {
        "places": Counter(visit.place or "not known" for visit in found),
        "sources": Counter(visit.referrer for visit in found if visit.referrer),
        "projects": Counter(one.detail["project"] for one in actions
                            if one.action == "card" and "project" in one.detail),
        "ideas": Counter(one.detail["idea"] for one in actions
                         if one.action in ("search", "gemini") and one.detail.get("idea")),
        "checks": Counter(one.detail["repo"] for one in actions
                          if one.action == "check" and one.detail.get("repo")),
        "actions": Counter(one.action for one in actions),
    }  # fmt: skip
    return {name: counter.most_common(15) for name, counter in counted.items()}


def described(one: Action, projects: Mapping[int, str], events: Mapping[str, str]) -> str:
    """One action in words, for the copy's owner."""
    detail = one.detail
    project = detail.get("project")
    named = projects.get(project, f"project {project}") if project is not None else ""
    idea = f"“{detail['idea']}”" if detail.get("idea") else ""
    words = {
        "home": "opened the start page",
        "list": f"went to page {detail.get('page')} of the list",
        "search": f"searched {idea}" + (" by meaning" if detail.get("mode") == "meaning" else ""),
        "gemini": f"asked Gemini to sort {idea}",
        "filter": "filtered the list",
        "card": f"opened the card of {named}",
        "graph": "looked at the graph" + (f" of {idea}" if idea else ""),
        "charts": "looked at the charts" + (f" of {idea}" if idea else ""),
        "mainnet": "looked at the main network" + (f" of {idea}" if idea else ""),
        "compare": "asked Gemini to compare",
        "register": f"registration, step {detail.get('step')}",
        "about": f"read the note “{detail.get('note')}”",
        "read-again": f"asked to read {named} again",
    }.get(one.action, one.action)
    if one.action == "check":
        event = detail.get("event", "")
        words = f"checked {detail.get('repo')}"
        if event == "other":
            words += f" with the dates {detail.get('starts')} to {detail.get('ends')}"
        elif event:
            words += f" against {events.get(event, event)}"
    filters = detail.get("filters") or {}
    if filters:
        chosen = "; ".join(
            f"{name}: " + ", ".join(events.get(value, value) if name == "event" else value
                                    for value in text.split("|"))
            for name, text in filters.items()
        )  # fmt: skip
        words += f" ({chosen})"
    if detail.get("status"):
        words += f", answered {detail['status']}"
    return words


def delete(conninfo: str) -> int:
    """Every noted action, for good; how many there were."""
    with psycopg.connect(conninfo, connect_timeout=10) as conn:
        return conn.execute("DELETE FROM visit_actions").rowcount


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hackathon_memory.web.visits")
    parser.add_argument("what", choices=("show", "delete"))
    parser.add_argument("--yes", action="store_true", help="delete with no question")
    parser.add_argument("--laptop", action="store_true", help="the laptop's database")
    arguments = parser.parse_args(argv)
    from hackathon_memory.settings import Settings  # noqa: PLC0415  (only for the command)

    settings = Settings()
    conninfo = (settings.database_conninfo() if arguments.laptop
                else settings.public_database_url.get_secret_value())  # fmt: skip
    if not conninfo:
        print("PUBLIC_DATABASE_URL is not set in .env.")
        return 1
    if arguments.what == "delete":
        if not arguments.yes:
            print("Nothing deleted: add --yes to delete every noted action, for good.")
            return 1
        print(f"Deleted {delete(conninfo)} noted actions.")
        return 0
    found = visits(conninfo)
    print(f"{len(found)} visitors, {sum(len(visit.actions) for visit in found)} actions.")
    for name, top in summary(found).items():
        print(f"{name}: " + ", ".join(f"{value} ({count})" for value, count in top[:8]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
