"""Hide words about people in a text that the parser copies (design 5.4, design rule 11).

A team can write the handle of a person, an email address or a link to a profile inside its own
text. The tool keeps no names, handles or addresses of people. So these words are hidden before
the text reaches a table, a model or a card. Everything else stays word for word.

What is hidden:

* a word that starts with "@", such as a handle on a social network;
* an email address;
* a link to a profile on a social site, written in the text ("x.com/name", "t.me/name");
* a link to the profile of an account on GitHub: an address with one name only.

The tool cannot tell a person from a company or from a bot of the project, so it hides all of
them. Little is lost: a card links to the page of the project.

A link that stands on its own, such as the demo link of a project, is asked the same question
by `profile_site`. Its address is then not kept: only the name of the site is.

What is not hidden:

* the name of a package, which has a slash after its first part ("@scope/package");
* anything inside code but an email address. There an "@" belongs to the language, as in
  "@media" or "@Override";
* a link to a video, or to the code: an address on GitHub with an account and a repository.
  The name of the account is part of that link, and the link is what a card needs.

A sign of the sentence after a hidden word stays where it is: "ask @someone." keeps its full
stop.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import urlsplit

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
# On a code host an address with one name only is the profile of an account, of a person or
# of a group. With two names it is a repository, and that link is kept.
CODE_HOST = "github.com"
_ACCOUNT_LINK = re.compile(
    rf"(?<![A-Za-z0-9.@/-])(?:https?://)?(?:www\.)?{re.escape(CODE_HOST)}/([^\s<>()\[\]\"']+)",
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


def _names_in(path: str) -> list[str]:
    """The names of a path, without what follows a "?" or a "#"."""
    return [name for name in re.split("[?#]", path, maxsplit=1)[0].split("/") if name]


def _account_link(match: re.Match[str]) -> str:
    link = match.group(0)
    bare = link.rstrip(_SENTENCE_SIGNS)
    path = match.group(1)[: len(match.group(1)) - (len(link) - len(bare))]
    if len(_names_in(path)) != 1:
        return link  # a repository, a file of one, or nothing after the site
    return HIDDEN_LINK + link[len(bare) :]


def _address(match: re.Match[str]) -> str:
    return HIDDEN_ADDRESS


# In this order: a link first, so that an address or a handle inside it is not taken alone.
_HIDERS = (
    (_PROFILE_LINK, _profile_link),
    (_ACCOUNT_LINK, _account_link),
    (ADDRESS, _address),
    (_AT_WORD, _handle),
)


def _hide(
    pattern: re.Pattern[str], shown_for: Callable[[re.Match[str]], str], text: str
) -> tuple[str, int]:
    """Put what `shown_for` gives in the place of each match, and count the matches that changed.

    A match that stays as it is, such as the name of a package, was not hidden.
    """
    changed = 0

    def swap(match: re.Match[str]) -> str:
        nonlocal changed
        shown = shown_for(match)
        changed += shown != match.group(0)
        return shown

    return pattern.sub(swap, text), changed


def hide_in_text(text: str) -> tuple[str, int]:
    """The text with links to profiles, addresses and handles hidden, and how many were hidden."""
    hidden = 0
    for pattern, shown_for in _HIDERS:
        text, changed = _hide(pattern, shown_for, text)
        hidden += changed
    return text, hidden


def profile_site(url: str) -> str | None:
    """The profile site that the address of a link leads to, or None when it leads elsewhere.

    For a link that stands on its own, such as the demo link of a project. The address of the
    site alone, with nothing after it, names nobody and gives None.
    """
    try:
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
    except ValueError:  # not an address that a browser could open
        return None
    if host in (CODE_HOST, "www." + CODE_HOST):
        return CODE_HOST if len(_names_in(parts.path)) == 1 else None
    if not (parts.path.strip("/") or parts.query or parts.fragment):
        return None
    return next((site for site in PROFILE_SITES if host == site or host.endswith("." + site)), None)


def hide_in_code(text: str) -> tuple[str, int]:
    """Code with its email addresses hidden, and how many were hidden.

    Inside code an "@" belongs to the language ("@media", "@Override", "@scope/package"), so
    nothing else is touched there. An email address is still an address.
    """
    return _hide(ADDRESS, _address, text)


def hide_in_box(box: Tag) -> int:
    """Hide the words about people in the texts inside `box`, in place. In code, only email
    addresses are hidden.

    Returns how many words were hidden.
    """
    hidden = 0
    for string in list(box.find_all(string=True)):
        if type(string) is not NavigableString:  # a comment is not text
            continue
        in_code = any(parent.name in _CODE_TAGS for parent in string.parents)
        shown, count = (hide_in_code if in_code else hide_in_text)(str(string))
        if count:
            string.replace_with(shown)
            hidden += count
    return hidden
