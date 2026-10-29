"""The public copy of the website (design 12.5, 30 October 2026).

The same site runs a second time on the laptop that holds the collection, started with --public,
and a Cloudflare tunnel brings jevadu.mohamedyaakoubi.com to it: nothing of the collection leaves
the laptop. The limits are those of 21 October 2026, for a public site with no accounts:

* Search engines are told not to index it (robots.txt, the header X-Robots-Tag and the page's own
  meta), so it is reached by its link only. This holds for the laptop's site too.
* Two switches, kept in the database and set by a command (web/switch.py): "ai" for every call to
  a model, which costs money, and "register" for a record written on Hedera. Both are off until
  turned on by that command: on the public copy nothing costs money, and the register's first
  record is still to come from the demo.
* A count for each visitor and day of what costs something (PER_DAY). A visitor is a salted hash
  of the address that Cloudflare gives in CF-Connecting-IP (an IPv6 address by its /64 network,
  since one home holds a whole /64), never a cookie a visitor could delete, never the address.
* The meter's caps (finops) stop the spending in every case, as on the laptop.
"""

from __future__ import annotations

import contextvars
import hashlib
import ipaddress
from collections.abc import Callable, Mapping

import psycopg

AI, REGISTER = "ai", "register"  # the switches, off until turned on
CHECK, REFRESH = "check", "refresh"
SWITCHES = (AI, REGISTER)
# How many times one visitor may do each, in one day (UTC). Generous: a whole campus can share one
# address.
PER_DAY = {AI: 30, CHECK: 10, REFRESH: 10, REGISTER: 3}
ROBOTS = "User-agent: *\nDisallow: /\n"
HEADERS = {
    "X-Robots-Tag": "noindex, nofollow",  # every page of the site, on the laptop too
}
PUBLIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}

# The visitor of the request being answered, for the calls to a model, which know no request.
visitor: contextvars.ContextVar[str | None] = contextvars.ContextVar("visitor", default=None)


def visitor_of(headers: Mapping[str, str], peer: str | None, salt: str) -> str:
    """The salted hash of the visitor's address: the one that Cloudflare gives, else the peer's."""
    raw = (headers.get("cf-connecting-ip") or peer or "").strip()
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        kept = "unknown"
    else:
        if address.version == 6:
            kept = str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
        else:
            kept = str(address)
    return hashlib.sha256(f"{salt}|{kept}".encode()).hexdigest()


class Limits:
    """The switches and the counts of the public copy, in PostgreSQL. A short connection each."""

    def __init__(self, conninfo: Callable[[], str]) -> None:
        self._conninfo = conninfo

    def on(self, name: str) -> bool:
        """Whether a part is turned on; off when the database cannot say."""
        try:
            with psycopg.connect(self._conninfo(), connect_timeout=5) as conn:
                row = conn.execute("SELECT turned_on FROM site_switches WHERE name = %s",
                                   (name,)).fetchone()  # fmt: skip
        except psycopg.Error:
            return False
        return bool(row and row[0])

    def take(self, kind: str, client: str | None) -> bool:
        """Count one use of `kind` by `client` today, and say whether it was still allowed. A use
        over the limit is not counted."""
        if client is None:
            return False
        try:
            with psycopg.connect(self._conninfo(), connect_timeout=5) as conn:
                row = conn.execute(
                    "INSERT INTO visitor_counts AS v (day, client, kind, count) "
                    "VALUES ((now() AT TIME ZONE 'UTC')::date, %s, %s, 1) "
                    "ON CONFLICT (day, client, kind) DO UPDATE SET count = v.count + 1 "
                    "WHERE v.count < %s RETURNING count",
                    (client, kind, PER_DAY[kind]),
                ).fetchone()
        except psycopg.Error:
            return False
        return row is not None


def turn(conninfo: str, name: str, turned_on: bool) -> None:
    if name not in SWITCHES:
        raise ValueError(f"no switch named {name}")
    with psycopg.connect(conninfo) as conn:
        conn.execute(
            "INSERT INTO site_switches (name, turned_on) VALUES (%s, %s) "
            "ON CONFLICT (name) DO UPDATE SET turned_on = excluded.turned_on, changed_at = now()",
            (name, turned_on),
        )


def today(conninfo: str) -> tuple[dict[str, bool], dict[str, tuple[int, int]]]:
    """The switches, and for each kind today its visitors and its uses."""
    with psycopg.connect(conninfo) as conn:
        switches = dict(conn.execute("SELECT name, turned_on FROM site_switches").fetchall())
        counts = {kind: (visitors, uses) for kind, visitors, uses in conn.execute(
            "SELECT kind, count(*), sum(count) FROM visitor_counts "
            "WHERE day = (now() AT TIME ZONE 'UTC')::date GROUP BY kind").fetchall()}  # fmt: skip
    return {name: bool(switches.get(name)) for name in SWITCHES}, counts
