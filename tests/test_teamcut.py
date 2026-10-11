"""The team part never reaches the disk (design 5.3 and 5.7).

The test pages are invented. The names in them belong to nobody.
"""

from __future__ import annotations

import json

import pytest

from fakes import sample
from hackathon_memory.collect.teamcut import (
    CutFailed,
    CutPolicy,
    CutRule,
    TeamShapeChanged,
    TeamTextRemains,
    cut_team,
)

POLICY = CutPolicy(rules=(CutRule("#team"),), json_blocklist=frozenset({"members"}))
NAMES = ["Quillfeather", "Ledgerwood", "quillfeather", "ledgerwood", "avatars"]


def cut(html: str | bytes, policy: CutPolicy = POLICY):
    body = html.encode("utf-8") if isinstance(html, str) else html
    return cut_team(body, policy)


def test_the_team_block_goes_and_the_project_text_stays() -> None:
    output, _ = cut(sample("project_zed_widget.html"))
    text = output.decode("utf-8")
    for name in NAMES:
        assert name not in text
    for kept in ("Zed Widget", "0.0.1234567", "How it's Made", "github.com/sample-org/zed-widget"):
        assert kept in text


def test_personal_metadata_goes_even_with_no_rule_for_it() -> None:
    output, _ = cut(sample("project_zed_widget.html"))
    assert b'name="author"' not in output
    assert b'name="description"' in output  # other meta tags stay


def test_the_data_block_loses_its_members_and_keeps_the_rest() -> None:
    output, report = cut(sample("project_zed_widget.html"))
    start = output.index(b'type="application/json">') + len(b'type="application/json">')
    data = json.loads(output[start : output.index(b"</script>", start)])
    project = data["props"]["pageProps"]["project"]
    assert "members" not in project
    assert project["name"] == "Zed Widget"
    assert project["prize"] == "Best use of Hedera"
    assert report.json_keys_removed == 1


def test_the_report_counts_what_was_done() -> None:
    _, report = cut(sample("project_zed_widget.html"))
    assert report.elements_removed == 2  # the team section and the author meta tag
    assert report.strings_guarded > 0


def test_a_name_copied_into_a_data_block_is_caught() -> None:
    # Same page, but the policy does not know the key "members": the names stay in the data block.
    policy = CutPolicy(rules=(CutRule("#team"),), json_blocklist=frozenset())
    with pytest.raises(TeamTextRemains, match="still in the page"):
        cut(sample("project_zed_widget.html"), policy)


def test_the_error_never_contains_the_names_it_found() -> None:
    policy = CutPolicy(rules=(CutRule("#team"),), json_blocklist=frozenset())
    with pytest.raises(TeamTextRemains) as failure:
        cut(sample("project_zed_widget.html"), policy)
    for name in NAMES:
        assert name not in str(failure.value)


def test_a_required_rule_with_no_match_fails_closed() -> None:
    page = "<html><body><main><h1>A project</h1><p>No team here.</p></main></body></html>"
    with pytest.raises(TeamShapeChanged, match="required rule"):
        cut(page)


def test_an_optional_rule_with_no_match_is_fine() -> None:
    policy = CutPolicy(rules=(CutRule("#team", required=False),))
    page = (
        '<html><head><meta name="author" content="Quill Samplewright"></head>'
        "<body><main><h1>Zed Widget</h1><p>No team block on this page.</p></main></body></html>"
    )
    output, report = cut(page, policy)
    assert b"Zed Widget" in output
    assert b"Samplewright" not in output  # the author meta tag is still removed
    assert report.elements_removed == 1


def test_generic_words_in_the_team_block_do_not_cause_a_false_alarm() -> None:
    page = (
        "<html><body><nav><a href='/team-info'>Team</a></nav>"
        "<section id='team'><h2>Team</h2><p>Dorian Plumtree</p></section>"
        "<p>The project text.</p></body></html>"
    )
    output, _ = cut(page)
    assert b"Plumtree" not in output
    assert b"The project text." in output


def test_matches_inside_other_matches_are_removed_once() -> None:
    policy = CutPolicy(rules=(CutRule("#team"), CutRule(".member")))
    output, report = cut(sample("project_mango_ledger.html"), policy)
    assert b"Orchardson" not in output
    assert report.elements_removed == 1


def test_a_page_that_is_not_utf8_fails_closed() -> None:
    with pytest.raises(TeamShapeChanged, match="not UTF-8"):
        cut(b"\xff\xfe\x00<html></html>")


def test_a_name_in_the_projects_own_text_makes_that_page_unsafe_to_save() -> None:
    # The same name stands in the team block and in the description. The cut cannot tell a
    # team member's name from the team's own words, so it refuses the page. It is not removed
    # from the text: that would change what the team wrote.
    page = (
        "<html><body><main><p>Dorian Plumtree thanks the jury.</p>"
        "<section id='team'><p>Dorian Plumtree</p></section></main></body></html>"
    )
    with pytest.raises(TeamTextRemains):
        cut(page)


def test_both_kinds_of_failure_are_a_kind_of_cut_failed() -> None:
    assert issubclass(TeamShapeChanged, CutFailed)
    assert issubclass(TeamTextRemains, CutFailed)


# ------------------------------------------------------------ what the rewrite changes (Q20)


