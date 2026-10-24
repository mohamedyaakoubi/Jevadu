"""Whether a thing of the ledger can have been made inside a window, from its number alone.

Hedera gives the numbers of its things (accounts, tokens, topics, contracts, schedules) in order on
each network, one counter for all kinds. Measured on the ledger facts of the collection on 24
October 2026: of 959 things whose day of making the mirror node gave (739 on the test network,
220 on the main network), none stands out of that order. So a thing made inside a window has a
number above every known number made before the window, and below every known number made after
it. A number outside those two bounds was made outside the window, and the mirror node need not be
asked: the check of the IDs of the code (pipeline/code_ids.py) asks only about the others.

The bounds come from things known to the table, so they are never closer than the truth, and if
the order were ever broken a thing would be skipped, never given: this can only miss a proof.
"""

from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence
from datetime import datetime

from hackathon_memory.check.proof import Window


class Numbers:
    """The known numbers of each network with the moment each thing was made, oldest first."""

    def __init__(self, dated: Mapping[str, Sequence[tuple[datetime, int]]]) -> None:
        self._moments = {network: [made for made, _ in rows] for network, rows in dated.items()}
        self._numbers = {network: [number for _, number in rows] for network, rows in dated.items()}

    def could_be_made_inside(self, entity_id: str, network: str, window: Window) -> bool:
        """False only when the number of the thing shows that it was made outside the window."""
        parts = entity_id.split(".")
        if len(parts) != 3 or not parts[2].isdigit():
            return True  # an address of the EVM kind, or a transaction: asked as before
        number = int(parts[2])
        moments, numbers = self._moments.get(network, []), self._numbers.get(network, [])
        before = bisect.bisect_left(moments, window.start)  # made before the window: [:before]
        after = bisect.bisect_right(moments, window.end)  # made after the window: [after:]
        if before and number <= max(numbers[:before]):
            return False
        return not (after < len(numbers) and number >= min(numbers[after:]))
