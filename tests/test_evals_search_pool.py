"""Where the known projects stand in the list by meaning (evals/search_pool.py). Everything is
invented."""

from __future__ import annotations

from evals.search_pool import within
from hackathon_memory.search.rerank import POOL


def test_the_known_projects_are_counted_within_each_top() -> None:
    ranks = [("same idea", 1), ("same idea", 12), ("idea", POOL), ("idea", POOL + 1),
             ("same idea", None)]  # fmt: skip
    found = within(ranks)
    assert found["first_10"] == {"found": 1, "known": 5, "share": 0.2}
    assert found[f"first_{POOL}"]["found"] == 3  # the pool holds its last place
    assert found["first_50"]["found"] == 4
    assert found["outside_the_pool_by_kind"] == {"idea": 1, "same idea": 1}
    assert within([])["first_10"] == {"found": 0, "known": 0, "share": 0.0}
