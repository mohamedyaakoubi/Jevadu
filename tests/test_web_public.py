"""The public copy of the website (web/public.py, design 12.5): no page indexed, the AI and the
register off until turned on, a budget of its own, an allowance for each visitor, one time only,
and Cloudflare's Turnstile before Gemini, GitHub or Hedera. Everything is invented."""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs

import httpx
import psycopg
import pytest
from pydantic import SecretStr
from test_web import (  # noqa: F401  (the fixtures of the website's tests)
    REPO,
    SEARCH,
    checkable,
    chromium,
    compare_answer,
    model_calls,
    order_of,
    served,
    site,
)

from hackathon_memory.finops import meter
from hackathon_memory.finops.meter import Tags
from hackathon_memory.settings import Settings
from hackathon_memory.web import public, switch, turnstile
from searchfakes import google

SALT = "s" * 40
HX = {"HX-Request": "true"}


def public_site(client, **changes):  # noqa: ANN001, ANN003, ANN201
    return client.make(app_options={"public": True}, public_salt=SecretStr(SALT), **changes)


# Cloudflare's own keys for tests (developers.cloudflare.com/turnstile/troubleshooting/testing/,
# read on 30 October 2026): a site key that always passes, a secret that always validates.
SITE_KEY = "1x00000000000000000000AA"
SECRET = "1x0000000000000000000000000000000AA"
TOKEN = "XXXX.DUMMY.TOKEN.XXXX"
CONFIRM = "asks Cloudflare whether you are a person"
INSIGHTS = "/_vercel/insights/script.js"  # Vercel's Web Analytics (design 12.5)


class Cloudflare:
    """A stand-in for Cloudflare's siteverify: the forms it was sent, and its answer (a JSON
    object, a status, or an error of the network)."""

    def __init__(self) -> None:
        self.asked: list[dict[str, list[str]]] = []
        self.answer: dict | int | Exception = {
            "success": True, "action": "visitor", "hostname": "jevadu.mohamedyaakoubi.com"
        }  # fmt: skip

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == turnstile.SITEVERIFY and request.method == "POST"
        self.asked.append(parse_qs(request.content.decode()))
        if isinstance(self.answer, Exception):
            raise self.answer
        if isinstance(self.answer, int):
            return httpx.Response(self.answer)
        return httpx.Response(200, json=self.answer)


def guarded_site(client, cloudflare: Cloudflare, **changes):  # noqa: ANN001, ANN003, ANN201
    """The public copy with the keys of Turnstile, which asks `cloudflare`."""
    asker = httpx.Client(transport=httpx.MockTransport(cloudflare))
    return client.make(app_options={"public": True, "turnstile_client": asker},
                       public_salt=SecretStr(SALT), turnstile_site_key=SITE_KEY,
                       turnstile_secret_key=SecretStr(SECRET), **changes)  # fmt: skip


def asks(database: str) -> int:
    """The asks of Gemini counted for the visitors, all together."""
    with psycopg.connect(database) as conn:
        (counted,) = conn.execute(
            "SELECT coalesce(sum(count), 0) FROM visitor_uses "
            "WHERE scope = 'visitor' AND kind = 'ai'"
        ).fetchone()
    return counted


def test_no_page_is_indexed_on_the_laptop_or_on_the_public_copy(site) -> None:  # noqa: ANN001, F811
    client, _, _, _ = site
    for one in (client, public_site(client)):
        assert one.get("/robots.txt").text == "User-agent: *\nDisallow: /\n"
        page = one.get("/")
        assert page.headers["X-Robots-Tag"] == "noindex, nofollow"
        assert '<meta name="robots" content="noindex, nofollow">' in page.text
    assert "X-Frame-Options" not in client.get("/").headers  # only the public copy adds these
    open_copy = public_site(client)
    assert open_copy.get("/").headers["X-Frame-Options"] == "DENY"
    assert open_copy.get("/").headers["Strict-Transport-Security"] == "max-age=31536000"
    # a visitor in plain HTTP, as Cloudflare says, goes to HTTPS
    moved = open_copy.get("/?idea=pay", headers={"X-Forwarded-Proto": "http"},
                          follow_redirects=False)  # fmt: skip
    assert moved.status_code == 301 and moved.headers["location"] == "https://testserver/?idea=pay"
    laptop = client.get("/", headers={"X-Forwarded-Proto": "http"}, follow_redirects=False)
    assert laptop.status_code == 200  # the laptop's own site is never redirected
    # Vercel's analytics count the pages of the public copy only (1 November 2026)
    assert INSIGHTS not in laptop.text and INSIGHTS in open_copy.get("/").text


