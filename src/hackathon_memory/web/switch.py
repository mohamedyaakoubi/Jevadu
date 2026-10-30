"""Turn a part of the public copy on or off, and see what it used (web/public.py, design 12.5).

    python -m hackathon_memory.web.switch                what is on, the public copy's budget and
                                                         what its visitors used
    python -m hackathon_memory.web.switch ai on          the search by meaning, and the order and
                                                         the comparisons of the AI (it costs money,
                                                         from the public copy's own budget)
    python -m hackathon_memory.web.switch register on    registering on Hedera
    python -m hackathon_memory.web.switch ai off

The laptop's own site (without --public) is never limited by these switches. They are written
into the public copy's database: PUBLIC_DATABASE_URL when it is set (the copy on its host), else
this computer's.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from hackathon_memory.finops import budget as budgets
from hackathon_memory.finops.calls import PostgresStore
from hackathon_memory.settings import Settings
from hackathon_memory.web import public

USAGE = "usage: python -m hackathon_memory.web.switch [ai|register on|off]"
WORDS = {public.AI: "the AI (search by meaning, order, comparisons)",
         public.REGISTER: "registering on Hedera"}  # fmt: skip
KINDS = {public.AI: "asks of Gemini", public.EMBED: "searches by meaning",
         public.CHECK: "checks", public.REFRESH: "readings again",
         public.REGISTER: "registrations"}  # fmt: skip


def main(argv: Sequence[str]) -> int:
    settings = Settings()
    hosted = settings.public_database_url.get_secret_value().strip()
    conninfo = hosted or settings.database_conninfo()
    print("the public copy's database: " + ("on its host (PUBLIC_DATABASE_URL)" if hosted
                                             else "this computer's"))  # fmt: skip
    if len(argv) == 2 and argv[0] in public.SWITCHES and argv[1] in ("on", "off"):
        public.turn(conninfo, argv[0], argv[1] == "on")
    elif argv:
        print(USAGE)
        return 2
    switches, counts = public.totals(conninfo)
    for name, turned_on in switches.items():
        print(f"{WORDS[name]}: {'on' if turned_on else 'off'}")
    spent = budgets.status(budgets.from_settings(settings, "public"), PostgresStore(conninfo),
                           datetime.now(UTC))  # fmt: skip
    print(f"the public copy's own budget: ${spent.spent_total_usd:.2f} spent of "
          f"${spent.total_usd:.2f}, today ${spent.spent_today_usd:.2f} of "
          f"${spent.per_day_usd or 0:.2f}")  # fmt: skip
    allowance = {public.AI: settings.public_ai_per_visitor, **public.ALLOWANCE}
    print("each visitor, one time: "
          + ", ".join(f"{allowance[kind]} {words}" for kind, words in KINDS.items()))  # fmt: skip
    for kind, words in KINDS.items():
        visitors, uses = counts.get(kind, (0, 0))
        print(f"used since the start, {words}: {uses} by {visitors} visitors")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
