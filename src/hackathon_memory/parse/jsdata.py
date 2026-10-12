"""Data written as JavaScript literals inside a script file.

A page built with Next.js can keep its data in the script files that it loads. There the data is
JavaScript, not JSON: keys without quotes (`{name:"x"}`), strings in double, single or back
quotes, and `!0` and `!1` for true and false. This module reads such literals and nothing else:
no function, no variable, no expression is read or run. A value that is not a literal ends the
literal that holds it, which is then not read at all.

One exception, asked for by name (`lenient=True`): a record whose values are mostly data, with
one value that is code, such as `logo:H.silsilat` (a picture that the script imports). Then the
code is passed over, its key is left out of the record, and the rest is read.

Written for the winners page of the Hedera Africa hackathon on 12 October 2026. Nothing here
knows about one site.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SPACE = re.compile(r"\s*")
_NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_WORD = re.compile(r"[A-Za-z_$][\w$]*")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
_MAX_DEPTH = 40
# How many "{" to the left of a matching string are tried as the start of its object.
_MAX_STARTS = 40


class NotALiteral(ValueError):
    """The text at this place is not a JavaScript literal that this module reads."""


@dataclass(frozen=True)
class Found:
    """An object in a script, where it stands, and where each of its own values stands."""

    start: int  # the index of its "{"
    end: int  # the index just after its "}"
    value: dict
    spans: dict[str, tuple[int, int]] = field(default_factory=dict)  # key: (start, end) of value


def _skip(text: str, at: int) -> int:
    return _SPACE.match(text, at).end()  # type: ignore[union-attr]


def _string(text: str, at: int) -> tuple[str, int]:
    quote = text[at]
    out: list[str] = []
    i = at + 1
    while i < len(text):
        char = text[i]
        if char == quote:
            joined = "".join(out)
            # A pair of escaped halves (😀) becomes one letter.
            return joined.encode("utf-16", "surrogatepass").decode("utf-16"), i + 1
        if quote == "`" and text.startswith("${", i):
            raise NotALiteral("a template string with an expression")
        if char == "\\":
            i += 1
            if i >= len(text):
                break
            code = text[i]
            if code == "u" and text.startswith("{", i + 1):
                close = text.find("}", i + 2)
                out.append(chr(int(text[i + 2 : close], 16)))
                i = close + 1
                continue
            if code in "ux":
                size = 4 if code == "u" else 2
                digits = text[i + 1 : i + 1 + size]
                if len(digits) != size or not all(c in "0123456789abcdefABCDEF" for c in digits):
                    raise NotALiteral("a wrong escape in a string")
                out.append(chr(int(digits, 16)))
                i += 1 + size
                continue
            if code in "\r\n":  # a line that goes on after a backslash
                i += 1
                continue
            out.append(_ESCAPES.get(code, code))
            i += 1
            continue
        if char == "\n" and quote != "`":
            raise NotALiteral("a string that runs past the end of its line")
        out.append(char)
        i += 1
    raise NotALiteral("a string with no end")


def _after_string(text: str, at: int) -> int:
    """The index just after the string that starts at `at`, with what a template holds."""
    quote = text[at]
    i = at + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
        elif text[i] == quote:
            return i + 1
        elif quote == "`" and text.startswith("${", i):
            i = _end_of_code(text, i + 2) + 1  # the "}" that closes the expression
        else:
            i += 1
    raise NotALiteral("a string with no end")


def _end_of_code(text: str, at: int) -> int:
    """The index of the "," or closing sign that ends the code starting at `at`, outside of any
    string and of any bracket that the code opens itself."""
    depth = 0
    i = at
    while i < len(text):
        char = text[i]
        if char in "\"'`":
            i = _after_string(text, i)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif char == "," and depth == 0:
            return i
        i += 1
    raise NotALiteral("code with no end")


def _object(
    text: str,
    at: int,
    depth: int,
    lenient: bool,
    spans: dict[str, tuple[int, int]] | None = None,
) -> tuple[dict, int]:
    result: dict = {}
    i = _skip(text, at + 1)
    while True:
        if i >= len(text):
            raise NotALiteral("an object with no end")
        if text[i] == "}":
            return result, i + 1
        if text[i] in "\"'":
            key, i = _string(text, i)
        else:
            word = _WORD.match(text, i) or _NUMBER.match(text, i)
            if word is None:
                raise NotALiteral("a key that is not a name")
            key, i = word.group(), word.end()
        i = _skip(text, i)
        if i >= len(text) or text[i] != ":":
            raise NotALiteral("a key with no value")  # a method or a short form: not data
        start = _skip(text, i + 1)
        try:
            result[key], i = _value(text, start, depth + 1, lenient)
        except NotALiteral:
            if not lenient:
                raise
            i = _end_of_code(text, start)  # code, not data: its key is left out
        else:
            if spans is not None:
                spans[key] = (start, i)
        i = _skip(text, i)
        if i < len(text) and text[i] == ",":
            i = _skip(text, i + 1)
        elif i >= len(text) or text[i] != "}":
            raise NotALiteral("an object that goes on with something else")


def _array(text: str, at: int, depth: int, lenient: bool) -> tuple[list, int]:
    result: list = []
    i = _skip(text, at + 1)
    while True:
        if i >= len(text):
            raise NotALiteral("a list with no end")
        if text[i] == "]":
            return result, i + 1
        try:
            item, i = _value(text, i, depth + 1, lenient)
        except NotALiteral:
            if not lenient:
                raise
            i = _end_of_code(text, i)  # code, not data: the item is left out
        else:
            result.append(item)
        i = _skip(text, i)
        if i < len(text) and text[i] == ",":
            i = _skip(text, i + 1)
        elif i >= len(text) or text[i] != "]":
            raise NotALiteral("a list that goes on with something else")


def _value(text: str, at: int, depth: int, lenient: bool = False) -> tuple[object, int]:
    if depth > _MAX_DEPTH:
        raise NotALiteral("too deep")
    at = _skip(text, at)
    if at >= len(text):
        raise NotALiteral("the text ends")
    char = text[at]
    if char in "\"'`":
        return _string(text, at)
    if char == "{":
        return _object(text, at, depth, lenient)
    if char == "[":
        return _array(text, at, depth, lenient)
    if text.startswith(("!0", "!1"), at):
        return text[at + 1] == "0", at + 2
    number = _NUMBER.match(text, at)
    if number:
        written = number.group()
        is_whole = not any(c in written for c in ".eE")
        return (int(written) if is_whole else float(written)), number.end()
    word = _WORD.match(text, at)
    if word and word.group() in ("true", "false", "null"):
        return {"true": True, "false": False, "null": None}[word.group()], word.end()
    raise NotALiteral("not a literal")


def read_literal(text: str, at: int, *, lenient: bool = False) -> tuple[object, int]:
    """The literal that starts at `at` (after spaces), and the index just after it."""
    return _value(text, at, 0, lenient)


def read_object(text: str, at: int, *, lenient: bool = False) -> Found:
    """The object whose "{" stands at `at`, with the place of each of its own values."""
    if not text.startswith("{", at):
        raise NotALiteral("no object here")
    spans: dict[str, tuple[int, int]] = {}
    value, end = _object(text, at, 0, lenient, spans)
    return Found(at, end, value, spans)


def objects_holding(text: str, pattern: re.Pattern[str], *, lenient: bool = False) -> list[Found]:
    """Every object that holds, as one of its own values, a string that `pattern` matches, in
    the order of the text.

    For each place that the pattern matches, the "{" signs to its left are tried, the nearest
    first, until one starts an object that reaches past the match and holds such a string itself.
    """
    found: dict[int, Found] = {}
    for match in pattern.finditer(text):
        start = match.start()
        for _ in range(_MAX_STARTS):
            start = text.rfind("{", 0, start)
            if start == -1:
                break
            try:
                candidate = read_object(text, start, lenient=lenient)
            except (NotALiteral, ValueError, OverflowError):
                continue
            if candidate.end <= match.start():
                continue
            if any(isinstance(v, str) and pattern.search(v) for v in candidate.value.values()):
                found.setdefault(start, candidate)
                break
    return [found[start] for start in sorted(found)]


def enclosing_object(text: str, inner: Found, *, lenient: bool = False) -> Found | None:
    """The nearest object around `inner`: the first "{" to its left that starts an object that
    reaches past it."""
    start = inner.start
    for _ in range(_MAX_STARTS * 5):
        start = text.rfind("{", 0, start)
        if start == -1:
            return None
        try:
            candidate = read_object(text, start, lenient=lenient)
        except (NotALiteral, ValueError, OverflowError):
            continue
        if candidate.end >= inner.end:
            return candidate
    return None
