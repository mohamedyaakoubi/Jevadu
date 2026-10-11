"""The client for GitHub's API: the promises of design 5.7, and the answers of GitHub.

No request leaves the test: an invented site answers. The token is invented too.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from fakes import FakeSite, FakeTime, Reply, session_for
from hackathon_memory.collect.github import (
    API_VERSION,
    HOURLY_RESERVE,
    PAUSE_SECONDS,
    GitHubClient,
    allowed,
    github_client,
    readme_address,
    repository_of,
    request_count,
)
from hackathon_memory.collect.polite import (
    CollectorIdentity,
    CollectorRefused,
    FetchFailed,
    RequestCount,
    StopCollecting,
    TooManyRequests,
)
from hackathon_memory.settings import Settings

NAME = "TestTool-research"
CONTACT = "owner@example.test"
TOKEN = "github_pat_INVENTED_CANARY_0123456789"
README = "https://api.github.com/repos/sample-org/pebble-pay/readme"
MOVED = "https://api.github.com/repositories/123456/readme"
OTHER = "https://api.github.com/repos/sample-org/eel-ledger/readme"
NOW = datetime(2026, 10, 11, 18, 0, tzinfo=UTC)


def answer(status: int = 200, body: dict | None = None, **headers: str) -> Reply:
    base = {"Content-Type": "application/json; charset=utf-8", "x-ratelimit-remaining": "4990"}
    base.update({name.replace("_", "-"): value for name, value in headers.items()})
    return Reply(status, json.dumps(body or {"type": "file"}).encode(), base)


def make(pages: dict, tmp_path: Path, *, enabled=lambda: True, **options):
    site = FakeSite(pages)
    fake_time = FakeTime()
    count = RequestCount(tmp_path / "count.json", "api.github.com", limit=100, now=lambda: NOW)
    client = GitHubClient(
        token=SecretStr(TOKEN),
        site="api.github.com",
        identity=CollectorIdentity(name=NAME, contact=CONTACT),
        allow=allowed,
        is_enabled=enabled,
        session=session_for(site),
        count=count,
        pause_seconds=PAUSE_SECONDS,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        now=lambda: NOW,
        **options,
    )
    return client, site, fake_time, count


# --------------------------------------------------------------------- what every request carries


def test_every_request_names_the_tool_the_contact_the_version_and_the_token(
    tmp_path: Path,
) -> None:
    client, site, _, _ = make({README: answer(), OTHER: answer()}, tmp_path)
    client.get(README)
    client.get(OTHER)
    for request in site.seen:
        assert NAME in request.headers["User-Agent"] and CONTACT in request.headers["User-Agent"]
        assert request.headers["From"] == CONTACT
        assert request.headers["Accept"] == "application/vnd.github+json"
        assert request.headers["X-GitHub-Api-Version"] == API_VERSION
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"


def test_the_token_never_prints(tmp_path: Path) -> None:
    client, _, _, _ = make({README: answer(401, {"message": "Bad credentials"})}, tmp_path)
    assert TOKEN not in repr(client) and TOKEN not in str(vars(client))
    with pytest.raises(StopCollecting) as stop:
        client.get(README)
    assert TOKEN not in str(stop.value)


def test_requests_go_one_second_apart(tmp_path: Path) -> None:
    client, _, fake_time, count = make({README: answer(), OTHER: answer()}, tmp_path)
    client.get(README)
    client.get(OTHER)
    client.get(README)
    assert fake_time.sleeps == [1.0, 1.0]
    assert count.sent() == 3


# --------------------------------------------------------------------- the answers of GitHub


def test_a_404_is_an_answer_and_the_run_goes_on(tmp_path: Path) -> None:
    client, _, _, _ = make({README: answer(404, {"message": "Not Found"})}, tmp_path)
    for _ in range(6):  # never counted as an error
        assert client.get(README).status == 404


def test_a_moved_repository_is_followed_on_the_api(tmp_path: Path) -> None:
    moved = answer(301, {"message": "Moved Permanently"}, Location=MOVED)
    client, site, _, _ = make({README: moved, MOVED: answer()}, tmp_path)
    got = client.get(README)
    assert (got.url, got.final_url, got.status) == (README, MOVED, 200)
    assert [request.url for request in site.seen] == [README, MOVED]


def test_a_redirect_out_of_the_api_is_refused_and_nothing_is_sent_there(tmp_path: Path) -> None:
    away = "https://example.test/collect?token=1"
    client, site, _, _ = make({README: answer(302, Location=away)}, tmp_path)
    with pytest.raises(StopCollecting):
        client.get(README)
    assert [request.url for request in site.seen] == [README]


@pytest.mark.parametrize(
    "reply",
    [
        answer(403, {"message": "API rate limit exceeded"}, x_ratelimit_remaining="0",
               x_ratelimit_reset=str(int(NOW.timestamp()) + 600)),
        answer(429, {"message": "slow down"}, retry_after="120"),
        answer(403, {"message": "You have exceeded a secondary rate limit."}),
    ],
)  # fmt: skip
def test_a_rate_limit_is_a_speed_limit_with_the_rule_of_a_429(tmp_path: Path, reply: Reply) -> None:
    client, _, _, count = make({README: reply}, tmp_path)
    with pytest.raises(TooManyRequests):
        client.get(README)
    assert count.refusal() is None  # not a no
    assert count.wait_left() >= 3600  # at least one hour
    assert count.min_pause() == 5 * PAUSE_SECONDS  # then five times slower


def test_the_time_that_github_names_is_kept_when_it_is_longer_than_an_hour(
    tmp_path: Path,
) -> None:
    reset = int(NOW.timestamp()) + 5400
    reply = answer(403, {"message": "API rate limit exceeded"}, x_ratelimit_remaining="0",
                   x_ratelimit_reset=str(reset))  # fmt: skip
    client, _, _, count = make({README: reply}, tmp_path)
    with pytest.raises(TooManyRequests):
        client.get(README)
    assert count.wait_left() == 5400


@pytest.mark.parametrize("status", [403, 451])
def test_one_blocked_repository_is_an_answer_about_it(tmp_path: Path, status: int) -> None:
    blocked = answer(status, {"message": "Repository access blocked", "block": {"reason": "tos"}})
    client, _, _, count = make({README: blocked, OTHER: answer()}, tmp_path)
    assert client.get(README).status == status
    assert client.get(OTHER).status == 200
    assert count.refusal() is None


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "Bad credentials"),
        (403, "Resource not accessible by personal access token"),
        (451, "Unavailable for legal reasons"),
    ],
)
def test_any_other_no_stops_everything_and_a_person_decides(
    tmp_path: Path, status: int, message: str
) -> None:
    client, site, _, count = make({README: answer(status, {"message": message})}, tmp_path)
    with pytest.raises(StopCollecting):
        client.get(README)
    assert count.refusal()["status"] == status  # type: ignore[index]
    with pytest.raises(StopCollecting):
        client.get(OTHER)
    assert len(site.seen) == 1


def test_errors_of_the_server_stop_the_run_after_five_in_a_row(tmp_path: Path) -> None:
    client, site, _, _ = make({README: answer(502)}, tmp_path)
    for _ in range(4):
        with pytest.raises(FetchFailed):
            client.get(README)
    with pytest.raises(StopCollecting):
        client.get(README)
    assert len(site.seen) == 5


def test_the_run_stops_before_github_has_to_say_no(tmp_path: Path) -> None:
    low = answer(x_ratelimit_remaining=str(HOURLY_RESERVE - 1), x_ratelimit_reset="1791747543")
    client, site, _, _ = make({README: low, OTHER: answer()}, tmp_path)
    client.get(README)
    with pytest.raises(StopCollecting, match="left in its hour"):
        client.get(OTHER)
    assert len(site.seen) == 1


def test_the_switch_off_stops_it_before_a_request(tmp_path: Path) -> None:
    client, site, _, _ = make({README: answer()}, tmp_path, enabled=lambda: False)
    with pytest.raises(StopCollecting, match="switch"):
        client.get(README)
    assert site.seen == []


# --------------------------------------------------------------------- the addresses


@pytest.mark.parametrize(
    ("link", "repository"),
    [
        ("https://github.com/sample-org/pebble-pay", "https://github.com/sample-org/pebble-pay"),
        ("https://www.GitHub.com/Sample-Org/Pebble-Pay.git/", "https://github.com/sample-org/pebble-pay"),
        ("http://github.com/sample-org/pebble-pay/tree/main/app", "https://github.com/sample-org/pebble-pay"),
        ("https://github.com/sample-org/pebble.pay_2", "https://github.com/sample-org/pebble.pay_2"),
    ],
)  # fmt: skip
def test_the_link_of_a_repository_has_one_spelling(link: str, repository: str) -> None:
    assert repository_of(link) == repository


@pytest.mark.parametrize(
    "link",
    [
        "https://github.com/sample-org",  # an account, not a repository
        "https://gitlab.com/sample-org/pebble-pay",
        "https://sample-org.github.io/pebble-pay",
        "https://github.com/sample-org/..",
        "not a link at all",
        "https://[broken",
    ],
)
def test_another_link_is_not_a_repository(link: str) -> None:
    assert repository_of(link) is None


def test_the_readme_of_a_repository_has_its_address_in_the_api() -> None:
    assert readme_address("https://github.com/sample-org/pebble-pay") == README


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        (README, True),
        (MOVED, True),
        ("https://api.github.com/user", False),
        ("https://api.github.com/search/repositories?q=hedera", False),
        ("http://api.github.com/repos/a/b/readme", False),
        ("https://api.github.com.example.test/repos/a/b/readme", False),
        ("https://api.github.com/repos/a/../../user", False),
    ],
)
def test_only_the_pages_of_the_api_about_repositories_are_allowed(url: str, ok: bool) -> None:
    assert allowed(url) is ok


# --------------------------------------------------------------------- building the client


def settings_for(tmp_path: Path, **values: object) -> Settings:
    base = {
        "collector_name": NAME,
        "collector_contact_email": CONTACT,
        "github_token": TOKEN,
        "data_dir": str(tmp_path),
    }
    base.update(values)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def test_it_does_not_start_without_a_token(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="GITHUB_TOKEN"):
        github_client(settings_for(tmp_path, github_token=""))


def test_the_pause_is_never_shorter_than_one_second(tmp_path: Path) -> None:
    with pytest.raises(CollectorRefused, match="pause"):
        github_client(settings_for(tmp_path), pause_seconds=0.5)


def test_it_does_not_start_after_a_no_or_during_a_cooldown(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    count = request_count(settings)
    count.note_too_many("60")
    with pytest.raises(CollectorRefused, match="too many requests"):
        github_client(settings)
    assert github_client(settings, wait_for_cooldown=True).wait_for_cooldown
    count.note_refusal(401)
    with pytest.raises(CollectorRefused, match="refused"):
        github_client(settings)


def test_the_switch_is_read_from_the_settings_file_before_every_request(tmp_path: Path) -> None:
    env = tmp_path / "switch.env"
    env.write_text("COLLECT_GITHUB=off\n", encoding="utf-8")
    client = github_client(settings_for(tmp_path), env_file=env)
    assert client.is_enabled() is False
    env.write_text("COLLECT_GITHUB=on\n", encoding="utf-8")
    assert client.is_enabled() is True
