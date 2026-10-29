"""The public copy of the website (web/public.py, design 12.5): no page indexed, the AI and the
register off until turned on, a budget of its own, and an allowance for each visitor, one time
only. Everything is invented."""

from __future__ import annotations

import json
import re

import psycopg
import pytest
from pydantic import SecretStr
from test_web import (  # noqa: F401  (the fixtures of the website's tests)
    REPO,
    checkable,
    chromium,
    compare_answer,
    order_of,
    served,
    site,
)

from hackathon_memory.finops import meter
from hackathon_memory.finops.meter import Tags
from hackathon_memory.settings import Settings
from hackathon_memory.web import public, switch
from searchfakes import google

SALT = "s" * 40
HX = {"HX-Request": "true"}


def public_site(client, **changes):  # noqa: ANN001, ANN003, ANN201
    return client.make(app_options={"public": True}, public_salt=SecretStr(SALT), **changes)


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
