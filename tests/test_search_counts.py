"""The counts behind the charts and the overview (design 12.1): the projects of a list, and
those of them with a Hedera prize, with nothing that ranks."""

from __future__ import annotations

from hackathon_memory.search.counts import tally
from hackathon_memory.search.filters import Facts

ROWS = [
    Facts(1, "7", "Event A", "2026", "Payments and remittance", "proof_found", "active",
          prize="hedera_prize", kinds=("account", "topic")),
    Facts(2, "7", "Event A", "2026", "", "no_id_given", "stopped", prize="other_prize"),
    Facts(3, "8", "Event B", "2025", "Health", "proof_found", "stopped",
          prize="hedera_prize", entry_kind="winner_entry", kinds=("account",)),
    Facts(4, "9", "Event C", "", "", "no_id_given", "unknown"),
]  # fmt: skip


def test_the_tally_counts_all_projects_and_those_with_a_hedera_prize() -> None:
    found = tally(ROWS)
    assert (found.projects, found.winners, found.winner_entries, found.with_theme) == (4, 2, 1, 2)
    assert found.prize == {"hedera_prize": 2, "other_prize": 1, "no_prize": 1}
    assert found.proof == {"proof_found": 2, "no_id_given": 2}
    assert found.proof_won == {"proof_found": 2}
    assert found.life == {"active": 1, "stopped": 2, "unknown": 1}
    assert found.life_won == {"active": 1, "stopped": 1}
    assert found.services == {"account": 2, "topic": 1} and found.services_won == found.services
    assert found.themes == {"Payments and remittance": 1, "Health": 1}
    assert found.events == {"7": 2, "8": 1, "9": 1}
    assert found.events_won == {"7": 1, "8": 1, "9": 0}


def test_an_empty_list_counts_nothing() -> None:
    found = tally([])
    assert (found.projects, found.winners) == (0, 0) and not found.events