def test_the_ai_stays_off_on_the_public_copy_until_it_is_turned_on(site) -> None:  # noqa: ANN001, F811
    client, fake, _, database = site
    open_copy = public_site(client)
    asked = len(fake.requests)
    page = open_copy.get("/", params={"idea": "pay street vendors", "mode": "meaning", "ai": "1"})
    assert "the AI is turned off, so these are keyword results" in page.text
    assert len(fake.requests) == asked  # no call to a model, so nothing paid
    laptop = client.get("/", params={"idea": "pay street vendors", "mode": "meaning"})
    assert "the AI is turned off" not in laptop.text  # the laptop's site is never limited
    public.turn(database, public.AI, True)
    turned_on = open_copy.get("/", params={"idea": "pay a vendor in coins", "mode": "meaning"})
    assert "the AI is turned off" not in turned_on.text and len(fake.requests) > asked


def test_the_public_copy_spends_from_a_budget_of_its_own(site, monkeypatch) -> None:  # noqa: ANN001, F811
    client, _, _, database = site
    counted, _, _ = google()
    environments = []

    def made(settings, purpose, **_):  # noqa: ANN001, ANN003, ANN202
        environments.append(settings.llm_environment)
        return counted

    monkeypatch.setattr(meter, "metered_client", made)
    idea = {"idea": "pay a vendor in coins", "mode": "meaning"}
    client.make(app_options={"google": None}).get("/", params=idea)
    public.turn(database, public.AI, True)
    open_copy = client.make(app_options={"public": True, "google": None},
                            public_salt=SecretStr(SALT))  # fmt: skip
    open_copy.get("/", params=idea)
    assert environments == ["test", "public"]  # the laptop's site, then the public copy


def test_one_ask_of_gemini_counts_once_for_all_its_calls(site) -> None:  # noqa: ANN001, F811
    """The order of the closest and the comparison of the first ten are one ask; asked again, it
    is kept and costs nothing. Past the allowance, the results keep the search order."""
    client, fake, ids, database = site
    public.turn(database, public.AI, True)
    open_copy = public_site(client, public_ai_per_visitor=2)
    first = {"idea": "pay a street vendor with coins", "ai": "1"}
    fake.answer_queue = [json.dumps({"closest": [2]})]
    page = open_copy.get("/", params=first)
    assert "Sorted by Gemini" in page.text
    assert "You can ask Gemini 1 more time on this public copy." in page.text
    fake.answer_text = compare_answer((1, ["what_it_does"]))  # Pebble Pay alone has a card
    shown = ",".join(order_of(page.text))
    compared = open_copy.get("/compare", params={"idea": first["idea"], "ids": shown})
    assert compared.status_code == 200 and "Same 1." in compared.text
    assert "Sorted by Gemini" in open_copy.get("/", params=first).text  # kept, not asked again
    assert asks(database) == 1
    fake.answer_queue = [json.dumps({"closest": [1]})]
    second = open_copy.get("/", params={"idea": "a market for carbon credits", "ai": "1"})
    assert "Sorted by Gemini" in second.text and asks(database) == 2
    third = open_copy.get("/", params={"idea": "a game of coins", "ai": "1"})
    assert "Sorted by Gemini" not in third.text and asks(database) == 2
    used = (
        "This public copy of Jevadu gives each visitor 2 asks of Gemini, one time only, and "
        "you have used them, so these results are in the search order."
    )
    assert used in third.text
    pebble = str(ids["Pebble Pay"])  # a project's own window asks once more
    one = open_copy.get("/compare", params={"idea": "a game of coins", "ids": pebble, "one": "1"})
    assert one.status_code == 429 and "2 asks of Gemini, one time only" in one.text
    assert "Sorted by Gemini" in open_copy.get("/", params=first).text  # an ask counted stays open