@pytest.mark.parametrize("name", ["project_zed_widget.html", "project_mango_ledger.html"])
def test_the_page_is_written_again_but_text_links_and_tags_stay_the_same(name: str) -> None:
    """The wording of design rule 5 rests on this test.

    The page is not saved byte for byte: the parser writes it again. This test compares the
    saved page with the original after the team part was removed by plain string slicing, and
    shows that the visible text, the links and the order of the tags are the same.
    """
    import re

    from bs4 import BeautifulSoup

    raw = sample(name).decode("utf-8")
    by_hand = re.sub(r'<section id="team">.*?</section>\s*', "", raw, flags=re.S)
    by_hand = re.sub(r'\s*<meta name="author"[^>]*>', "", by_hand)
    saved, _ = cut(raw)

    before = BeautifulSoup(by_hand, "lxml")
    after = BeautifulSoup(saved.decode("utf-8"), "lxml")
    assert " ".join(before.get_text().split()) == " ".join(after.get_text().split())
    assert [a["href"] for a in before.find_all("a", href=True)] == [
        a["href"] for a in after.find_all("a", href=True)
    ]
    assert [t.name for t in before.find_all(True)] == [t.name for t in after.find_all(True)]
    assert saved.decode("utf-8").lower().startswith("<!doctype html")  # the case may change


# ---------------------------------------------------- tripwires, script keys, site names
# These three exist because of what the real pages of a site showed: no team block at all for a
# visitor who is not signed in, the data of a React page kept as text, and a "creator" meta tag
# that holds the name of the site itself.

PAGE_WITH_A_PROFILE_LINK = (
    "<html><body><main><h1>A project</h1>"
    '<a href="/hackers/someone-invented">someone</a></main></body></html>'
)
PAGE_WITH_TEXT_DATA = (
    "<html><body><main><h1>A project</h1></main>"
    '<script>self.__next_f.push([1,"{\\"project\\":{\\"slug\\":\\"x\\",\\"members\\":'
    '[{\\"name\\":\\"Quillfeather\\"}]}}"])</script></body></html>'
)


def test_a_tripwire_stops_a_page_that_shows_a_profile_link() -> None:
    policy = CutPolicy(rules=(), tripwires=("a[href^='/hackers/']",))
    with pytest.raises(TeamShapeChanged, match="should not exist"):
        cut(PAGE_WITH_A_PROFILE_LINK, policy)


def test_a_tripwire_lets_a_page_without_it_pass() -> None:
    policy = CutPolicy(rules=(), tripwires=("a[href^='/hackers/']",))
    output, _ = cut("<html><body><main><h1>A project</h1></main></body></html>", policy)
    assert b"A project" in output


def test_a_person_key_in_a_script_that_is_not_json_refuses_the_page() -> None:
    policy = CutPolicy(rules=(), script_person_keys=frozenset({"members"}))
    with pytest.raises(TeamShapeChanged, match="'members'") as failure:
        cut(PAGE_WITH_TEXT_DATA, policy)
    assert "Quillfeather" not in str(failure.value)  # the key is named, never its value


def test_the_same_script_passes_when_the_key_is_not_one_that_holds_people() -> None:
    policy = CutPolicy(rules=(), script_person_keys=frozenset({"teammembers"}))
    output, _ = cut(PAGE_WITH_TEXT_DATA, policy)
    assert b"__next_f" in output


def test_a_person_key_written_with_plain_quotes_is_found_too() -> None:
    page = '<html><body><script>var data = {"users": [1, 2]};</script></body></html>'
    with pytest.raises(TeamShapeChanged, match="'users'"):
        cut(page, CutPolicy(rules=(), script_person_keys=frozenset({"users"})))


SITE_NAMED_IN_METADATA = (
    "<html><head>"
    '<meta name="author" content="SampleSite">'
    '<meta name="twitter:creator" content="@samplesite">'
    "</head><body><main><h1>SampleSite project</h1></main>"
    '<script>self.__next_f.push([1,"{\\"site\\":\\"@samplesite\\"}"])</script></body></html>'
)


def test_the_name_of_the_site_in_the_author_tags_is_not_a_leak_when_the_policy_says_so() -> None:
    # Without the names, the handle that also stands in the page data looks like a person.
    with pytest.raises(TeamTextRemains):
        cut(SITE_NAMED_IN_METADATA, CutPolicy(rules=()))
    policy = CutPolicy(rules=(), site_names=frozenset({"samplesite", "@samplesite"}))
    output, report = cut(SITE_NAMED_IN_METADATA, policy)
    assert b'name="author"' not in output  # the tags still go
    assert b'name="twitter:creator"' not in output
    assert report.elements_removed == 2


def test_a_name_that_is_not_the_site_is_still_caught_when_site_names_are_set() -> None:
    page = SITE_NAMED_IN_METADATA.replace('content="SampleSite"', 'content="Quill Samplewright"')
    page = page.replace(
        "<h1>SampleSite project</h1>", "<h1>A project</h1><p>Quill Samplewright</p>"
    )
    policy = CutPolicy(rules=(), site_names=frozenset({"samplesite", "@samplesite"}))
    output, _ = cut(page, policy)  # the name is visible in the page, so it is generic: no leak
    assert b"Quill Samplewright" in output
    hidden = SITE_NAMED_IN_METADATA.replace('content="SampleSite"', 'content="Quill Samplewright"')
    hidden = hidden.replace("</script>", ' var by = "Quill Samplewright";</script>')
    with pytest.raises(TeamTextRemains):
        cut(hidden, policy)
