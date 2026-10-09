"""The polite request layer: one test for each promise made to the sites (design 5.7)."""

from __future__ import annotations

import threading
import time

import pytest

from fakes import FakeSite, FakeTime, Reply, session_for
from hackathon_memory.collect.polite import (
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    PoliteClient,
    StopCollecting,
    _NoCookies,
)
from hackathon_memory.settings import Settings

NAME = "TestTool-research"
CONTACT = "owner@example.test"
A = "https://ethglobal.com/showcase/a-one"
B = "https://ethglobal.com/showcase/b-two"
C = "https://ethglobal.com/showcase/c-three"
OK = Reply(200, b"<html>ok</html>", {"Content-Type": "text/html"})


def make(pages, *, enabled=lambda: True, allow=lambda url: True, **options):
    site = FakeSite(pages)
    fake_time = FakeTime()
    client = PoliteClient(
        site="ethglobal.com",
        identity=CollectorIdentity(name=NAME, contact=CONTACT),
        allow=allow,
        is_enabled=enabled,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        **options,
    )
    return client, site, fake_time


# ---------------------------------------- "the tool's name and my address in each request"


def test_every_request_carries_the_tool_name_and_the_contact_address() -> None:
    client, site, _ = make({A: OK, B: OK})
    client.get(A)
    client.get(B)
    assert len(site.seen) == 2
    for request in site.seen:
        assert NAME in request.headers["User-Agent"]
        assert CONTACT in request.headers["User-Agent"]
        assert request.headers["From"] == CONTACT


def test_the_collector_does_not_pretend_to_be_a_browser() -> None:
    client, site, _ = make({A: OK})
    client.get(A)
    agent = site.seen[0].headers["User-Agent"]
    assert "Mozilla" not in agent
    assert "Chrome" not in agent


@pytest.mark.parametrize(
    ("name", "contact"),
    [("", "owner@example.test"), ("TestTool-research", ""), ("   ", "   ")],
)
def test_it_refuses_to_start_when_the_name_or_the_address_is_empty(name: str, contact: str) -> None:
    settings = Settings(_env_file=None, collector_name=name, collector_contact_email=contact)
    with pytest.raises(CollectorRefused):
        CollectorIdentity.from_settings(settings)


def test_a_wrong_address_is_refused_without_repeating_it() -> None:
    with pytest.raises(CollectorRefused) as refusal:
        CollectorIdentity(name=NAME, contact="not-an-email")
    assert "not-an-email" not in str(refusal.value)


def test_the_address_is_not_printed_by_repr() -> None:
    identity = CollectorIdentity(name=NAME, contact=CONTACT)
    assert CONTACT not in repr(identity)


# --------------------------------------------------- "one at a time, a pause of two seconds"


def test_the_pause_between_two_requests_is_two_seconds() -> None:
    client, _, fake_time = make({A: OK, B: OK, C: OK})
    for url in (A, B, C):
        client.get(url)
    assert fake_time.sleeps == [2.0, 2.0]  # none before the first request


def test_the_pause_can_be_made_longer_but_never_shorter() -> None:
    client, _, fake_time = make({A: OK, B: OK})
    client.raise_pause_to(1.0)  # shorter than ours: ignored
    client.raise_pause_to(5.0)  # a site asked for more: honoured
    client.get(A)
    client.get(B)
    assert fake_time.sleeps == [5.0]


