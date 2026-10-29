"""Turn a part of the public copy on or off (web/public.py, design 12.5).

    python -m hackathon_memory.web.switch                what is on, and today's numbers
    python -m hackathon_memory.web.switch ai on          the search by meaning, and the order and
                                                         the comparisons of the AI (it costs money,
                                                         within the meter's budget)
    python -m hackathon_memory.web.switch register on    registering on Hedera
    python -m hackathon_memory.web.switch ai off

The laptop's own site (without --public) is never limited by these switches.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from hackathon_memory.settings import Settings
from hackathon_memory.web import public

USAGE = "usage: python -m hackathon_memory.web.switch [ai|register on|off]"
WORDS = {public.AI: "the AI (search by meaning, order, comparisons)",
         public.REGISTER: "registering on Hedera"}  # fmt: skip


def main(argv: Sequence[str]) -> int:
    conninfo = Settings().database_conninfo()
    if len(argv) == 2 and argv[0] in public.SWITCHES and argv[1] in ("on", "off"):
        public.turn(conninfo, argv[0], argv[1] == "on")
    elif argv:
        print(USAGE)
        return 2
    switches, counts = public.today(conninfo)
    for name, turned_on in switches.items():
        print(f"{WORDS[name]}: {'on' if turned_on else 'off'}")
    for kind, (visitors, uses) in sorted(counts.items()):
        print(f"today, {kind}: {uses} uses by {visitors} visitors")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
