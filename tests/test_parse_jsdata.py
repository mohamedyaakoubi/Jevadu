"""Data written as JavaScript literals: read, and nothing run. Every text here is invented."""

from __future__ import annotations

import re

import pytest

from hackathon_memory.parse.jsdata import (
    NotALiteral,
    enclosing_object,
    objects_holding,
    read_literal,
)

LINK = re.compile(r"https://example\.test/p/\d+")


def test_keys_without_quotes_and_both_kinds_of_quotes() -> None:
    text = "{name:\"Pebble\",track:'Payments',place:1,live:!0,old:!1,x:null}"
    value, end = read_literal(text + ";next()", 0)
    assert value == {
        "name": "Pebble",
        "track": "Payments",
        "place": 1,
        "live": True,
        "old": False,
        "x": None,
    }
    assert end == len(text)  # the literal ends where its "}" ends, before the code after it


def test_escapes_in_strings() -> None:
    value, _ = read_literal(r'"a\"b\né\x41😀\u{1F600}"', 0)
    assert value == 'a"b\néA\U0001f600\U0001f600'


def test_lists_and_objects_inside_each_other() -> None:
    value, _ = read_literal('{team:[{name:"x"},{name:"y"}],tags:["a","b"],n:-1.5e2,0:`t`}', 0)
    assert value == {"team": [{"name": "x"}, {"name": "y"}], "tags": ["a", "b"], "n": -150.0,
                     "0": "t"}  # fmt: skip


@pytest.mark.parametrize(
    "text", ["{a:b}", "{a:f()}", "{a(){}}", "`x${y}`", '"no end', "{a:1", "[1 2]", "'a\nb'"]
)
def test_what_is_not_a_literal_is_not_read(text: str) -> None:
    with pytest.raises(NotALiteral):
        read_literal(text, 0)


def test_the_objects_that_hold_a_link_are_found_with_the_place_of_each_value() -> None:
    script = (
        "var x=function(){return 1};const w=["
        '{name:"One",link:"https://example.test/p/1",team:["Ann"]},'
        '{name:"Two",about:{x:1},link:"https://example.test/p/2"}];foo({a:1});'
    )
    found = objects_holding(script, LINK)
    assert [f.value["name"] for f in found] == ["One", "Two"]
    start, end = found[0].spans["team"]
    assert script[start:end] == '["Ann"]'
    assert script[found[0].start : found[0].end].startswith('{name:"One"')


def test_a_link_in_code_and_not_in_an_object_is_not_found() -> None:
    assert objects_holding('fetch("https://example.test/p/9").then(r=>r.json())', LINK) == []


def test_a_lenient_read_passes_over_code_and_keeps_the_rest() -> None:
    text = (
        '{title:"Pay",logo:H.pay,fn:f(1,[2],"a,b"),t:`x${y}`,list:[1,g(),2],link:"https://x.test"}'
    )
    with pytest.raises(NotALiteral):
        read_literal(text, 0)
    value, end = read_literal(text + ";next()", 0, lenient=True)
    assert value == {"title": "Pay", "list": [1, 2], "link": "https://x.test"}
    assert end == len(text)


def test_the_object_around_the_records_is_found() -> None:
    script = (
        'x=1;m={onchain:[{title:"A",logo:H.a,url:"https://example.test/p/1"}],'
        'ai:[{title:"B",url:"https://example.test/p/2"}]};f=[{id:"ai"}];'
    )
    first, second = objects_holding(script, LINK, lenient=True)
    assert (first.value["title"], second.value["title"]) == ("A", "B")
    around = enclosing_object(script, first, lenient=True)
    assert around is not None and around.value == {
        "onchain": [{"title": "A", "url": "https://example.test/p/1"}],
        "ai": [{"title": "B", "url": "https://example.test/p/2"}],
    }


def test_a_link_held_by_an_inner_object_finds_the_inner_object() -> None:
    [found] = objects_holding('{name:"Outer",links:{site:"https://example.test/p/3"}}', LINK)
    assert found.value == {"site": "https://example.test/p/3"}