def test_each_visitor_has_an_allowance_of_checks_one_time_only(site, monkeypatch) -> None:  # noqa: ANN001, F811
    client, _, _, database = site
    monkeypatch.setitem(public.ALLOWANCE, public.CHECK, 2)
    open_copy = public_site(client)
    asked = {"repo": REPO, "event": checkable(database)}
    one = {"CF-Connecting-IP": "203.0.113.5", **HX}
    for _ in range(2):
        assert open_copy.get("/check", params=asked, headers=one).status_code == 200
    third = open_copy.get("/check", params=asked, headers=one)
    assert third.status_code == 429
    assert "gives each visitor 2 checks, one time only, and you have used them." in third.text
    other = {"CF-Connecting-IP": "198.51.100.7", **HX}
    assert open_copy.get("/check", params=asked, headers=other).status_code == 200
    assert client.get("/check", params=asked, headers=one).status_code == 200  # the laptop's site
    started_again = public_site(client)  # nothing is renewed
    assert started_again.get("/check", params=asked, headers=one).status_code == 429
    switches, counts = public.totals(database)
    assert switches == {public.AI: False, public.REGISTER: False}
    assert counts[public.CHECK] == (2, 3)  # two visitors, three checks counted


def test_one_address_holds_the_allowances_of_a_few_visitors(site, monkeypatch) -> None:  # noqa: ANN001, F811
    """People behind one address each have their own allowance, up to SHARED of them: another
    name of the browser is no way around the count."""
    client, _, _, database = site
    monkeypatch.setitem(public.ALLOWANCE, public.CHECK, 1)
    monkeypatch.setattr(public, "SHARED", 2)
    open_copy = public_site(client)
    asked = {"repo": REPO, "event": checkable(database)}
    campus = {"CF-Connecting-IP": "203.0.113.9", **HX}
    for browser in ("Firefox/131", "Chrome/130"):
        allowed = open_copy.get("/check", params=asked, headers={**campus, "User-Agent": browser})
        assert allowed.status_code == 200
    third = open_copy.get("/check", params=asked, headers={**campus, "User-Agent": "Safari/18"})
    assert third.status_code == 429
    elsewhere = {"CF-Connecting-IP": "198.51.100.9", "User-Agent": "Safari/18", **HX}
    assert open_copy.get("/check", params=asked, headers=elsewhere).status_code == 200


@pytest.mark.browser
def test_a_used_allowance_is_read_where_it_was_asked(site, chromium, monkeypatch) -> None:  # noqa: ANN001, F811
    """An answer of 429 takes the place of the steps of the check: before 29 October 2026 the
    page's script showed only answers of 400, 404 and 503, and the visitor saw nothing."""
    client, _, _, database = site
    monkeypatch.setitem(public.ALLOWANCE, public.CHECK, 1)
    event = checkable(database)
    page = served(chromium, public_site(client), viewport={"width": 1440, "height": 900})
    for _ in range(2):
        page.goto("http://site.test/")
        page.fill("#check-repo", "github.com/sample-org/pebble-pay")
        page.select_option("#check-event", event)
        page.locator("#check button[type=submit]").click()
        page.wait_for_selector("#viewer[open]")
    page.wait_for_selector("#viewer-body:has-text('gives each visitor 1 check, one time only')")
    page.context.close()


def test_the_gate_counts_each_call_and_refuses_what_it_cannot_count(site) -> None:  # noqa: ANN001, F811
    _, _, _, database = site
    limits = public.Limits(lambda: database, ai_per_visitor=1)
    with pytest.raises(public.Refused, match="no call for 'rewrite'"):
        limits.admit(Tags("rewrite"))
    with pytest.raises(public.Refused):  # a call that knows no visitor
        limits.admit(Tags("embed_query"))
    token = public.visitor.set(public.visitor_of({"user-agent": "Firefox"}, "203.0.113.5", SALT))
    try:
        limits.admit(Tags("rerank", item_ref=public.press_key("an idea", "order")))
        limits.admit(Tags("compare", item_ref=public.press_key("an idea", "order")))  # the same ask
        limits.admit(Tags("compare", item_ref=public.press_key("AN  Idea", "order")))  # same words
        with pytest.raises(public.Refused, match="'ai'"):
            limits.admit(Tags("compare", item_ref=public.press_key("an idea", "one:7")))
        limits.admit(Tags("embed_query"))  # the searches by meaning have their own allowance
        assert limits.left(public.AI, public.visitor.get()) == 0
        assert limits.left(public.EMBED, public.visitor.get()) == public.ALLOWANCE[public.EMBED] - 1
    finally:
        public.visitor.reset(token)


