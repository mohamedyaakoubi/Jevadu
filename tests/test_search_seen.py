"""Projects linked across events by their code or a Hedera ID (search/seen.py, design 8.4)."""

from __future__ import annotations

from hackathon_memory.search.seen import Member, groups

A, B = ("ethglobal.com", "a"), ("ethglobal.com", "b")


def test_the_same_repository_at_two_events_links_the_projects() -> None:
    members = [Member(1, A, 10), Member(2, B, 10), Member(3, B, 11)]
    assert groups(members, []) == [[1, 2]]


def test_projects_of_one_event_are_not_a_group() -> None:
    assert groups([Member(1, A, 10), Member(2, A, 10)], []) == []


def test_the_same_hedera_id_links_the_projects() -> None:
    members = [Member(1, A, 10), Member(2, B, 11)]
    assert groups(members, [(1, "testnet:0.0.5"), (2, "testnet:0.0.5")]) == [[1, 2]]
    # The same number on the other network is another thing (design 7.1).
    assert groups(members, [(1, "testnet:0.0.5"), (2, "mainnet:0.0.5")]) == []


def test_an_id_that_many_projects_name_links_nothing() -> None:
    members = [Member(n, ("ethglobal.com", f"e{n}"), 10 + n) for n in range(1, 7)]  # six events
    found = [(1, "testnet:0.0.9"), (4, "testnet:0.0.9")]  # the ledger found it for two
    named = [(n, "testnet:0.0.9") for n in range(1, 7)]  # six projects with other code name it
    assert groups(members, found, named) == []
    assert groups(members, found, named[:3]) == [[1, 4]]  # three: not yet a shared service


def test_an_id_that_two_teams_name_at_one_event_links_nothing() -> None:
    """Teams of one hackathon that name one account most likely use a service; they are not one
    team (three teams of one event named one account of the main network, 18 October 2026)."""
    members = [Member(1, A, 11), Member(2, A, 12), Member(3, B, 13)]
    found = [(1, "mainnet:0.0.7"), (2, "mainnet:0.0.7"), (3, "mainnet:0.0.7")]
    assert groups(members, found) == []
    # One code at one event counts once: the same team, back at another event, still links.
    members = [Member(1, A, 11), Member(2, A, 11), Member(3, B, 13)]
    assert groups(members, found) == [[1, 2, 3]]


def test_a_name_alone_links_nothing() -> None:
    assert groups([Member(1, A, None), Member(2, B, None)], []) == []
