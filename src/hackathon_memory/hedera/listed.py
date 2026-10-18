"""The hackathons that a registration may name although the collection holds none of their
projects (design 9.3).

A registration names a hackathon of a list, so that all the teams of one hackathon name it the
same way: a name typed by each team would be spelled in many ways, and days typed by each team
would differ too. The events of the collection are in the list. A hackathon that is not in the
collection is added here by hand, once, from its organiser's own announcement; its days stay
empty until the organiser gives them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Listed:
    key: str  # how the register names it
    name: str
    first: date | None = None  # the first day the teams may build
    last: date | None = None  # the last day they may submit


# The FSS Campus Edition of the Hedera Cross Campus Challenge 2026; the short name fits the
# list of the check.
LISTED = (Listed("listed/fss-campus-edition-2026", "FSS Campus Edition 2026"),)


def listed(key: str) -> Listed | None:
    """The hackathon of the list with this key, or None."""
    return next((one for one in LISTED if one.key == key), None)