def test_registering_is_paused_on_the_public_copy_until_it_is_turned_on(site) -> None:  # noqa: ANN001, F811
    client, _, _, database = site
    open_copy = public_site(client)
    form = {"repo": REPO, "event": checkable(database), "starts": "", "ends": ""}
    paused = open_copy.post("/register", data=form, headers=HX)
    assert paused.status_code == 503 and "registering on Hedera is paused" in paused.text
    public.turn(database, public.REGISTER, True)
    opened = open_copy.post("/register", data=form, headers=HX)
    assert "registering on Hedera is paused" not in opened.text  # on to the usual rules
    assert "Check the repository first" in opened.text and client.writes.written == []


def test_the_switch_turns_a_part_on_and_says_what_was_used(site, monkeypatch, capsys) -> None:  # noqa: ANN001, F811
    _, _, _, database = site
    monkeypatch.setattr(switch, "Settings", lambda: Settings(_env_file=None, database_url=database))
    assert switch.main(["ai", "on"]) == 0
    said = capsys.readouterr().out
    assert "the AI (search by meaning, order, comparisons): on" in said
    assert "registering on Hedera: off" in said
    assert "the public copy's own budget: $0.00 spent of $30.00, today $0.00 of $5.00" in said
    assert ("each visitor, one time: 12 asks of Gemini, 200 searches by meaning, 10 checks, "
            "10 readings again, 3 registrations") in said  # fmt: skip
    assert "used since the start, asks of Gemini: 0 by 0 visitors" in said
    assert switch.main(["everything", "on"]) == 2


def test_a_visitor_is_a_salted_hash_of_the_address_and_of_the_browser() -> None:
    one = public.visitor_of({"cf-connecting-ip": "203.0.113.5", "user-agent": "Firefox"},
                            "127.0.0.1", SALT)  # fmt: skip
    assert re.fullmatch("[0-9a-f]{64}", one.key) and re.fullmatch("[0-9a-f]{64}", one.address)
    assert one == public.visitor_of({"user-agent": "Firefox"}, "203.0.113.5", SALT)  # the peer
    chrome = public.visitor_of({"cf-connecting-ip": "203.0.113.5", "user-agent": "Chrome"}, None,
                               SALT)  # fmt: skip
    assert chrome.key != one.key and chrome.address == one.address  # one address, two people
    assert one != public.visitor_of({"cf-connecting-ip": "203.0.113.5", "user-agent": "Firefox"},
                                    None, "other salt")  # fmt: skip
    home = public.visitor_of({"cf-connecting-ip": "2001:db8:1:2::5"}, None, SALT)
    assert home == public.visitor_of({"cf-connecting-ip": "2001:db8:1:2:ffff::9"}, None, SALT)
    assert home != public.visitor_of({"cf-connecting-ip": "2001:db8:1:3::5"}, None, SALT)
    with pytest.raises(ValueError):
        public.turn("unused", "everything", True)


def test_the_switch_writes_into_the_public_copys_own_database(site, monkeypatch, capsys) -> None:  # noqa: ANN001, F811
    """On its host, the copy reads its switches from its own database (Neon), not this
    computer's: PUBLIC_DATABASE_URL names it."""
    _, _, _, database = site
    elsewhere = Settings(_env_file=None, database_url="postgresql://nobody@127.0.0.1:1/none",
                         public_database_url=database)  # fmt: skip
    monkeypatch.setattr(switch, "Settings", lambda: elsewhere)
    assert switch.main(["register", "on"]) == 0
    assert "the public copy's database: on its host" in capsys.readouterr().out
    assert public.totals(database)[0][public.REGISTER] is True


# ----------------------------------------------------- Cloudflare's Turnstile (web/turnstile.py)


