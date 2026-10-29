"""The public copy of the website (web/public.py, design 12.5): no page indexed, the AI and the
register off until turned on, and a count a day for each visitor. Everything is invented."""

from __future__ import annotations

import pytest
from pydantic import SecretStr
from test_web import REPO, checkable, site  # noqa: F401  (the fixture of the website's tests)

from hackathon_memory.finops import meter
from hackathon_memory.web import public
from searchfakes import google

SALT = "s" * 40


def public_site(client):  # noqa: ANN001, ANN201
    return client.make(app_options={"public": True}, public_salt=SecretStr(SALT))


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


def test_each_visitor_has_a_count_of_checks_a_day(site, monkeypatch) -> None:  # noqa: ANN001, F811
    client, _, _, database = site
    monkeypatch.setitem(public.PER_DAY, public.CHECK, 2)
    event = checkable(database)
    open_copy = public_site(client)
    asked = {"repo": REPO, "event": event}
    one = {"CF-Connecting-IP": "203.0.113.5", "HX-Request": "true"}
    for _ in range(2):
        assert open_copy.get("/check", params=asked, headers=one).status_code == 200
    third = open_copy.get("/check", params=asked, headers=one)
    assert third.status_code == 429 and "allows 2 checks a day for each visitor" in third.text
    other = {"CF-Connecting-IP": "198.51.100.7", "HX-Request": "true"}
    assert open_copy.get("/check", params=asked, headers=other).status_code == 200
    assert client.get("/check", params=asked, headers=one).status_code == 200  # the laptop's site
    switches, counts = public.today(database)
    assert switches == {public.AI: False, public.REGISTER: False}
    assert counts[public.CHECK] == (2, 3)  # two visitors, three checks counted


def test_registering_is_paused_on_the_public_copy_until_it_is_turned_on(site) -> None:  # noqa: ANN001, F811
    client, _, _, database = site
    open_copy = public_site(client)
    form = {"repo": REPO, "event": checkable(database), "starts": "", "ends": ""}
    paused = open_copy.post("/register", data=form, headers={"HX-Request": "true"})
    assert paused.status_code == 503 and "registering on Hedera is paused" in paused.text
    public.turn(database, public.REGISTER, True)
    opened = open_copy.post("/register", data=form, headers={"HX-Request": "true"})
    assert "registering on Hedera is paused" not in opened.text  # on to the usual rules
    assert "Check the repository first" in opened.text and client.writes.written == []


def test_a_visitor_is_a_salted_hash_of_the_address_that_cloudflare_gives() -> None:
    key = public.visitor_of({"cf-connecting-ip": "203.0.113.5"}, "127.0.0.1", SALT)
    assert len(key) == 64 and "203" not in key
    assert key == public.visitor_of({}, "203.0.113.5", SALT)  # the peer, when no header
    assert key != public.visitor_of({"cf-connecting-ip": "203.0.113.5"}, None, "other salt")
    home = public.visitor_of({"cf-connecting-ip": "2001:db8:1:2::5"}, None, SALT)
    assert home == public.visitor_of({"cf-connecting-ip": "2001:db8:1:2:ffff::9"}, None, SALT)
    assert home != public.visitor_of({"cf-connecting-ip": "2001:db8:1:3::5"}, None, SALT)
    with pytest.raises(ValueError):
        public.turn("unused", "everything", True)
