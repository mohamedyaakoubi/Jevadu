"""The public copy of the website (design 12.5, 29 October 2026).

The same site runs a second time as the public copy at jevadu.mohamedyaakoubi.com: on Vercel, with
its database on Neon (web/vercel_app.py), or started on the laptop with --public behind a
Cloudflare tunnel (web/tunnel.py). The limits are those of a public site with no accounts:

* Search engines are told not to index it (robots.txt, the header X-Robots-Tag and the page's own
  meta), so it is reached by its link only. This holds for the laptop's site too.
* Two switches, kept in the database and set by a command (web/switch.py): "ai" for every call to
  a model, which costs money, and "register" for a record written on Hedera. Both are off until
  turned on by that command: on the public copy nothing costs money, and the register's first
  record is still to come from the demo.
* A budget of its own (finops, the environment "public"): what strangers spend never touches the
  money of the tool, and stops at its cap.
* An allowance for each visitor, one time only and never renewed. Asking Gemini counts once for
  each of its buttons pressed for an idea (press_key), however many calls the answer takes; an
  answer kept for a day costs nothing again. The count is made by the meter, just before a call
  to a model (Limits.admit), so only what is really asked of a model is counted.
* A visitor is a salted hash of the address that the host gives (Vercel's or Cloudflare's header;
  an IPv6 address by its /64 network, since one home holds a whole /64) and of the name the
  browser gives itself
  (User-Agent): people who share an address, on a campus or behind a mobile network, each have
  their own allowance. Never a cookie, which a visitor could delete, and never the address
  itself. One address holds the allowances of at most SHARED visitors, so another browser name is
  no way around the count. A visitor who changes both network and browser gets a new allowance:
  no site without accounts can stop that, and the budget of its own keeps the money safe.
* A person, as Cloudflare's Turnstile says (web/turnstile.py, 30 October 2026), when the copy has
  its keys: before asking Gemini, checking, reading again or registering, a visitor must have
  been found to be a person in the last PASS_HOURS. A program that changes its address or its
  browser's name for a new allowance must solve the challenge again each time. The search by
  meaning asks for no pass, so the tool's main use never waits for one.
"""

from __future__ import annotations

import contextvars
import hashlib
import ipaddress
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import psycopg

from hackathon_memory.db.embeddings import idea_fingerprint
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.finops.meter import Tags

AI, REGISTER = "ai", "register"  # the switches, off until turned on
EMBED, CHECK, REFRESH = "embed", "check", "refresh"
SWITCHES = (AI, REGISTER)
# What one visitor may do, one time and for good, besides asking Gemini (PUBLIC_AI_PER_VISITOR):
# ideas read by meaning (an embedding costs about two thousandths of a cent: this count only stops
# a program that would ask for thousands), checks, readings again and registrations.
ALLOWANCE = {EMBED: 200, CHECK: 10, REFRESH: 10, REGISTER: 3}
# One address holds the allowances of at most this many visitors: a campus behind one address, or
# one person who changes the name of the browser.
SHARED = 25
# What a visitor may do only once found to be a person, when the copy asks (Limits.needs_pass),
# and for how long a pass holds.
FOR_PEOPLE = (AI, CHECK, REFRESH, REGISTER)
PASS_HOURS = 24
VISITOR, ADDRESS = "visitor", "address"  # whom a count is kept for
# The calls to a model that the public copy makes, and what each one counts against.
KINDS = {"embed_query": EMBED, "rerank": AI, "compare": AI}
ROBOTS = "User-agent: *\nDisallow: /\n"
HEADERS = {
    "X-Robots-Tag": "noindex, nofollow",  # every page of the site, on the laptop too
}
PUBLIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    # HTTPS only, for this name alone (no includeSubDomains): the address is served by Cloudflare
    "Strict-Transport-Security": "max-age=31536000",
}


class Refused(BudgetExceeded):
    """A call that the public copy refuses for its visitor: past the allowance, or with no
    visitor. Every place that falls back when a budget is spent falls back the same way."""


@dataclass(frozen=True)
class Visitor:
    """A visitor of the public copy: two salted hashes, never an address."""

    key: str  # of the address and the browser's name
    address: str  # of the address alone, for the share of an address