def test_a_visitor_is_found_to_be_a_person_before_gemini_github_or_hedera(site) -> None:  # noqa: ANN001, F811
    client, fake, ids, database = site
    public.turn(database, public.AI, True)
    public.turn(database, public.REGISTER, True)
    cloudflare = Cloudflare()
    open_copy = guarded_site(client, cloudflare)
    idea = {"idea": "pay a street vendor with coins", "ai": "1"}
    before = len(fake.requests)
    page = open_copy.get("/", params=idea)
    assert 'id="person-check"' in page.text and f'data-sitekey="{SITE_KEY}"' in page.text
    assert CONFIRM in page.text and order_of(page.text)  # by meaning, in the search order
    assert "keyword results" not in page.text and model_calls(fake, before) == 0
    pebble = str(ids["Pebble Pay"])
    waiting = [
        open_copy.get("/compare", params={"idea": idea["idea"], "ids": pebble, "one": "1"},
                      headers=HX),
        open_copy.get("/check", params={"repo": REPO, "event": checkable(database)}, headers=HX),
        open_copy.post(f"/project/{pebble}/read-again", headers=HX),
        open_copy.post("/register", data={"repo": REPO, "event": checkable(database),
                                          "starts": "", "ends": ""}, headers=HX),
    ]  # fmt: skip
    for answer in waiting:
        assert answer.status_code == 403 and CONFIRM in answer.text
    assert model_calls(fake, before) == 0 and asks(database) == 0 and client.writes.written == []
    assert open_copy.post("/person-check", data={"token": TOKEN}).status_code == 204
    assert cloudflare.asked == [{"secret": [SECRET], "response": [TOKEN]}]  # never the address
    fake.answer_queue = [json.dumps({"closest": [2]})]
    page = open_copy.get("/", params=idea)
    assert 'id="person-check"' not in page.text and "Sorted by Gemini" in page.text
    fake.answer_text = compare_answer((1, ["what_it_does"]))
    one = open_copy.get("/compare", params={"idea": idea["idea"], "ids": pebble, "one": "1"})
    assert one.status_code == 200 and "Same 1." in one.text


def test_cloudflare_saying_no_or_nothing_gives_no_pass(site) -> None:  # noqa: ANN001, F811
    client, _, ids, database = site
    public.turn(database, public.AI, True)
    cloudflare = Cloudflare()
    open_copy = guarded_site(client, cloudflare)

    def kept(token: str = TOKEN) -> int:
        return open_copy.post("/person-check", data={"token": token}).status_code

    cloudflare.answer = {"success": False, "error-codes": ["timeout-or-duplicate"]}
    assert kept() == 403
    cloudflare.answer = {"success": True, "action": "login"}  # a token for another action
    assert kept() == 403
    cloudflare.answer = 500
    assert kept() == 503
    cloudflare.answer = httpx.ConnectError("no route to Cloudflare")
    assert kept() == 503
    asked = len(cloudflare.asked)
    assert kept("") == 403 and kept("x" * (turnstile.LONGEST_TOKEN + 1)) == 403
    assert len(cloudflare.asked) == asked  # no token worth asking about
    assert 'id="person-check"' in open_copy.get("/").text  # still no pass
    one = open_copy.get("/compare", params={"idea": "an idea", "ids": str(ids["Pebble Pay"]),
                                            "one": "1"})  # fmt: skip
    assert one.status_code == 403


def test_a_pass_holds_for_a_day_and_guards_the_counts_too(site) -> None:  # noqa: ANN001, F811
    """Each place asks for the pass before it counts; the count asks again, so a place that
    forgets cannot spend an allowance for a program."""
    _, _, _, database = site
    limits = public.Limits(lambda: database, ai_per_visitor=5, needs_pass=True)
    who = public.visitor_of({"user-agent": "Firefox"}, "203.0.113.5", SALT)
    assert not limits.passed(who) and not limits.passed(None)
    assert not limits.take(public.CHECK, who)
    assert not limits.press(who, public.press_key("an idea", "order"))
    assert limits.take(public.EMBED, who)  # the search by meaning needs no pass
    limits.keep_pass(who)
    assert limits.passed(who) and limits.take(public.CHECK, who)
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE visitor_passes SET passed_at = now() - make_interval(hours => %s)",
                     (public.PASS_HOURS + 1,))  # fmt: skip
    assert not limits.passed(who) and not limits.take(public.CHECK, who)
    limits.keep_pass(who)  # a new confirmation moves the time
    assert limits.passed(who)
    assert public.Limits(lambda: database, ai_per_visitor=5).passed(None)  # no pass asked


def test_the_laptop_and_a_copy_without_both_keys_never_ask(site) -> None:  # noqa: ANN001, F811
    client, _, _, _ = site
    assert client.post("/person-check", data={"token": TOKEN}).status_code == 404
    assert 'id="person-check"' not in client.get("/").text
    for open_copy in (public_site(client), public_site(client, turnstile_site_key=SITE_KEY)):
        assert open_copy.post("/person-check", data={"token": TOKEN}).status_code == 404
        assert 'id="person-check"' not in open_copy.get("/").text


