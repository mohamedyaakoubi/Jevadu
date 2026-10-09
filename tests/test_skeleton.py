"""The skeleton printer shows the shape of a page and nothing that names a person."""

from __future__ import annotations

from pathlib import Path

import pytest

from fakes import SAMPLES, sample
from hackathon_memory.collect.skeleton import main, path_shape, skeleton

PEOPLE = ["Quillfeather", "Ledgerwood", "Orchardson", "quillfeather", "ledgerwood", "orchardson"]


@pytest.mark.parametrize("name", ["project_zed_widget.html", "project_mango_ledger.html"])
def test_no_person_and_no_page_text_in_the_output(name: str) -> None:
    text = skeleton(sample(name))
    for person in PEOPLE:
        assert person not in text
    for page_text in ("Zed Widget", "Mango Ledger", "0.0.1234567", "fruit stall", "Best use of"):
        assert page_text not in text


def test_the_structure_of_a_project_page_is_visible() -> None:
    text = skeleton(sample("project_zed_widget.html"))
    assert "section#team" in text
    assert 'h2 "Team"' in text  # a plain section word is shown
    assert 'h2 "Project Description"' in text
    assert "li.member" in text
    assert "hackers/{x}" in text  # a profile link, without the handle
    assert "script#__NEXT_DATA__" in text


def test_a_data_block_is_shown_as_keys_and_kinds() -> None:
    text = skeleton(sample("project_zed_widget.html"))
    assert "props.pageProps.project.members: list of 2" in text
    assert "props.pageProps.project.members[].name: str" in text
    assert "props.pageProps.project.slug: str" in text


def test_a_map_keyed_by_handles_does_not_show_the_handles() -> None:
    page = (
        b'<html><body><script type="application/json">'
        b'{"users": {"dorian_plumtree": {"name": "x"}, "pip_orchardson": {"name": "y"}}}'
        b"</script></body></html>"
    )
    text = skeleton(page)
    assert "dorian" not in text
    assert "orchardson" not in text
    assert "users: map of 2 records" in text
    assert "users{}.name: str" in text


def test_meta_tags_are_listed_by_name_only() -> None:
    text = skeleton(sample("project_zed_widget.html"))
    assert "Meta tags (names only): " in text
    assert "author" in text.split("Meta tags (names only): ")[1].split("\n")[0]


def test_a_heading_that_is_not_a_plain_section_word_is_shown_by_length() -> None:
    page = b"<html><body><h2>Dorian Plumtree</h2><h2>Team</h2></body></html>"
    text = skeleton(page)
    assert "Plumtree" not in text
    assert 'h2 "Team"' in text
    assert "h2 <text 15 chars>" in text


def test_link_shapes_are_counted() -> None:
    text = skeleton(sample("prize_page.html"))
    assert "/showcase/{x}" in text
    assert "example.com/{x}" in text


@pytest.mark.parametrize(
    ("url", "shape"),
    [
        ("https://ethglobal.com/hackers/zed-quillfeather", "ethglobal.com/hackers/{x}"),
        ("/hackers/zed-quillfeather", "/hackers/{x}"),
        ("/@alice", "/{x}"),
        ("/alice", "/{x}"),
        ("https://github.com/sample-org/zed-widget", "github.com/{x}/{x}"),
        ("https://ethglobal.com/showcase/mango-ledger-d4e5f", "ethglobal.com/showcase/{x}"),
        ("/showcase?page=2", "/showcase?{query}"),
        ("/", "/"),
    ],
)
def test_path_shapes(url: str, shape: str) -> None:
    assert path_shape(url) == shape


def test_the_command_line(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main([str(SAMPLES / "project_zed_widget.html")]) == 0
    assert "Structure" in capsys.readouterr().out
    assert main([str(tmp_path / "missing.html")]) == 1
    assert main([]) == 2