def test_two_threads_never_make_a_request_at_the_same_time() -> None:
    site = FakeSite({A: OK, B: OK, C: OK}, during_request=lambda: time.sleep(0.05))
    fake_time = FakeTime()
    client = PoliteClient(
        site="ethglobal.com",
        identity=CollectorIdentity(name=NAME, contact=CONTACT),
        allow=lambda url: True,
        is_enabled=lambda: True,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
    )
    threads = [threading.Thread(target=client.get, args=(url,)) for url in (A, B, C)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(site.seen) == 3
    assert site.most_at_once == 1


# --------------------------------------------------- "a fixed limit stops it after 300 requests"


def test_the_limit_of_requests_stops_the_run_exactly() -> None:
    client, site, _ = make({A: OK, B: OK, C: OK}, max_requests=2)
    client.get(A)
    client.get(B)
    with pytest.raises(StopCollecting, match="limit of 2 requests"):
        client.get(C)
    assert len(site.seen) == 2


def test_the_default_limit_is_300() -> None:
    client, _, _ = make({})
    assert client.max_requests == 300


# --------------------------------------------------- "only the pages we named"


def test_an_address_outside_the_list_is_never_requested() -> None:
    client, site, _ = make({}, allow=lambda url: url == A)
    with pytest.raises(StopCollecting, match="not on the list"):
        client.get("https://example.com/anything")
    assert site.seen == []


def test_a_redirect_inside_the_list_is_followed_and_counts_as_a_request() -> None:
    pages = {A: Reply(301, b"", {"Location": "/showcase/b-two"}), B: OK}
    client, site, fake_time = make(pages, allow=lambda url: url in (A, B))
    result = client.get(A)
    assert result.final_url == B
    assert result.url == A
    assert site.urls == [A, B]
    assert client.requests_made == 2
    assert fake_time.sleeps == [2.0]


def test_a_redirect_outside_the_list_stops_the_run_and_is_not_followed() -> None:
    pages = {A: Reply(302, b"", {"Location": "https://ethglobal.com/login"})}
    client, site, _ = make(pages, allow=lambda url: url == A)
    with pytest.raises(StopCollecting, match="not on the list"):
        client.get(A)
    assert site.urls == [A]  # the login page was never requested


def test_a_loop_of_redirects_stops_the_run() -> None:
    pages = {A: Reply(302, b"", {"Location": A})}
    client, _, _ = make(pages)
    with pytest.raises(StopCollecting, match="too many redirects"):
        client.get(A)


# --------------------------------------------------- "I stop at once if you ask"


def test_a_switch_that_is_off_means_no_request_at_all() -> None:
    client, site, _ = make({A: OK}, enabled=lambda: False)
    with pytest.raises(StopCollecting, match="switch"):
        client.get(A)
    assert site.seen == []


def test_turning_the_switch_off_during_a_run_stops_it_before_the_next_request() -> None:
    state = {"on": True}
    client, site, _ = make({A: OK, B: OK}, enabled=lambda: state["on"])
    client.get(A)
    state["on"] = False
    with pytest.raises(StopCollecting, match="switch"):
        client.get(B)
    assert site.urls == [A]


# --------------------------------------------------- "never work around a block"


@pytest.mark.parametrize("status", [401, 403, 429, 451])
def test_a_refusal_stops_the_run_at_once_with_no_second_try(status: int) -> None:
    client, site, _ = make({A: Reply(status, b"no")})
    with pytest.raises(StopCollecting, match="says no"):
        client.get(A)
    assert len(site.seen) == 1


def test_a_bot_challenge_header_stops_the_run() -> None:
    client, _, _ = make({A: Reply(200, b"x", {"cf-mitigated": "challenge"})})
    with pytest.raises(StopCollecting, match="says no"):
        client.get(A)


def test_five_errors_in_a_row_stop_the_run() -> None:
    urls = [f"https://ethglobal.com/showcase/p{i}" for i in range(5)]
    client, _, _ = make({u: Reply(500) for u in urls})
    for url in urls[:4]:
        with pytest.raises(FetchFailed):
            client.get(url)
    with pytest.raises(StopCollecting, match="5 errors in a row"):
        client.get(urls[4])


def test_a_good_answer_resets_the_count_of_errors() -> None:
    bad = [f"https://ethglobal.com/showcase/bad{i}" for i in range(4)]
    pages = {u: Reply(500) for u in bad} | {A: OK}
    client, _, _ = make(pages, max_errors_in_a_row=3)
    for url in bad[:2]:
        with pytest.raises(FetchFailed):
            client.get(url)
    client.get(A)  # success: the count starts again
    for url in bad[2:]:
        with pytest.raises(FetchFailed):
            client.get(url)  # two more errors are fine, three in a row would stop


def test_a_missing_page_is_not_an_error() -> None:
    client, _, _ = make({}, max_errors_in_a_row=2)
    for i in range(5):
        assert client.get(f"https://ethglobal.com/showcase/gone{i}").status == 404


def test_an_answer_that_is_too_large_is_an_error() -> None:
    client, _, _ = make({A: Reply(200, b"x" * 100)}, max_bytes=50)
    with pytest.raises(FetchFailed, match="larger than"):
        client.get(A)


# --------------------------------------------------- "never sign in"


def test_the_client_keeps_no_cookie_and_uses_no_login_from_the_computer() -> None:
    client, _, _ = make({})
    assert isinstance(client.session.cookies._policy, _NoCookies)
    assert client.session.trust_env is False  # no ~/.netrc login, no proxy from the environment
    assert client.session.auth is None
    policy = _NoCookies()
    assert policy.set_ok(None, None) is False
    assert policy.return_ok(None, None) is False