def plain_http(headers: Mapping[str, str]) -> bool:
    """A visitor who came in plain HTTP, as Cloudflare says in X-Forwarded-Proto: sent to HTTPS
    (seen on 29 October 2026: the zone does not redirect by itself)."""
    return headers.get("x-forwarded-proto", "").lower() == "http"


# The visitor of the request being answered, for the calls to a model, which know no request.
visitor: contextvars.ContextVar[Visitor | None] = contextvars.ContextVar("visitor", default=None)


def visitor_of(headers: Mapping[str, str], peer: str | None, salt: str,
               header: str = "cf-connecting-ip") -> Visitor:  # fmt: skip
    """The visitor of a request: the address in `header`, which the host writes itself so that a
    visitor cannot give another (Cloudflare's CF-Connecting-IP; Vercel's x-vercel-forwarded-for),
    else the peer's, and the name the browser gives itself, each kept as a salted hash only."""
    raw = (headers.get(header) or peer or "").strip()
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        kept = "unknown"
    else:
        if address.version == 6:
            kept = str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
        else:
            kept = str(address)

    def hashed(*parts: str) -> str:
        return hashlib.sha256("|".join((salt, *parts)).encode()).hexdigest()

    return Visitor(key=hashed(kept, headers.get("user-agent", "")), address=hashed(kept))


def press_key(idea: str, button: str) -> str:
    """One press of a button of Gemini for an idea: "order" (the order and the comparison of the
    first ten), "one:<project>" (the comparison in a project's window) or "check" (a README and
    its closest projects). The idea is kept by its fingerprint only."""
    return f"{idea_fingerprint(idea)}:{button}"