TURNSTILE_SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js"
# Cloudflare's script, played: the widget gives a token at once, and a new one on each reset.
GIVES_TOKENS = """
window.turnstile = {
  render: function (box, options) {
    window.tsOptions = options;
    setTimeout(function () { options.callback("XXXX.DUMMY.TOKEN.XXXX"); }, 0);
    return "widget-1";
  },
  reset: function () {
    window.tsResets = (window.tsResets || 0) + 1;
    setTimeout(function () { window.tsOptions.callback("XXXX.DUMMY.TOKEN.XXXX"); }, 0);
  },
  remove: function () { window.tsRemoved = true; }
};
window.jevaduPerson();
"""
# ... and the widget asks for a click, a moment after the page opened.
ASKS_A_CLICK = """
window.turnstile = {
  render: function (box, options) {
    setTimeout(function () {
      window.tsWindowWasOpen = document.getElementById("viewer").open;
      options["before-interactive-callback"]();
    }, 300);
    return "widget-1";
  },
  reset: function () {}, remove: function () {}
};
window.jevaduPerson();
"""


def played(page, script: str | None) -> None:  # noqa: ANN001
    """Cloudflare's script on the page is `script`; None: it cannot load."""

    def answer(route) -> None:  # noqa: ANN001
        if script is None:
            route.abort()
        else:
            route.fulfill(status=200, body=script, headers={"content-type": "text/javascript"})

    page.route(lambda url: url.startswith(TURNSTILE_SCRIPT), answer)


@pytest.mark.browser
def test_the_widget_token_gives_the_pass_and_the_box_goes(site, chromium) -> None:  # noqa: ANN001, F811
    client, _, _, _ = site
    cloudflare = Cloudflare()
    page = served(chromium, guarded_site(client, cloudflare),
                  viewport={"width": 1440, "height": 900})  # fmt: skip
    played(page, GIVES_TOKENS)
    page.goto("http://site.test/")
    page.wait_for_selector("#person-check", state="detached")
    options = page.evaluate(
        "[window.tsOptions.action, window.tsOptions.appearance, window.tsRemoved]"
    )
    assert options == ["visitor", "interaction-only", True]
    assert cloudflare.asked == [{"secret": [SECRET], "response": [TOKEN]}]
    page.context.close()


@pytest.mark.browser
def test_a_refused_token_is_never_sent_again(site, chromium) -> None:  # noqa: ANN001, F811
    client, _, _, _ = site
    cloudflare = Cloudflare()
    cloudflare.answer = {"success": False, "error-codes": ["invalid-input-response"]}
    page = served(chromium, guarded_site(client, cloudflare),
                  viewport={"width": 1440, "height": 900})  # fmt: skip
    played(page, GIVES_TOKENS)
    page.goto("http://site.test/")
    page.wait_for_selector("#person-check.shown")
    assert "Cloudflare could not confirm" in page.locator("#person-check").inner_text()
    assert page.evaluate("window.tsResets") == 2 and len(cloudflare.asked) == 3  # a token each
    page.context.close()


@pytest.mark.browser
def test_a_click_asked_by_cloudflare_closes_the_window_over_the_box(site, chromium) -> None:  # noqa: ANN001, F811
    """The windows are modal: the box of Turnstile behind one could not be clicked."""
    client, _, ids, _ = site
    page = served(chromium, guarded_site(client, Cloudflare()),
                  viewport={"width": 1440, "height": 900})  # fmt: skip
    played(page, ASKS_A_CLICK)
    page.goto(f"http://site.test/?open={ids['Pebble Pay']}")
    page.wait_for_selector("#person-check.shown")
    assert page.evaluate("window.tsWindowWasOpen") is True
    assert page.evaluate("document.getElementById('viewer').open") is False
    assert "Tick the box below once." in page.locator("#person-check").inner_text()
    page.context.close()


@pytest.mark.browser
def test_without_cloudflare_the_page_says_so_and_the_search_works(site, chromium) -> None:  # noqa: ANN001, F811
    client, _, ids, database = site
    public.turn(database, public.AI, True)
    page = served(chromium, guarded_site(client, Cloudflare()),
                  viewport={"width": 1440, "height": 900})  # fmt: skip
    played(page, None)
    page.goto(SEARCH)
    page.wait_for_selector("#person-check.shown")
    assert "could not load" in page.locator("#person-check").inner_text()
    pebble = ids["Pebble Pay"]
    page.locator(f"#result-{pebble} .result-link").click()
    page.locator(f"#one-compare-{pebble} button").click()
    page.wait_for_selector(f"#one-compare-{pebble}:has-text('{CONFIRM}')")  # an answer of 403
    page.context.close()


