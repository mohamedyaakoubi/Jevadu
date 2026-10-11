"""The polite request layer: one test for each promise made to the sites (design 5.7)."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fakes import FakeSite, FakeTime, Reply, session_for
from hackathon_memory.collect.polite import (
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    PoliteClient,
    RequestCount,
    StopCollecting,
    TooManyRequests,
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


# --------------------------------------------------- "a few hundred pages at most, one time"


def counted(tmp_path: Path, limit: int = 300) -> RequestCount:
    day = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
    return RequestCount(
        tmp_path / "requests" / "ethglobal.com.json", "ethglobal.com", limit, lambda: day
    )


def test_the_requests_of_all_runs_are_counted_in_one_file(tmp_path: Path) -> None:
    first, _, _ = make({A: OK, B: OK}, count=counted(tmp_path))
    first.get(A)
    first.get(B)

    later, _, _ = make({C: OK}, count=counted(tmp_path))  # another run, another day
    assert later.count.sent() == 2
    later.get(C)
    assert later.count.sent() == 3
    assert later.requests_made == 1
    record = json.loads((tmp_path / "requests" / "ethglobal.com.json").read_text(encoding="utf-8"))
    assert record == {"site": "ethglobal.com", "sent": 3, "by_day": {"2026-10-10": 3}}


def test_the_limit_over_all_runs_stops_a_later_run(tmp_path: Path) -> None:
    first, _, _ = make({A: OK, B: OK}, count=counted(tmp_path, limit=3))
    first.get(A)
    first.get(B)

    later, site, _ = make({A: OK, C: OK}, count=counted(tmp_path, limit=3))
    later.get(C)  # the third request of all runs: the last one that is allowed
    with pytest.raises(StopCollecting, match="over all runs"):
        later.get(A)
    assert site.urls == [C]
    assert later.count.left() == 0


def test_a_redirect_and_a_refused_request_are_counted_too(tmp_path: Path) -> None:
    pages = {A: Reply(301, b"", {"Location": "/showcase/b-two"}), B: OK, C: Reply(403, b"no")}
    client, _, _ = make(pages, count=counted(tmp_path))
    client.get(A)  # two requests: the redirect and the page
    with pytest.raises(StopCollecting, match="says no"):
        client.get(C)
    assert client.count.sent() == 3


def test_a_request_that_is_not_allowed_is_not_counted(tmp_path: Path) -> None:
    client, _, _ = make({}, allow=lambda url: False, count=counted(tmp_path))
    with pytest.raises(StopCollecting, match="not on the list"):
        client.get(A)
    assert client.count.sent() == 0  # nothing was sent, so nothing is counted


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[1, 2]",
        '{"site": "example.com", "sent": 1, "by_day": {}}',  # the count of another site
        '{"site": "ethglobal.com", "sent": -1, "by_day": {}}',
        '{"site": "ethglobal.com", "sent": "many", "by_day": {}}',
        '{"site": "ethglobal.com", "sent": 1}',
        '{"site": "ethglobal.com", "sent": 1, "by_day": {}, "not_before": "soon"}',
        '{"site": "ethglobal.com", "sent": 1, "by_day": {}, "refused": {"status": 403}}',
        '{"site": "ethglobal.com", "sent": 1, "by_day": {}, "min_pause_seconds": -1}',
    ],
)
def test_a_count_that_cannot_be_read_is_never_taken_for_zero(tmp_path: Path, content: str) -> None:
    count = counted(tmp_path)
    count.path.parent.mkdir(parents=True)
    count.path.write_text(content, encoding="utf-8")
    client, site, _ = make({A: OK}, count=count)
    with pytest.raises(StopCollecting, match="cannot be read"):
        client.get(A)
    assert site.seen == []
    assert count.path.read_text(encoding="utf-8") == content  # and it is not written over


def test_notes_in_the_count_file_are_kept(tmp_path: Path) -> None:
    count = counted(tmp_path)
    count.path.parent.mkdir(parents=True)
    start = {
        "site": "ethglobal.com",
        "sent": 24,
        "by_day": {"2026-10-10": 24},
        "notes": ["by hand"],
    }
    count.path.write_text(json.dumps(start), encoding="utf-8")
    client, _, _ = make({A: OK}, count=count)
    client.get(A)
    record = json.loads(count.path.read_text(encoding="utf-8"))
    assert record["sent"] == 25
    assert record["notes"] == ["by hand"]


# --------------------------------------------------- "too many requests" is a speed limit

START = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)
TOO_MANY = Reply(429, b"slow down")


def slowed(tmp_path: Path, pages, **options):
    """A client whose count keeps time with the fake clock, so that a cooldown can pass."""
    site, fake_time = FakeSite(pages), FakeTime()
    count = RequestCount(
        tmp_path / "requests" / "ethglobal.com.json",
        "ethglobal.com",
        now=lambda: START + timedelta(seconds=fake_time.now - 1000.0),
    )
    client = PoliteClient(
        site="ethglobal.com",
        identity=CollectorIdentity(name=NAME, contact=CONTACT),
        allow=lambda url: True,
        is_enabled=lambda: True,
        session=session_for(site),
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        count=count,
        **options,
    )
    return client, site, fake_time


def test_too_many_requests_stops_at_once_and_is_not_a_no(tmp_path: Path) -> None:
    client, site, _ = slowed(tmp_path, {A: Reply(429, b"slow down", {"Retry-After": "30"}), B: OK})
    with pytest.raises(TooManyRequests, match="too many requests") as stop:
        client.get(A)
    assert "The site asks to wait: 30." in str(stop.value)
    assert len(site.seen) == 1  # no second try
    assert client.count.refusal() is None  # a speed limit is not a no
    assert client.count.wait_left() == 3600  # one hour, although the site asked for less
    assert client.count.min_pause() == 10.0  # five times the two seconds that were too fast
    record = json.loads(client.count.path.read_text(encoding="utf-8"))
    assert record["too_many"] == [
        {"at": "2026-10-11T00:00:00Z", "asked_to_wait": "30", "pause_seconds": 2.0}
    ]
    assert record["not_before"] == "2026-10-11T01:00:00Z"


def test_nothing_is_sent_before_the_cooldown_is_over(tmp_path: Path) -> None:
    client, site, fake_time = slowed(tmp_path, {A: TOO_MANY, B: OK})
    with pytest.raises(TooManyRequests):
        client.get(A)
    with pytest.raises(StopCollecting, match="cooldown runs until 2026-10-11T01:00:00Z"):
        client.get(B)
    fake_time.sleep(3599)
    with pytest.raises(StopCollecting, match="cooldown"):
        client.get(B)
    assert site.urls == [A]  # nothing was sent during the hour
    fake_time.sleep(1)
    assert client.get(B).status == 200


def test_after_a_cooldown_the_pause_is_five_times_longer_for_every_later_client(
    tmp_path: Path,
) -> None:
    client, _, fake_time = slowed(tmp_path, {A: TOO_MANY})
    with pytest.raises(TooManyRequests):
        client.get(A)
    fake_time.sleep(3600)

    later, _, later_time = slowed(tmp_path, {B: OK, C: OK})  # another command, another day
    later_time.now = fake_time.now
    later.get(B)
    later.get(C)
    assert later.pause_in_use() == 10.0
    assert later_time.sleeps == [10.0]


@pytest.mark.parametrize(
    ("asked", "seconds"),
    [
        ("7200", 7200),  # the site asks for two hours
        ("Sun, 11 Oct 2026 03:00:00 GMT", 10800),  # the same thing written as a date
        ("59", 3600),  # less than our hour: the hour stays
        ("soon", 3600),  # something we cannot read: the hour stays
    ],
)
def test_a_site_that_names_a_longer_wait_gets_it(tmp_path: Path, asked: str, seconds: int) -> None:
    client, _, _ = slowed(tmp_path, {A: Reply(429, b"", {"Retry-After": asked})})
    with pytest.raises(TooManyRequests):
        client.get(A)
    assert client.count.wait_left() == seconds


def test_a_client_that_was_told_to_wait_sleeps_through_the_cooldown_and_goes_on(
    tmp_path: Path,
) -> None:
    client, site, fake_time = slowed(tmp_path, {A: TOO_MANY, B: OK}, wait_for_cooldown=True)
    with pytest.raises(TooManyRequests):
        client.get(A)  # the refused request itself is never repeated by the client
    assert client.get(B).status == 200
    assert fake_time.sleeps == [3600.0]
    assert client.cooldowns_waited == 1
    assert site.urls == [A, B]


def test_the_switch_still_stops_a_client_that_waited(tmp_path: Path) -> None:
    state = {"on": True}
    client, site, fake_time = slowed(tmp_path, {A: TOO_MANY, B: OK}, wait_for_cooldown=True)
    client.is_enabled = lambda: state["on"]
    with pytest.raises(TooManyRequests):
        client.get(A)
    client.sleep = lambda seconds: (fake_time.sleep(seconds), state.update(on=False))
    with pytest.raises(StopCollecting, match="switch"):
        client.get(B)  # somebody turned the switch off during the hour
    assert site.urls == [A]


def test_a_third_time_within_a_day_is_taken_for_a_no(tmp_path: Path) -> None:
    pages = {A: TOO_MANY, B: TOO_MANY, C: TOO_MANY}
    client, site, fake_time = slowed(tmp_path, pages, wait_for_cooldown=True)
    with pytest.raises(TooManyRequests):
        client.get(A)
    with pytest.raises(TooManyRequests):
        client.get(B)  # after one hour, at 10 seconds: too many again
    assert client.count.min_pause() == 50.0
    assert client.count.refusal() is None
    with pytest.raises(TooManyRequests, match="a person decides now"):
        client.get(C)
    assert client.count.refusal()["status"] == 429
    waited = len(fake_time.sleeps)
    with pytest.raises(StopCollecting, match="refused a request"):
        client.get("https://ethglobal.com/showcase/d-four")
    assert len(site.seen) == 3  # nothing more is sent, and nothing is waited for
    assert len(fake_time.sleeps) == waited


def test_two_times_on_two_days_are_two_speed_limits_and_not_a_no(tmp_path: Path) -> None:
    client, _, fake_time = slowed(tmp_path, {A: TOO_MANY, B: TOO_MANY, C: TOO_MANY})
    for url in (A, B, C):
        with pytest.raises(TooManyRequests):
            client.get(url)
        fake_time.sleep(25 * 3600)  # more than a day later
    assert client.count.refusal() is None


# --------------------------------------------------- a no of the site needs a person


def test_a_no_of_the_site_is_remembered_until_a_person_decides(tmp_path: Path) -> None:
    client, site, _ = slowed(tmp_path, {A: Reply(403, b"no"), B: OK})
    with pytest.raises(StopCollecting, match="says no"):
        client.get(A)
    assert client.count.refusal()["status"] == 403

    later, later_site, _ = slowed(tmp_path, {B: OK})  # another command
    with pytest.raises(StopCollecting, match="refused a request on 2026-10-11T00:00:00Z"):
        later.get(B)
    assert later_site.seen == []

    assert later.count.clear_refusal("the site wrote that the tool may go on") is True
    assert later.count.clear_refusal("again") is False  # there is nothing left to clear
    assert later.get(B).status == 200
    record = json.loads(later.count.path.read_text(encoding="utf-8"))
    assert "refused" not in record
    assert "the site wrote that the tool may go on" in record["notes"][0]
    assert later.count.wait_left() == 0  # a no brings no cooldown and no slower pace
    assert later.pause_in_use() == 2.0


def test_a_bot_check_is_a_no_too(tmp_path: Path) -> None:
    client, _, _ = slowed(tmp_path, {A: Reply(200, b"x", {"cf-mitigated": "challenge"})})
    with pytest.raises(StopCollecting, match="says no"):
        client.get(A)
    assert client.count.refusal()["status"] == 200


def test_the_headers_about_limits_are_kept_and_nothing_else(tmp_path: Path) -> None:
    headers = {
        "CF-Cache-Status": "HIT",
        "X-RateLimit-Remaining": "12",
        "Age": "40",
        "Set-Cookie": "session=abc",
        "X-Something-Else": "a value",
    }
    client, _, _ = slowed(tmp_path, {A: Reply(200, b"ok", headers), B: Reply(200, b"ok", headers)})
    client.get(A)
    client.get(B)
    assert client.site_headers == {
        "cf-cache-status": "HIT",
        "x-ratelimit-remaining": "12",
        "age": "40",
    }
    assert client.cache_answers == {"cf-cache-status: HIT": 2}


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


@pytest.mark.parametrize("status", [401, 403, 451])
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
