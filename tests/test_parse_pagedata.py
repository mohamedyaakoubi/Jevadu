"""The data that a Next.js page carries in its scripts. Every text here is invented."""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from hackathon_memory.parse.pagedata import objects_with_key, page_data_text


def page(*pushed: str, extra: str = "") -> BeautifulSoup:
    scripts = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(text)}])</script>" for text in pushed
    )
    return BeautifulSoup(f"<html><body>{extra}{scripts}</body></html>", "lxml")


def test_the_texts_of_the_scripts_are_decoded_and_joined_in_order() -> None:
    soup = page('a:{"name":"Pebble', ' Pay","line":"say \\"hi\\"\\n"}\n', "b:done")
    assert page_data_text(soup) == 'a:{"name":"Pebble Pay","line":"say \\"hi\\"\\n"}\nb:done'


def test_letters_outside_ascii_and_escaped_signs_come_back_as_they_were() -> None:
    text = 'c:{"city":"Sfax ⵣ","mark":"<b> & </b>","path":"C:\\\\tmp"}'
    assert page_data_text(page(text)) == text


def test_other_scripts_hold_no_data() -> None:
    extra = (
        "<script>self.__next_f=self.__next_f||[];self.__next_f.push([0])</script>"
        "<script>self.__next_f.push([2,null])</script>"
        '<script type="application/ld+json">{"name":"not page data"}</script>'
        "<script>console.log('self.__next_f.push')</script>"
        "<script></script>"
    )
    assert page_data_text(page("only this", extra=extra)) == "only this"
    assert page_data_text(BeautifulSoup("<html><body><p>no script</p></body></html>", "lxml")) == ""


def test_an_object_is_found_by_one_of_its_own_keys() -> None:
    text = '2a:["$","$L2b",null,{"currentPage":3,"projects":[{"slug":"a"},{"slug":"b"}]}]\n'
    assert objects_with_key(text, "currentPage") == [
        {"currentPage": 3, "projects": [{"slug": "a"}, {"slug": "b"}]}
    ]
    assert objects_with_key(text, "slug") == [{"slug": "a"}, {"slug": "b"}]
    assert objects_with_key(text, "missing") == []


def test_the_object_that_holds_the_key_itself_is_returned_not_a_neighbour() -> None:
    # An object stands before the key, inside the object that we want.
    text = 'x:{"first":{"deep":1},"wanted":2,"last":{"deep":3}}'
    assert objects_with_key(text, "wanted") == [
        {"first": {"deep": 1}, "wanted": 2, "last": {"deep": 3}}
    ]
    # The same key at two depths: both objects, the outer one first.
    nested = '{"k":1,"inner":{"k":2}}'
    assert objects_with_key(nested, "k") == [{"k": 1, "inner": {"k": 2}}, {"k": 2}]


def test_a_key_that_is_only_written_inside_a_string_is_not_a_key() -> None:
    text = json.dumps({"note": 'the text says "currentPage":1 here'})
    assert objects_with_key(text, "currentPage") == []


def test_text_around_an_object_does_not_have_to_be_json() -> None:
    text = (
        '1b:T1c,a text row with a } and a "\n'
        '2a:["$","$L2b",null,{"currentPage":1,"projects":[]}]\n'
        '2c:T1c,a text row with a { and a "\n'
    )
    assert objects_with_key(text, "currentPage") == [{"currentPage": 1, "projects": []}]


def test_an_object_that_is_cut_off_is_not_found() -> None:
    assert objects_with_key('{"currentPage":1,"projects":[{"slug":"a"}', "currentPage") == []
