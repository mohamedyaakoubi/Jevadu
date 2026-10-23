"""What the parser reads on a project page of ETHGlobal. The pages are invented."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from fakes import (
    EVENT,
    HEDERA_ID,
    OTHER_ID,
    PLANTED_SCORES,
    PROJECT_PAGE,
    project_page,
    sample,
    won,
)
from hackathon_memory.parse.blocks import ITEM, PARAGRAPH, TITLE, Block
from hackathon_memory.parse.ethglobal_page import (
    DESCRIPTION,
    HOW_ITS_MADE,
    PARSER_VERSION,
    PageShapeChanged,
    prize_lines,
    prize_sponsors,
    read_project_page,
    took_a_hedera_prize,
)
from hackathon_memory.parse.hedera_ids import ACCOUNT, TOKEN, TOPIC
from hackathon_memory.parse.people import HIDDEN_ADDRESS, HIDDEN_HANDLE, HIDDEN_LINK
from hackathon_memory.parse.project import (
    CODE_LINK,
    DEMO_LINK,
    HEDERA_PRIZE,
    NO_PRIZE,
    OTHER_PRIZE,
    EventRef,
    Link,
    Prize,
)

# --------------------------------------------------------------------- the Hedera prize


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("project_winner.html", True),
        ("project_other_sponsor.html", False),  # won another sponsor's prize, talks about Hedera
        ("project_no_prize.html", False),
    ],
)
def test_a_page_is_a_hedera_winner_only_if_its_prize_block_says_so(
    name: str, expected: bool
) -> None:
    assert took_a_hedera_prize(sample(name)) is expected


def block(line: str) -> bytes:
    return f"<h3>Winner of</h3><div><div><h4>{line}</h4></div></div>".encode()


def test_the_prize_line_is_read_whatever_the_case() -> None:
    assert took_a_hedera_prize(block("HEDERA - Best use"))
    assert not took_a_hedera_prize(block("Hederaphile - Best use"))
    assert not took_a_hedera_prize(b"<h3>Finalist</h3><div><h4>Hedera - Best use</h4></div>")


@pytest.mark.parametrize("dash", ["-", "‐", "‑", "‒", "–", "—", "―"])
def test_the_prize_line_is_read_whatever_the_dash(dash: str) -> None:
    assert took_a_hedera_prize(block(f"Hedera {dash} Best use"))
    assert prize_sponsors(block(f"Acme-Labs {dash} First")) == ["Acme-Labs"]


def test_the_sponsors_of_a_page_are_the_parts_before_the_dash() -> None:
    assert prize_sponsors(sample("project_winner.html")) == ["Hedera", "Other Sponsor"]
    assert prize_sponsors(sample("project_no_prize.html")) == []
    twice = "<h3>Winner of</h3><div><h4>Acme-Labs - First</h4><h4>Acme-Labs - Second</h4></div>"
    assert prize_sponsors(twice.encode()) == ["Acme-Labs"]


# --------------------------------------------------------------------- the whole page

HEDERA_FIRST = won()  # a tier: the page shows the prize and the place
OTHER_TRACK = won("Other Sponsor", OTHER_ID, track="Best use of Other Sponsor", kind="track")


def test_the_facts_of_a_page_are_read_from_it() -> None:
    page = read_project_page(project_page(), PROJECT_PAGE)
    assert page.site == "ethglobal.com"
    assert page.page == PROJECT_PAGE
    assert page.site_key == "pebble-pay-x1y2z"
    assert page.name == "Pebble Pay"
    assert page.short_line == "Pay a street vendor with a coin on Hedera."
    assert page.event == EventRef(
        "ethglobal.com", "sample-event", EVENT, "2026-03-06T16:00:00.000Z"
    )
    assert page.links == (
        Link(DEMO_LINK, "https://demo.example.test/pebble-pay", "Live Demo"),
        Link(CODE_LINK, "https://github.com/sample-org/pebble-pay", "Source Code"),
    )
    assert page.link(CODE_LINK) == "https://github.com/sample-org/pebble-pay"
    assert page.has_video
    assert page.parser == PARSER_VERSION


def test_a_name_with_signs_of_the_markup_is_read_as_it_is_shown() -> None:
    html = project_page(name="Pebble & <Pay>", short_line='A "coin" for < 1 cent & more.')
    page = read_project_page(html, PROJECT_PAGE)
    assert page.name == "Pebble & <Pay>"
    assert page.short_line == 'A "coin" for < 1 cent & more.'


def test_a_page_without_a_demo_a_code_link_or_a_video_is_read_too() -> None:
    page = read_project_page(project_page(code=None, demo=None, video=False), PROJECT_PAGE)
    assert page.links == ()
    assert page.link(CODE_LINK) is None
    assert not page.has_video


def test_a_link_of_the_header_with_other_words_is_kept_as_another_link() -> None:
    html = project_page().replace(b">Live Demo<", b">Watch the film<")
    page = read_project_page(html, PROJECT_PAGE)
    assert [(link.kind, link.label) for link in page.links] == [
        ("other", "Watch the film"),
        (CODE_LINK, "Source Code"),
    ]


def test_a_link_inside_the_site_is_not_a_link_of_the_project() -> None:
    html = project_page().replace(b"<header>", b'<header><a href="/showcase">Back</a>')
    assert len(read_project_page(html, PROJECT_PAGE).links) == 2


# --------------------------------------------------------------------- the three prize states


def test_a_project_with_a_hedera_prize() -> None:
    page = read_project_page(project_page(prizes=[HEDERA_FIRST, OTHER_TRACK]), PROJECT_PAGE)
    assert page.prize_state == HEDERA_PRIZE
    assert page.prizes == (
        Prize(
            sponsor="Hedera",
            sponsor_id=HEDERA_ID,
            track="AI, Agents & Hedera Services",
            award="1st place",
            kind="tier",
            pool=False,
            line="Hedera - AI, Agents & Hedera Services 1st place",
        ),
        Prize(
            sponsor="Other Sponsor",
            sponsor_id=OTHER_ID,
            track="Best use of Other Sponsor",
            award="Best use of Other Sponsor",
            kind="track",
            pool=False,
            line="Other Sponsor - Best use of Other Sponsor",
        ),
    )


def test_a_project_with_a_prize_of_another_sponsor_only() -> None:
    # It talks about Hedera in its texts, and that changes nothing.
    html = project_page(prizes=[OTHER_TRACK], made="<p>We use Hedera for the payments.</p>")
    assert read_project_page(html, PROJECT_PAGE).prize_state == OTHER_PRIZE


def test_a_project_with_no_prize() -> None:
    page = read_project_page(project_page(), PROJECT_PAGE)
    assert page.prize_state == NO_PRIZE
    assert page.prizes == ()


def test_a_prize_shared_by_many_and_a_finalist_are_read_with_their_kind() -> None:
    pool = won(track="Hedera Pool Prize", kind="pool", pool=True)
    finalist = won("ETHGlobal", "eth03", track="Finalists", award="Finalist", kind="finalist")
    page = read_project_page(project_page(prizes=[pool, finalist]), PROJECT_PAGE)
    assert [(p.kind, p.pool, p.line) for p in page.prizes] == [
        ("pool", True, "Hedera - Hedera Pool Prize"),
        ("finalist", False, "ETHGlobal - Finalist"),
    ]
    assert page.prize_state == HEDERA_PRIZE


def test_the_page_reader_and_the_collector_agree_about_a_hedera_prize() -> None:
    for prizes in ([], [OTHER_TRACK], [HEDERA_FIRST], [OTHER_TRACK, HEDERA_FIRST]):
        html = project_page(prizes=prizes)
        state = read_project_page(html, PROJECT_PAGE).prize_state
        assert (state == HEDERA_PRIZE) is took_a_hedera_prize(html)
        assert len(prize_lines(html)) == len(prizes)


# --------------------------------------------------------------------- the two texts

DESCRIPTION_HTML = (
    "<p>Pebble<strong>Pay</strong> lets a vendor take a coin.</p>"
    "<h3>Problem</h3><p>Small shops lose a day to count cash.</p>"
    "<ul><li>no change</li><li>no receipt</li></ul>"
)
MADE_HTML = "<p>A small web page asks the buyer to sign.</p><h1>The stack</h1><p>Plain code.</p>"


def test_the_two_texts_are_copied_block_by_block() -> None:
    page = read_project_page(
        project_page(description=DESCRIPTION_HTML, made=MADE_HTML), PROJECT_PAGE
    )
    description = page.section(DESCRIPTION)
    made = page.section(HOW_ITS_MADE)
    assert description is not None and made is not None
    assert description.title == "Project Description"
    assert made.title == "How it's Made"
    assert description.blocks == (
        Block(PARAGRAPH, "PebblePay lets a vendor take a coin."),
        Block(TITLE, "Problem", 3),
        Block(PARAGRAPH, "Small shops lose a day to count cash."),
        Block(ITEM, "no change", 1),
        Block(ITEM, "no receipt", 1),
    )
    assert made.text == "A small web page asks the buyer to sign.\nThe stack\nPlain code."


def test_a_second_name_title_inside_a_text_does_not_change_the_name() -> None:
    page = read_project_page(project_page(made=MADE_HTML), PROJECT_PAGE)
    assert page.name == "Pebble Pay"


def test_a_title_of_the_team_with_the_words_of_the_site_is_not_a_part_of_the_page() -> None:
    # A team wrote "How it's Made" as a title inside its description.
    inside = "<p>First.</p><h3>How it's Made</h3><p>Still the description.</p>"
    page = read_project_page(project_page(description=inside), PROJECT_PAGE)
    description = page.section(DESCRIPTION)
    made = page.section(HOW_ITS_MADE)
    assert description is not None and made is not None
    assert description.text == "First.\nHow it's Made\nStill the description."
    assert made.text == "A small web page asks the buyer to sign."


def test_an_empty_text_is_a_part_with_no_block() -> None:
    page = read_project_page(project_page(made=""), PROJECT_PAGE)
    made = page.section(HOW_ITS_MADE)
    assert made is not None and made.blocks == () and made.text == ""


# --------------------------------------------------------------------- the Hedera ids


def test_the_ids_of_the_two_texts_and_of_their_links_are_found() -> None:
    html = project_page(
        description="<p>The coin is the token 0.0.2345671 on the test network.</p>",
        made=(
            "<p>Each sale goes to the topic 0.0.3456781. The version of the page is 0.0.1.</p>"
            '<p>The payer is <a href="https://hashscan.io/mainnet/account/0.0.4567891">here</a>.'
            "</p>"
        ),
    )
    page = read_project_page(html, PROJECT_PAGE)
    assert [(i.entity_id, i.network, i.said_kind) for i in page.hedera_ids] == [
        ("0.0.2345671", "testnet", TOKEN),
        ("0.0.3456781", None, TOPIC),
        ("0.0.4567891", "mainnet", ACCOUNT),
    ]


def test_a_demo_link_to_hashscan_gives_an_id() -> None:
    html = project_page(demo="https://hashscan.io/testnet/topic/0.0.3456781")
    page = read_project_page(html, PROJECT_PAGE)
    assert [(i.entity_id, i.network, i.said_kind) for i in page.hedera_ids] == [
        ("0.0.3456781", "testnet", TOPIC)
    ]


def test_a_page_with_no_id_gives_none() -> None:
    assert read_project_page(project_page(), PROJECT_PAGE).hedera_ids == ()


# --------------------------------------------------------------------- what is never read


def test_the_scores_of_the_site_never_come_out_of_the_parser() -> None:
    html = project_page(prizes=[HEDERA_FIRST], description=DESCRIPTION_HTML, made=MADE_HTML)
    assert all(str(value).encode() in html for value in PLANTED_SCORES.values())  # they are there
    everything = json.dumps(asdict(read_project_page(html, PROJECT_PAGE)))
    for key, value in PLANTED_SCORES.items():
        assert key not in everything
        assert str(value) not in everything


def test_the_pictures_and_the_film_of_the_site_are_not_taken() -> None:
    everything = json.dumps(asdict(read_project_page(project_page(), PROJECT_PAGE)))
    assert "cdn.example.test" not in everything
    assert "stream.example.test" not in everything


# --------------------------------------------------------------------- a page of another shape


def changed(html: bytes, old: str, new: str) -> bytes:
    assert html.count(old.encode()) == 1, f"{old!r} must stand once in the invented page"
    return html.replace(old.encode(), new.encode())


@pytest.mark.parametrize(
    ("html", "said"),
    [
        (project_page(data_changes={"slug": "another-project"}), "holds the project"),
        (
            changed(project_page(), "<h1>Pebble Pay</h1>", "<h1>Pebble Play</h1>"),
            "name in the header",
        ),
        (changed(project_page(), "<header><h1>", "<div><h1>"), "no header"),
        (project_page(data_changes={"tagline": "Another short line."}), "short line"),
        (
            changed(project_page(), '<p class="lg:text-lg text-black-500">', "<span>"),
            "not followed by a short line",
        ),
        (changed(project_page(), "<h3>Created At</h3>", "<h3>Made At</h3>"), "Created At"),
        (changed(project_page(), 'href="/events/sample-event"', 'href="/prizes/x"'), "event"),
        (project_page(data_changes={"event": {"slug": "another-event"}}), "event"),
        (project_page(prizes=[won()], data_changes={"prizes": []}), "Winner of"),
        (project_page(data_changes={"prizes": [won()]}), "Winner of"),
        (
            project_page(prizes=[won()], data_changes={"prizes": [won("Other Sponsor", OTHER_ID)]}),
            "does not start with the sponsor",
        ),
        (changed(project_page(), "<h3>Project Description</h3>", "<h3>About</h3>"), "titles"),
        (
            changed(project_page(), "<h3>How it's Made</h3>", "<h3>Project Description</h3>"),
            "titles",
        ),
    ],
)
def test_a_page_of_another_shape_is_refused_and_nothing_is_guessed(html: bytes, said: str) -> None:
    with pytest.raises(PageShapeChanged, match=said):
        read_project_page(html, PROJECT_PAGE)


def test_a_page_read_under_the_address_of_another_project_is_refused() -> None:
    with pytest.raises(PageShapeChanged, match="holds the project"):
        read_project_page(project_page(), "https://ethglobal.com/showcase/quartz-notes-q3w4e")


def test_the_same_project_twice_in_the_data_is_fine_when_both_say_the_same() -> None:
    html = project_page()
    script = html[html.index(b"<script>self.__next_f.push([1,") : html.index(b"</body>")]
    page = read_project_page(html.replace(b"</body>", script + b"</body>"), PROJECT_PAGE)
    assert page.name == "Pebble Pay"


# --------------------------------------------------------------------- people are hidden


def test_words_about_people_in_the_short_line_and_the_texts_are_hidden() -> None:
    html = project_page(
        short_line="A coin for vendors, by @quill_invented.",
        description=(
            "<p>Built by <strong>@quill_invented</strong>. Write to quill@example.test.</p>"
        ),
        made=(
            "<p>We use <code>@sample-scope/sdk</code>. News on https://x.com/quill_invented.</p>"
            "<pre><code>@Override\nvoid pay() {}</code></pre>"
        ),
    )
    page = read_project_page(html, PROJECT_PAGE)
    description = page.section(DESCRIPTION)
    made = page.section(HOW_ITS_MADE)
    assert description is not None and made is not None
    assert page.short_line == f"A coin for vendors, by {HIDDEN_HANDLE}."
    assert description.text == f"Built by {HIDDEN_HANDLE}. Write to {HIDDEN_ADDRESS}."
    # Code keeps its @ signs: there they belong to the language.
    assert made.text == (
        f"We use @sample-scope/sdk. News on {HIDDEN_LINK}.\n@Override\nvoid pay() {{}}"
    )
    assert page.people_words_hidden == 4
    assert "quill" not in json.dumps(asdict(page))  # in no field at all


def test_a_page_with_no_word_about_people_hides_nothing() -> None:
    assert read_project_page(project_page(), PROJECT_PAGE).people_words_hidden == 0


def test_an_id_next_to_a_hidden_word_is_still_found_and_its_words_name_nobody() -> None:
    html = project_page(made="<p>Ask @quill about the topic 0.0.3456781 on testnet.</p>")
    page = read_project_page(html, PROJECT_PAGE)
    assert [(i.entity_id, i.network, i.said_kind) for i in page.hedera_ids] == [
        ("0.0.3456781", "testnet", TOPIC)
    ]
    assert "quill" not in page.hedera_ids[0].words_around


def test_a_demo_link_to_a_profile_site_is_kept_without_its_address() -> None:
    # The tool cannot tell a bot of the project from a person, so the address is not kept.
    page = read_project_page(project_page(demo="https://t.me/invented_helper_bot"), PROJECT_PAGE)
    assert page.links == (
        Link(DEMO_LINK, None, "Live Demo", hidden_on="t.me"),
        Link(CODE_LINK, "https://github.com/sample-org/pebble-pay", "Source Code"),
    )
    assert page.link(DEMO_LINK) is None
    assert page.link(CODE_LINK) == "https://github.com/sample-org/pebble-pay"
    assert page.people_words_hidden == 1
    assert "invented_helper_bot" not in json.dumps(asdict(page))  # in no field at all


def test_the_address_of_a_kind_is_the_first_one_that_is_not_hidden() -> None:
    html = project_page(demo="https://x.com/quill_invented/status/1").replace(
        b"</header>", b'<a href="https://demo.example.test/second">Live Demo</a></header>'
    )
    page = read_project_page(html, PROJECT_PAGE)
    assert [(link.kind, link.url, link.hidden_on) for link in page.links] == [
        (DEMO_LINK, None, "x.com"),
        (CODE_LINK, "https://github.com/sample-org/pebble-pay", None),
        (DEMO_LINK, "https://demo.example.test/second", None),
    ]
    assert page.link(DEMO_LINK) == "https://demo.example.test/second"


def test_a_handle_in_the_words_of_a_header_link_is_hidden() -> None:
    html = project_page().replace(b">Live Demo<", b">Demo by @quill_invented<")
    page = read_project_page(html, PROJECT_PAGE)
    assert page.links[0] == Link(
        "other", "https://demo.example.test/pebble-pay", f"Demo by {HIDDEN_HANDLE}"
    )
    assert page.people_words_hidden == 1
    assert "quill" not in json.dumps(asdict(page))


def test_no_id_is_taken_from_a_link_whose_address_is_hidden() -> None:
    page = read_project_page(
        project_page(demo="https://t.me/invented_helper_bot?start=0.0.3456781"), PROJECT_PAGE
    )
    assert page.hedera_ids == ()


def test_a_demo_link_to_an_account_on_github_is_kept_without_its_address() -> None:
    page = read_project_page(project_page(demo="https://github.com/quill-invented"), PROJECT_PAGE)
    assert page.links == (
        Link(DEMO_LINK, None, "Live Demo", hidden_on="github.com"),
        Link(CODE_LINK, "https://github.com/sample-org/pebble-pay", "Source Code"),  # kept
    )
    assert page.people_words_hidden == 1
    assert "quill" not in json.dumps(asdict(page))
