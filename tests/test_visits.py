"""What the visitors of the public copy do (web/visits.py, design 12.5 and screen S9)."""

from __future__ import annotations

from datetime import UTC, datetime

from hackathon_memory.web.visits import (
    Action,
    action_of,
    described,
    device_of,
    place_of,
    referrer_of,
)


def test_each_request_says_what_a_visitor_did() -> None:
    assert action_of("/", {"idea": "pay vendors", "mode": "meaning"}) == (
        "search", {"idea": "pay vendors", "mode": "meaning"})  # fmt: skip
    assert action_of("/", {"idea": "pay", "ai": "1"})[0] == "gemini"
    assert action_of("/", {"event": "7|8"}) == ("filter", {"filters": {"event": "7|8"}})
    assert action_of("/", {"open": "837", "idea": "x"}) == ("card", {"idea": "x", "project": 837})
    assert action_of("/", {"view": "graph"})[0] == "graph"
    assert action_of("/", {}) == ("home", {})
    assert action_of("/", {"page": "3"})[0] == "list"
    assert action_of("/project/837/panel", {}) == ("card", {"project": 837})
    assert action_of("/check", {"repo": "github.com/a/b", "event": "7676"}) == (
        "check", {"repo": "github.com/a/b", "event": "7676"})  # fmt: skip
    assert action_of("/about/how", {}) == ("about", {"note": "how"})
    for nothing in ("/static/style.css", "/owner/visits", "/check/progress", "/health",
                    "/github/callback", "/_vercel/insights/view"):  # fmt: skip
        assert action_of(nothing, {}) is None


def test_the_place_the_site_and_the_browser_stay_short() -> None:
    city = {"x-vercel-ip-country": "BR", "x-vercel-ip-country-region": "SP",
            "x-vercel-ip-city": "S%C3%A3o%20Paulo"}  # fmt: skip
    assert place_of(city) == ("BR", "SP", "São Paulo")
    assert place_of({}) == (None, None, None)
    came = {"referer": "https://4hacks.io/fss/submit?id=9"}
    assert referrer_of(came, "jevadu.example") == "4hacks.io/fss/submit"  # never the query
    assert referrer_of({"referer": "https://jevadu.example/?idea=x"}, "jevadu.example") is None
    assert referrer_of({}, "jevadu.example") is None
    windows = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit Chrome/130.0 Safari/537.36"
    assert device_of(windows) == "Chrome on Windows"
    assert device_of("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1") == "Safari on iOS"
    assert device_of("Mozilla/5.0 HeadlessChrome/130.0") == "robot"


def test_an_action_reads_as_words() -> None:
    at = datetime(2026, 11, 7, 10, tzinfo=UTC)
    projects, events = {837: "AgentMarkets"}, {"7676": "ETHDenver 2026"}

    def words(action: str, detail: dict) -> str:
        return described(Action(at, action, detail), projects, events)

    assert words("card", {"project": 837}) == "opened the card of AgentMarkets"
    assert words("check", {"repo": "github.com/a/b", "event": "7676"}) == (
        "checked github.com/a/b against ETHDenver 2026")  # fmt: skip
    assert words("filter", {"filters": {"event": "7676"}}) == (
        "filtered the list (event: ETHDenver 2026)")  # fmt: skip
    assert words("search", {"idea": "pay vendors", "mode": "meaning"}) == (
        "searched “pay vendors” by meaning")  # fmt: skip
    assert words("check", {"repo": "github.com/a/b", "status": 429}) == (
        "checked github.com/a/b, answered 429")  # fmt: skip
