"""What the visitors of the public copy do (web/visits.py, design 12.5 and screen S9)."""

from __future__ import annotations

from datetime import UTC, datetime

from hackathon_memory.web.visits import (
    Action,
    Visit,
    action_of,
    described,
    device_of,
    failed,
    failures,
    place_of,
    referrer_of,
    summary,
    unexpected,
    whole_number,
)


def test_each_request_says_what_a_visitor_did() -> None:
    assert action_of("/", {"idea": "pay vendors", "mode": "meaning"}) == (
        "search", {"idea": "pay vendors", "mode": "meaning"})  # fmt: skip
    assert action_of("/", {"idea": "pay", "ai": "1"})[0] == "gemini"
    assert action_of("/", {"event": "7|8"}) == ("filter", {"filters": {"event": "7|8"}})
    assert action_of("/", {"open": "837", "idea": "x"}) == ("card", {"idea": "x", "project": 837})
    assert action_of("/", {"view": "graph"})[0] == "graph"
    assert action_of("/", {"view": "mainnet", "event": "7"}) == (
        "mainnet", {"view": "mainnet", "filters": {"event": "7"}})  # fmt: skip
    assert action_of("/", {}) == ("home", {})
    assert action_of("/", {"page": "3"})[0] == "list"
    assert action_of("/project/837/panel", {}) == ("card", {"project": 837})
    assert action_of("/project/566/mainnet", {}) == ("mainnet-path", {"project": 566})
    assert action_of("/check", {"repo": "github.com/a/b", "event": "7676"}) == (
        "check", {"repo": "github.com/a/b", "event": "7676"})  # fmt: skip
    assert action_of("/about/how", {}) == ("about", {"note": "how"})
    assert action_of("/jevadu-pitch.pdf", {}) == ("deck", {})
    for nothing in ("/static/style.css", "/owner/visits", "/check/progress", "/health",
                    "/github/callback", "/_vercel/insights/view"):  # fmt: skip
        assert action_of(nothing, {}) is None


def test_a_number_that_the_site_never_writes_is_no_number() -> None:
    """A sign such as "²" passes str.isdigit() and int() refuses it, as it refuses 5,000 digits:
    either broke a page of the public copy, where each visit is noted (7 November 2026)."""
    assert whole_number("837") == 837 and whole_number("0") == 0
    for odd in ("²", "٣", "1" * 5000, "", "-3", " 3", "3.0"):
        assert whole_number(odd) is None
    assert action_of("/", {"open": "²"}) == ("home", {})
    assert action_of("/", {"open": "1" * 5000}) == ("home", {})
    assert action_of("/project/²/panel", {}) is None


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
    assert words("mainnet-path", {"project": 837}) == (
        "opened the path of AgentMarkets on the main network")  # fmt: skip
    assert words("mainnet", {"idea": "pay"}) == "looked at the main network of “pay”"
    assert words("check", {"repo": "github.com/a/b", "event": "7676"}) == (
        "checked github.com/a/b against ETHDenver 2026")  # fmt: skip
    assert words("filter", {"filters": {"event": "7676"}}) == (
        "filtered the list (event: ETHDenver 2026)")  # fmt: skip
    assert words("search", {"idea": "pay vendors", "mode": "meaning"}) == (
        "searched “pay vendors” by meaning")  # fmt: skip
    assert words("check", {"repo": "github.com/a/b", "status": 429}) == (
        "checked github.com/a/b, answered 429")  # fmt: skip
    assert words("deck", {}) == "opened the pitch deck"


def test_a_failed_action_keeps_what_went_wrong() -> None:
    """A failed action reads with the words that the page showed, and the summary of the copy's
    owner counts them. An error that no page answers is kept by its kind, never by its message.
    Nothing is kept outside a request that is noted (3 November 2026)."""
    at = datetime(2026, 11, 7, 10, tzinfo=UTC)
    refused = {"repo": "github.com/a/b", "status": 400, "failed": ["This is not a repository."]}
    soft = {"idea": "pay", "mode": "meaning", "failed": ["Google did not answer (ReadTimeout)."]}
    assert described(Action(at, "check", refused), {}, {}) == (
        "checked github.com/a/b, answered 400, and failed: This is not a repository.")  # fmt: skip
    assert described(Action(at, "search", soft), {}, {}) == (
        "searched “pay” by meaning, and failed: Google did not answer (ReadTimeout).")  # fmt: skip
    assert unexpected(RuntimeError("the key sk-123 leaked")) == (
        "The site failed on an error that it did not expect (RuntimeError).")  # fmt: skip
    failed("Gemini did not answer.")  # no request is noted: nothing is kept, nothing breaks
    kept: list[str] = []
    token = failures.set(kept)
    try:
        failed("Gemini did not answer.")
        failed("Gemini  did not\nanswer.")  # the same words: kept once
        failed(None)
    finally:
        failures.reset(token)
    assert kept == ["Gemini did not answer."]
    visit = Visit("a1b2", "Tunis, TN", None, "Chrome on Windows",
                  [Action(at, "check", refused), Action(at, "search", soft)])  # fmt: skip
    counted = dict(summary([visit])["failures"])
    assert counted == {"This is not a repository.": 1, "Google did not answer (ReadTimeout).": 1}
