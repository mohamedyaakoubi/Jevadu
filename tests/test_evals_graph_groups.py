"""The measure of the graph's groups (evals/graph_groups.py): the silhouette of a cut, on lists
with a known answer. Everything is invented."""

from __future__ import annotations

import pytest

from evals.graph_groups import cuts, silhouette, summary
from hackathon_memory.search import closeness

# Two pairs of projects: 1 and 2 nearly the same, 3 and 4 too, and the two pairs far apart.
PAIRS = {(1, 2): 0.99, (3, 4): 0.99, (1, 3): 0.0, (1, 4): 0.0, (2, 3): 0.0, (2, 4): 0.0}
WITHIN, ACROSS = (2 * 0.01) ** 0.5, 2**0.5  # the distances of Ward's method here


def test_two_clear_groups_score_high_and_a_wrong_cut_scores_below_zero() -> None:
    assert closeness.groups([1, 2, 3, 4], PAIRS, 2) == [[1, 2], [3, 4]]
    assert silhouette([[1, 2], [3, 4]], PAIRS) == pytest.approx((ACROSS - WITHIN) / ACROSS)  # 0.9
    wrong = ((ACROSS + WITHIN) / 2 - ACROSS) / ACROSS  # each is nearer the other group: -0.45
    assert silhouette([[1, 3], [2, 4]], PAIRS) == pytest.approx(wrong)
    assert silhouette([[1, 2, 3, 4]], PAIRS) == 0.0  # one group: nothing to compare


def test_a_project_alone_counts_zero_and_the_summary_finds_the_best_number() -> None:
    # into 3 groups, one pair stays and the other splits: its two projects count 0
    assert cuts([1, 2, 3, 4], PAIRS) == {2: 0.9, 3: 0.45}
    found = summary([{2: 0.9, 3: 0.45}, {2: 0.1, 3: 0.2, 4: 0.3, 5: 0.4}], rules=[2, 4])
    assert found["silhouette"]["2"] == {"mean": 0.5, "median": 0.5}
    assert found["best_of_2_to_4"] == {"2": 1, "4": 1}
    assert found["best_of_2_to_8"] == {"2": 1, "5": 1}  # 5 groups fit best, but cannot be drawn
    assert found["the_rule_is_the_best_of_2_to_4"] == 2
    assert found["best_above_0_25"] == 2
    assert found["highest"] == 0.9  # the best cut of the list that fits best