class Limits:
    """The switches, the allowances and the passes of the public copy, in PostgreSQL. A short
    connection each; when the database cannot answer, nothing is allowed. With `needs_pass`,
    what FOR_PEOPLE names waits for the visitor's pass."""

    def __init__(self, conninfo: Callable[[], str], ai_per_visitor: int,
                 needs_pass: bool = False) -> None:  # fmt: skip
        self._conninfo = conninfo
        self.allowance = {AI: ai_per_visitor, **ALLOWANCE}
        self.needs_pass = needs_pass

    def on(self, name: str) -> bool:
        """Whether a part is turned on; off when the database cannot say."""
        try:
            with psycopg.connect(self._conninfo(), connect_timeout=5) as conn:
                row = conn.execute("SELECT turned_on FROM site_switches WHERE name = %s",
                                   (name,)).fetchone()  # fmt: skip
        except psycopg.Error:
            return False
        return bool(row and row[0])

    def take(self, kind: str, who: Visitor | None) -> bool:
        """Count one use of `kind` by `who`, one time and for good, and say whether it was still
        allowed. A use past the visitor's allowance, or past the share of the address, is not
        counted."""
        if who is None or self.allowance[kind] <= 0:
            return False
        try:
            with psycopg.connect(self._conninfo(), connect_timeout=5) as conn:
                return self._take(conn, kind, who)
        except psycopg.Error:
            return False

    def _take(self, conn: psycopg.Connection, kind: str, who: Visitor) -> bool:
        if kind in FOR_PEOPLE and not self._passed(conn, who):
            return False  # each place asks for the pass first; this holds when one forgets
        most = self.allowance[kind]
        for scope, client, limit in ((VISITOR, who.key, most),
                                     (ADDRESS, who.address, most * SHARED)):  # fmt: skip
            counted = conn.execute(
                "INSERT INTO visitor_uses AS v (scope, client, kind, count) "
                "VALUES (%s, %s, %s, 1) ON CONFLICT (scope, client, kind) "
                "DO UPDATE SET count = v.count + 1, last_at = now() "
                "WHERE v.count < %s RETURNING count",
                (scope, client, kind, limit),
            ).fetchone()
            if counted is None:
                conn.rollback()  # neither count moves, nor a press counted with them
                return False
        return True

    def passed(self, who: Visitor | None) -> bool:
        """Whether the visitor may do what FOR_PEOPLE names: always when the copy asks for no
        pass; else when Turnstile found them to be a person in the last PASS_HOURS. Not when
        the database cannot say."""
        if not self.needs_pass:
            return True
        if who is None:
            return False
        try:
            with psycopg.connect(self._conninfo(), connect_timeout=5) as conn:
                return self._passed(conn, who)
        except psycopg.Error:
            return False

    def _passed(self, conn: psycopg.Connection, who: Visitor) -> bool:
        if not self.needs_pass:
            return True
        row = conn.execute(
            "SELECT 1 FROM visitor_passes WHERE client = %s "
            "AND passed_at > now() - make_interval(hours => %s)",
            (who.key, PASS_HOURS),
        ).fetchone()
        return row is not None

    def keep_pass(self, who: Visitor) -> None:
        """Keep that Turnstile found the visitor to be a person, from now."""
        with psycopg.connect(self._conninfo(), connect_timeout=5) as conn:
            conn.execute(
                "INSERT INTO visitor_passes (client) VALUES (%s) "
                "ON CONFLICT (client) DO UPDATE SET passed_at = now()",
                (who.key,),
            )

    def press(self, who: Visitor | None, key: str) -> bool:
        """Count a press of a button of Gemini (press_key) once, and say whether it is allowed. A
        press counted before always is: its second call, a retry and its stand-in cost the
        visitor nothing more."""
        if who is None or self.allowance[AI] <= 0:
            return False
        try:
            with psycopg.connect(self._conninfo(), connect_timeout=5) as conn:
                fresh = conn.execute(
                    "INSERT INTO visitor_presses (client, press) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING RETURNING 1",
                    (who.key, key),
                ).fetchone()
                return fresh is None or self._take(conn, AI, who)
        except psycopg.Error:
            return False

    def pressed(self, who: Visitor | None, key: str) -> bool:
        """Whether this press was counted before, so that its answers cost nothing more."""
        if who is None:
            return False
        try:
            with psycopg.connect(self._conninfo(), connect_timeout=5) as conn:
                row = conn.execute("SELECT 1 FROM visitor_presses WHERE client = %s AND press = %s",
                                   (who.key, key)).fetchone()  # fmt: skip
        except psycopg.Error:
            return False
        return row is not None

    def left(self, kind: str, who: Visitor | None) -> int:
        """What the visitor has left of `kind`: the smaller of their own allowance and of what
        their address still holds. 0 when the database cannot say."""
        if who is None:
            return 0
        try:
            with psycopg.connect(self._conninfo(), connect_timeout=5) as conn:
                used = dict(conn.execute(
                    "SELECT scope, count FROM visitor_uses WHERE kind = %s AND "
                    "((scope = %s AND client = %s) OR (scope = %s AND client = %s))",
                    (kind, VISITOR, who.key, ADDRESS, who.address),
                ).fetchall())  # fmt: skip
        except psycopg.Error:
            return 0
        most = self.allowance[kind]
        return max(0, min(most - used.get(VISITOR, 0), most * SHARED - used.get(ADDRESS, 0)))

    def admit(self, tags: Tags) -> None:
        """The gate of the meter (finops/meter.py), just before a call to a model: the visitor of
        the request must still have it in their allowance. Raises Refused."""
        kind = KINDS.get(tags.purpose)
        if kind is None:
            raise Refused(f"The public copy makes no call for '{tags.purpose}'.")
        who = visitor.get()
        if kind == AI and tags.item_ref:
            allowed = self.press(who, tags.item_ref)
        else:
            allowed = self.take(kind, who)
        if not allowed:
            raise Refused(f"The visitor's allowance of '{kind}' on the public copy is used.")


def turn(conninfo: str, name: str, turned_on: bool) -> None:
    if name not in SWITCHES:
        raise ValueError(f"no switch named {name}")
    with psycopg.connect(conninfo) as conn:
        conn.execute(
            "INSERT INTO site_switches (name, turned_on) VALUES (%s, %s) "
            "ON CONFLICT (name) DO UPDATE SET turned_on = excluded.turned_on, changed_at = now()",
            (name, turned_on),
        )


def totals(conninfo: str) -> tuple[dict[str, bool], dict[str, tuple[int, int]]]:
    """The switches, and for each kind the visitors who used it and their uses, since the start."""
    with psycopg.connect(conninfo) as conn:
        switches = dict(conn.execute("SELECT name, turned_on FROM site_switches").fetchall())
        counts = {kind: (visitors, uses) for kind, visitors, uses in conn.execute(
            "SELECT kind, count(*), sum(count) FROM visitor_uses WHERE scope = %s GROUP BY kind",
            (VISITOR,)).fetchall()}  # fmt: skip
    return {name: bool(switches.get(name)) for name in SWITCHES}, counts
