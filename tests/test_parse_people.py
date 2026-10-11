"""Words about people are hidden in a copied text. Every name here is invented."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup, Tag

from hackathon_memory.parse.people import (
    HIDDEN_ADDRESS,
    HIDDEN_HANDLE,
    HIDDEN_LINK,
    PROFILE_SITES,
    hide_in_box,
    hide_in_code,
    hide_in_text,
    profile_site,
)


def box(html: str) -> Tag:
    found = BeautifulSoup(f'<div id="box">{html}</div>', "lxml").find(id="box")
    assert isinstance(found, Tag)
    return found


# --------------------------------------------------------------------- handles


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("Built by @quill_invented in a weekend.", f"Built by {HIDDEN_HANDLE} in a weekend."),
        ("Ask @quill.", f"Ask {HIDDEN_HANDLE}."),  # the full stop of the sentence stays
        ("(@quill-invented)", f"({HIDDEN_HANDLE})"),
        ("@quill.eth and @Quill99", f"{HIDDEN_HANDLE} and {HIDDEN_HANDLE}"),
        (
            "Thanks to @quill, @reed and @fern!",
            f"Thanks to {HIDDEN_HANDLE}, {HIDDEN_HANDLE} and {HIDDEN_HANDLE}!",
        ),
    ],
)
def test_a_word_that_starts_with_an_at_sign_is_hidden(text: str, shown: str) -> None:
    hidden, count = hide_in_text(text)
    assert hidden == shown
    assert count == shown.count(HIDDEN_HANDLE)


@pytest.mark.parametrize(
    "text",
    [
        "We use the package @sample-scope/sdk for the transfers.",
        "Install @sample-scope/sdk@2.1.0 and @other/tool.",  # a version after a package
        "The price is 5 @ 10 units.",  # an @ on its own
        "Send it to pool@",  # nothing after the @
        "The path is src/@types/index.d.ts in the code.",
        "No sign of that kind here.",
    ],
)
def test_the_name_of_a_package_and_a_lone_at_sign_are_not_handles(text: str) -> None:
    assert hide_in_text(text) == (text, 0)


def test_a_pattern_cannot_give_back_letters_to_turn_a_package_into_a_handle() -> None:
    # A lesson of this project: "not followed by a slash" must not be reached by stepping back.
    text = "@abcdefghijklmnopqrstuvwxyz/package"
    assert hide_in_text(text) == (text, 0)


# --------------------------------------------------------------------- addresses and links


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("Write to quill.invented@mail.example.test today.", f"Write to {HIDDEN_ADDRESS} today."),
        ("Contact: someone+tag@example.test", f"Contact: {HIDDEN_ADDRESS}"),
        ("(first@example.test, second@example.test)", f"({HIDDEN_ADDRESS}, {HIDDEN_ADDRESS})"),
    ],
)
def test_an_email_address_is_hidden_whole(text: str, shown: str) -> None:
    hidden, count = hide_in_text(text)
    assert hidden == shown
    assert count == shown.count(HIDDEN_ADDRESS)
    assert "@" not in hidden  # and it is not half hidden as a handle


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("Follow https://x.com/quill_invented for news.", f"Follow {HIDDEN_LINK} for news."),
        ("Our group: t.me/quill_invented.", f"Our group: {HIDDEN_LINK}."),
        ("See https://www.linkedin.com/in/quill-invented/", f"See {HIDDEN_LINK}"),
        ("twitter.com/quill and instagram.com/quill", f"{HIDDEN_LINK} and {HIDDEN_LINK}"),
        ("(https://warpcast.com/quill)", f"({HIDDEN_LINK})"),
        # The site behind another first part is the same site.
        ("See https://uk.linkedin.com/in/quill-invented.", f"See {HIDDEN_LINK}."),
        ("m.facebook.com/quill and mobile.twitter.com/quill", f"{HIDDEN_LINK} and {HIDDEN_LINK}"),
    ],
)
def test_a_link_to_a_profile_is_hidden(text: str, shown: str) -> None:
    hidden, count = hide_in_text(text)
    assert hidden == shown
    assert count == shown.count(HIDDEN_LINK)


@pytest.mark.parametrize(
    "text",
    [
        "The code is at https://github.com/sample-org/pebble-pay.",
        "Watch https://youtu.be/abc123 and https://www.youtube.com/watch?v=abc123.",
        "Files are on box.com/pebble and on dropbox.com/pebble.",  # not x.com
        "The log: https://hashscan.io/testnet/topic/0.0.3456789",
        "Docs at https://docs.example.test/x.com/page",  # the site is not x.com
        "Files at https://files.dropbox.com/pebble and max.com/pebble.",  # nor are these
        "We post on x.com and on t.me every week.",  # the name of a site names nobody
    ],
)
def test_a_link_to_code_to_a_video_or_to_another_site_stays(text: str) -> None:
    assert hide_in_text(text) == (text, 0)


def test_hiding_twice_changes_nothing_more() -> None:
    once, count = hide_in_text("By @quill, quill@example.test, x.com/quill.")
    assert count == 3
    assert hide_in_text(once) == (once, 0)


# --------------------------------------------------------------------- in a part of a page


def test_the_texts_of_a_box_are_hidden_and_in_its_code_only_an_address() -> None:
    page = box(
        "<p>Built by <strong>@quill</strong> and @reed.</p>"
        "<p>We use <code>@sample-scope/sdk</code> and the mark <code>@Override</code>.</p>"
        "<pre><code>@media (max-width: 600px) { }\nmail = 'someone@example.test'</code></pre>"
        "<ul><li>Write to quill@example.test</li></ul>"
        "<script>var handle = '@hidden_from_nobody';</script>"
    )
    assert hide_in_box(page) == 4
    text = page.get_text(" ")
    assert f"Built by {HIDDEN_HANDLE} and {HIDDEN_HANDLE}." in " ".join(text.split())
    assert f"Write to {HIDDEN_ADDRESS}" in text
    # Inside code an @ belongs to the language, and only an email address is hidden.
    assert "@sample-scope/sdk" in text and "@Override" in text
    assert "@media (max-width: 600px)" in text
    assert f"mail = '{HIDDEN_ADDRESS}'" in text
    assert "@hidden_from_nobody" in str(page)  # a script is not text of the page
    assert "quill" not in text and "reed" not in text  # no name of a person is left


@pytest.mark.parametrize(
    ("code", "shown"),
    [
        ("git config user.email quill@example.test", f"git config user.email {HIDDEN_ADDRESS}"),
        ("ADMIN = 'quill.invented@mail.example.test'", f"ADMIN = '{HIDDEN_ADDRESS}'"),
    ],
)
def test_in_code_an_email_address_is_hidden(code: str, shown: str) -> None:
    assert hide_in_code(code) == (shown, 1)


@pytest.mark.parametrize(
    "code",
    [
        "@media (max-width: 600px) { }",
        "@Override public void pay() {}",
        "import { Client } from '@sample-scope/sdk'",
        "npm install @sample-scope/sdk@2.1.0",
        '@app.route("/pay")',
        'const quill = "@quill_invented"  // a handle in code is code',
        "see x.com/quill_invented",  # a link in code too
    ],
)
def test_in_code_nothing_but_an_address_is_touched(code: str) -> None:
    assert hide_in_code(code) == (code, 0)


def test_a_box_with_no_word_about_people_is_not_changed() -> None:
    page = box("<p>Pebble Pay lets a vendor take a coin.</p><!-- a note with @someone -->")
    before = str(page)
    assert hide_in_box(page) == 0
    assert str(page) == before


# --------------------------------------------------------------------- a link on its own


@pytest.mark.parametrize(
    ("url", "site"),
    [
        ("https://t.me/invented_helper_bot", "t.me"),
        ("https://T.ME/quill_invented", "t.me"),
        ("http://www.x.com/quill_invented/status/123", "x.com"),
        ("https://uk.linkedin.com/in/quill-invented/", "linkedin.com"),
        ("https://x.com/?user=quill", "x.com"),
        ("  https://mobile.twitter.com/quill  ", "twitter.com"),
    ],
)
def test_the_address_of_a_link_to_a_profile_site_names_that_site(url: str, site: str) -> None:
    assert profile_site(url) == site


@pytest.mark.parametrize(
    "url",
    [
        "https://demo.example.test/pebble-pay",
        "https://github.com/sample-org/pebble-pay",
        "https://box.com/pebble",  # not x.com
        "https://docs.example.test/x.com/page",  # the site is not x.com
        "https://t.me/",  # the site alone names nobody
        "https://x.com",
        "https://[not-an-address",  # no browser could open it
        "",
    ],
)
def test_the_address_of_another_link_names_no_profile_site(url: str) -> None:
    assert profile_site(url) is None


def test_a_text_and_a_link_on_its_own_get_the_same_answer() -> None:
    # One list of sites decides both.
    for site in PROFILE_SITES:
        assert profile_site(f"https://{site}/quill_invented") == site
        assert hide_in_text(f"see {site}/quill_invented") == (f"see {HIDDEN_LINK}", 1)


# --------------------------------------------------------------------- an account on GitHub


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("Made by https://github.com/quill-invented.", f"Made by {HIDDEN_LINK}."),
        ("See github.com/quill-invented/ for more", f"See {HIDDEN_LINK} for more"),
        ("(www.GitHub.com/quill-invented?tab=repositories)", f"({HIDDEN_LINK})"),
    ],
)
def test_a_link_to_an_account_on_github_is_hidden(text: str, shown: str) -> None:
    assert hide_in_text(text) == (shown, 1)


@pytest.mark.parametrize(
    "text",
    [
        "The code is at https://github.com/sample-org/pebble-pay.",
        "Read github.com/sample-org/pebble-pay/blob/main/README.md, please.",
        "We host it on github.com and nowhere else.",  # the site alone
        "A fork lives on gist.github.com/sample-org and on notgithub.com/sample-org.",
        "The site sample-org.github.io/pebble-pay shows it.",
    ],
)
def test_a_link_to_a_repository_stays(text: str) -> None:
    assert hide_in_text(text) == (text, 0)


@pytest.mark.parametrize(
    ("url", "site"),
    [
        ("https://github.com/quill-invented", "github.com"),
        ("https://www.github.com/quill-invented/", "github.com"),
        ("https://github.com/quill-invented?tab=repositories", "github.com"),
        ("https://github.com/sample-org/pebble-pay", None),
        ("https://github.com/sample-org/pebble-pay/tree/main", None),
        ("https://github.com/", None),
        ("https://sample-org.github.io/pebble-pay", None),
    ],
)
def test_the_address_of_an_account_on_github_is_a_profile_and_a_repository_is_not(
    url: str, site: str | None
) -> None:
    assert profile_site(url) == site
