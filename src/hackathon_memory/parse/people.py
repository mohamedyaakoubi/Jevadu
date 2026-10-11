"""Hide words about people in a text that the parser copies (design 5.4, design rule 11).

A team can write the handle of a person, an email address or a link to a profile inside its own
text. The tool keeps no names, handles or addresses of people. So these words are hidden before
the text reaches a table, a model or a card. Everything else stays word for word.

What is hidden:

* a word that starts with "@", such as a handle on a social network;
* an email address;
* a link to a profile on a social site, written in the text ("x.com/name", "t.me/name").

The tool cannot tell a person from a company or from a bot of the project, so it hides all of
them. Little is lost: a card links to the page of the project.

What is not hidden:

* the name of a package, which has a slash after its first part ("@scope/package");
* anything inside code. There an "@" belongs to the language, as in "@media" or "@Override";
* a link to a video or to the code.

A sign of the sentence after a hidden word stays where it is: "ask @someone." keeps its full
stop.
"""

from __future__ import annotations

import re

from bs4 import NavigableString, Tag

HIDDEN_HANDLE = "@[name hidden]"
HIDDEN_ADDRESS = "[address hidden]"
HIDDEN_LINK = "[profile link hidden]"

# An email address: something, an @, and a name with at least one dot in it.
ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# An @ that starts a word, with everything that is glued to it. What it is, is decided after
# the whole word is taken: a pattern that could give back letters would turn "@scope/package"
# into a handle.
_AT_WORD = re.compile(r"(?<![A-Za-z0-9._%+/-])@([A-Za-z0-9_./-]+)")
# The sites where a page is the profile of somebody.
PROFILE_SITES = (
    "twitter.com",
    "x.com",
    "t.me",
    "telegram.me",
    "linkedin.com",
    "instagram.com",
    "facebook.com",
    "warpcast.com",
    "threads.net",
    "bsky.app",
    "tiktok.com",
)
# A link to one of them, also behind another first part ("www.", "uk.", "m."). The name of the
# site must start after a dot or at the start: "box.com" is not "x.com".
_PROFILE_LINK = re.compile(
    r"(?<![A-Za-z0-9.@/-])(?:https?://)?(?:[A-Za-z0-9-]+\.)*"
    rf"(?:{'|'.join(re.escape(site) for site in PROFILE_SITES)})/[^\s<>()\[\]\"']+",
    re.IGNORECASE,
)
_SENTENCE_SIGNS = ".,;:!?"
_CODE_TAGS = frozenset({"code", "pre", "script", "style"})


def _handle(match: re.Match[str]) -> str:
    word = match.group(1)
    name = word.rstrip(".-")
    if "/" in word or not name:
        return match.group(0)  # the name of a package, a path, or only signs
    return HIDDEN_HANDLE + word[len(name) :]


def _profile_link(match: re.Match[str]) -> str:
    link = match.group(0)
    return HIDDEN_LINK + link[len(link.rstrip(_SENTENCE_SIGNS)) :]


def hide_in_text(text: str) -> tuple[str, int]:
    """The text with links to profiles, addresses and handles hidden, and how many were hidden."""
    text, links = _PROFILE_LINK.subn(_profile_link, text)
    text, addresses = ADDRESS.subn(HIDDEN_ADDRESS, text)
    handles = 0

    def count(match: re.Match[str]) -> str:
        nonlocal handles
        shown = _handle(match)
        handles += shown != match.group(0)
        return shown

    return _AT_WORD.sub(count, text), links + addresses + handles


def hide_in_box(box: Tag) -> int:
    """Hide the words about people in the texts inside `box`, in place. Code is left alone.

    Returns how many words were hidden.
    """
    hidden = 0
    for string in list(box.find_all(string=True)):
        if type(string) is not NavigableString:  # a comment is not text
            continue
        if any(parent.name in _CODE_TAGS for parent in string.parents):
            continue
        shown, count = hide_in_text(str(string))
        if count:
            string.replace_with(shown)
            hidden += count
    return hidden