@pytest.mark.browser
def test_a_browser_check_of_vercel_asks_the_whole_page_again_once(site, chromium) -> None:  # noqa: ANN001, F811
    """Vercel's firewall may answer a request of the page with its own check that the visitor
    uses a browser: an answer of 429 with X-Vercel-Mitigated: challenge (seen on 30 October 2026).
    It is never shown inside a part of the page: the page is asked again, once a minute at most."""
    client, _, ids, _ = site
    page = served(chromium, public_site(client), viewport={"width": 1440, "height": 900})
    checkpoint = "Vercel Security Checkpoint"

    def challenged(route) -> None:  # noqa: ANN001
        headers = {"content-type": "text/html", "x-vercel-mitigated": "challenge"}
        route.fulfill(status=429, body=f"<html><body>{checkpoint}</body></html>", headers=headers)

    page.route(lambda url: "/panel" in url, challenged)
    pebble = ids["Pebble Pay"]
    page.goto(SEARCH)
    page.evaluate("window.hmBefore = true")
    page.locator(f"#result-{pebble} .result-link").click()
    page.wait_for_function("window.hmBefore === undefined")  # the page was asked again
    # its address names the project, so the page comes back with its window open
    page.wait_for_selector("#viewer[open] .project")
    assert checkpoint not in page.content()
    page.keyboard.press("Escape")
    page.wait_for_selector("#viewer", state="hidden")
    page.evaluate("window.hmBefore = true")
    page.locator(f"#result-{pebble} .result-link").click()  # again within the minute: no loop
    page.wait_for_selector("#viewer-body .alert-danger")
    assert page.evaluate("window.hmBefore") is True and checkpoint not in page.content()
    page.context.close()


def owners_copy(client, stand_in, **changes):  # noqa: ANN001, ANN003, ANN201
    """The public copy with Jevadu's GitHub App, which talks with `stand_in`, and the GitHub
    account of the copy's owner."""
    talk = httpx.Client(transport=httpx.MockTransport(stand_in))
    return client.make(app_options={"public": True, "github_app_client": talk},
                       public_salt=SecretStr(SALT), github_app_slug="jevadu-register",
                       github_app_client_id="Iv1.standin",
                       github_app_client_secret=SecretStr("standin-secret"),
                       public_owner_github="MohamedYaakoubi", **changes)  # fmt: skip


def test_the_copys_owner_is_not_counted_for_checks_but_for_gemini(site) -> None:  # noqa: ANN001, F811
    from dataclasses import replace

    _, _, _, database = site
    limits = public.Limits(lambda: database, ai_per_visitor=1)
    owner = replace(public.visitor_of({"user-agent": "Firefox"}, "203.0.113.5", SALT), owner=True)
    for _ in range(public.ALLOWANCE[public.CHECK] + 3):
        assert limits.take(public.CHECK, owner)
    assert limits.take(public.REGISTER, owner) and limits.take(public.REFRESH, owner)
    assert limits.left(public.CHECK, owner) == public.ALLOWANCE[public.CHECK]
    with psycopg.connect(database) as conn:
        (counted,) = conn.execute("SELECT count(*) FROM visitor_uses").fetchone()
    assert counted == 0  # nothing that the copy's owner does is counted
    assert limits.take(public.AI, owner) and not limits.take(public.AI, owner)  # Gemini's holds


def test_the_copys_owner_signs_in_with_github_and_checks_with_no_count(site, monkeypatch) -> None:  # noqa: ANN001, F811
    """On /owner the copy's owner signs in with GitHub; the account named in the settings gets a
    pass for its browser, and its checks are then not counted, until it signs out. Any other
    account gets nothing (30 October 2026)."""
    from test_github_app import StandInGitHub

    client, _, _, database = site
    monkeypatch.setitem(public.ALLOWANCE, public.CHECK, 1)
    copy = owners_copy(client, StandInGitHub(login="mohamedyaakoubi"))
    asked = {"repo": REPO, "event": checkable(database)}
    one = {"CF-Connecting-IP": "203.0.113.5", **HX}
    assert copy.get("/check", params=asked, headers=one).status_code == 200
    assert copy.get("/check", params=asked, headers=one).status_code == 429  # the allowance is used
    assert "Sign in with GitHub" in copy.get("/owner").text
    start = copy.get("/owner/start", follow_redirects=False)
    assert start.status_code == 303 and start.headers["location"].startswith(
        "https://github.com/login/oauth/authorize?")  # fmt: skip
    state = parse_qs(start.headers["location"].split("?", 1)[1])["state"][0]
    back = copy.get("/github/callback", params={"code": "the-code", "state": state},
                    follow_redirects=False)  # fmt: skip
    assert back.status_code == 303 and back.headers["location"] == "/owner"
    cookie = back.headers["set-cookie"].lower()
    assert "hm-owner=" in cookie and "httponly" in cookie and "path=/" in cookie
    assert "ghu_standin" not in cookie
    page = copy.get("/owner").text
    signed = "signed in as the copy's owner, with the GitHub account <b>mohamedyaakoubi</b>"
    assert signed in page  # the page's own words; a message from the code is escaped (&#39;)
    assert INSIGHTS not in copy.get("/").text  # the visits of the copy's owner are not counted
    for _ in range(3):  # not counted
        assert copy.get("/check", params=asked, headers=one).status_code == 200
    assert copy.get("/owner/sign-out", follow_redirects=False).status_code == 303
    assert copy.get("/check", params=asked, headers=one).status_code == 429  # counted again
    assert INSIGHTS in copy.get("/").text
    stranger = owners_copy(client, StandInGitHub(login="someone-else"))
    state = parse_qs(stranger.get("/owner/start", follow_redirects=False)
                     .headers["location"].split("?", 1)[1])["state"][0]  # fmt: skip
    refused = stranger.get("/github/callback", params={"code": "the-code", "state": state},
                           follow_redirects=False)  # fmt: skip
    assert refused.status_code == 403 and "is not the copy&#39;s owner" in refused.text
    assert "hm-owner=" not in refused.headers.get("set-cookie", "")
    plain = public_site(client)  # a copy without the settings offers no sign-in
    assert "has no sign-in for its owner" in plain.get("/owner").text


def test_the_copy_notes_what_its_visitors_do_for_its_owner_only(site) -> None:  # noqa: ANN001, F811
    """Each action of a visitor is noted with Vercel's place of its address, the site it came
    from and its browser; the copy's owner reads them on /owner/visits, with the public budget,
    and is not noted; anybody else is sent to the sign-in (design 12.5, S9, 1 November 2026)."""
    from test_github_app import StandInGitHub

    client, _, ids, database = site
    copy = owners_copy(client, StandInGitHub(login="mohamedyaakoubi"))
    where = {
        "CF-Connecting-IP": "203.0.113.9",
        "x-vercel-ip-country": "TN",
        "x-vercel-ip-country-region": "11",
        "x-vercel-ip-city": "Tunis",
        "referer": "https://4hacks.io/fss/projects?page=2",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36",
    }
    copy.get("/", params={"idea": "pay street"}, headers=where)
    copy.get("/", params={"idea": "pay street vendors"}, headers=where)  # typed on: one search
    copy.get(f"/project/{ids['Pebble Pay']}/panel", headers=where)
    copy.get("/static/style.css", headers=where)  # a file: no action
    assert copy.get("/owner/visits", follow_redirects=False).headers["location"] == "/owner"
    with psycopg.connect(database) as conn:
        (noted,) = conn.execute("SELECT count(*) FROM visit_actions").fetchone()
    assert noted == 3
    start = copy.get("/owner/start", follow_redirects=False)
    state = parse_qs(start.headers["location"].split("?", 1)[1])["state"][0]
    copy.get("/github/callback", params={"code": "the-code", "state": state},
             follow_redirects=False)  # fmt: skip
    page = copy.get("/owner/visits").text
    assert "Tunis, TN" in page and "4hacks.io/fss/projects" in page and "Chrome on Windows" in page
    assert "searched “pay street vendors”" in page and "searched “pay street”" not in page
    assert "opened the card of Pebble Pay" in page
    assert "0.00 of 30.00 dollars spent" in page
    copy.get("/", params={"idea": "a search of the copy's owner"}, headers=where)
    with psycopg.connect(database) as conn:
        (after,) = conn.execute("SELECT count(*) FROM visit_actions").fetchone()
    assert after == noted  # the copy's owner is not noted
    assert (
        "This copy notes which pages and actions its visitors use"
        in public_site(client).get("/").text
    )
