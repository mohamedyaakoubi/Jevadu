"""The line of the register, added to a team's README by Jevadu's GitHub App (design 9.2, 30
October 2026).

A team that asks for it signs in with GitHub, which gives the site a user access token. Such a
token "only has permissions that both the user and the app have", and "can only access resources
that both the user and app can access" (GitHub's docs, "Generating a user access token for a GitHub
App", read on 30 October 2026). With it the site finds the repository among the installations of
the app that the person can see, checks that the person may write to it, and adds the line at the
end of the README of the default branch: a commit of the person's own, made through the app. The
token lives for one request: it is never kept, in the database, a cookie or a log.

What the person asked for (the repository and the hackathon) waits in a cookie while GitHub signs
them in, sealed with a key made from the app's client secret, with a random `state` that GitHub
gives back: an answer whose `state` differs is not trusted (GitHub's docs, the same page).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urlencode

import httpx

from hackathon_memory.hedera.registry import carries_line

API = "https://api.github.com"
AUTHORIZE = "https://github.com/login/oauth/authorize"
TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105, a web address
COOKIE = "hm-github"  # what the person asked for, while GitHub signs them in
WAIT_SECONDS = 600  # the time a person has to sign in with GitHub
USER_AGENT = "Jevadu-register"
COMMIT_MESSAGE = "Add the line of the Jevadu register"
MOST_PAGES = 10  # of 100 installations, and of 100 repositories each

NOT_TEXT = (
    "The README of this repository is not text that the site can add a line to. Add the line "
    "yourself, then click the button of the register."
)
CHANGED = "The README changed while the line was added. Click the button again."
NOT_SIGNED_IN = "GitHub did not sign you in, so nothing was added. Click the button again."


class GitHubAppError(Exception):
    """A step with GitHub that went wrong, in plain words for the page."""


@dataclass(frozen=True)
class Asked:
    """What the person asked for: the line of this repository for this hackathon."""

    repository: str  # https://github.com/owner/name
    event: str  # the hackathon, as the form of the check sends it
    starts: str
    ends: str
    state: str  # the random text that GitHub gives back
    until: float  # the time after which the request is not trusted


@dataclass(frozen=True)
class Access:
    """What a person's token sees of one repository."""

    installed: bool  # the app is installed on the repository, among what the person can see
    push: bool  # the person may write to it
    branch: str | None  # its default branch


def owner_and_name(repository: str) -> tuple[str, str]:
    """The account and the name of a repository, from a link such as github.com/account/name."""
    parts = repository.rstrip("/").split("/")
    return parts[-2], parts[-1]


def _key(secret: str) -> bytes:
    return hashlib.sha256(b"jevadu-github-cookie|" + secret.encode("utf-8")).digest()


def sealed(asked: Asked, secret: str) -> str:
    """The cookie of a request: its parts in base64, and their HMAC-SHA256 under the app's key."""
    body = base64.urlsafe_b64encode(json.dumps(asked.__dict__).encode("utf-8")).decode("ascii")
    mark = hmac.new(_key(secret), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{mark}"


def opened(cookie: str, secret: str, now: float) -> Asked | None:
    """The request in a cookie, or None when the cookie is missing, changed or too old."""
    body, _, mark = (cookie or "").rpartition(".")
    if not body or not secret:
        return None
    good = hmac.new(_key(secret), body.encode("ascii", "replace"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, mark):
        return None
    try:
        asked = Asked(**json.loads(base64.urlsafe_b64decode(body.encode("ascii"))))
    except (binascii.Error, ValueError, TypeError):
        return None
    return asked if asked.until > now else None


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    """GitHub's page that signs the person in for the app (the web application flow)."""
    asked = {"client_id": client_id, "redirect_uri": redirect_uri, "state": state,
             "allow_signup": "false"}  # fmt: skip
    return f"{AUTHORIZE}?{urlencode(asked)}"


def install_url(slug: str) -> str:
    """GitHub's page where the person installs the app on a repository."""
    return f"https://github.com/apps/{quote(slug)}/installations/new"


def user_token(
    http: httpx.Client, client_id: str, client_secret: str, code: str, redirect_uri: str
) -> str:
    """The person's user access token, for the code that GitHub gave back."""
    asked = {"client_id": client_id, "client_secret": client_secret, "code": code,
             "redirect_uri": redirect_uri}  # fmt: skip
    plain = {"Accept": "application/json", "User-Agent": USER_AGENT}
    answer = http.post(TOKEN_URL, data=asked, headers=plain)
    try:
        found = answer.json()
    except ValueError:  # GitHub's form-encoded answer, when JSON was not given
        found = {key: values[0] for key, values in parse_qs(answer.text).items()}
    token = found.get("access_token") if isinstance(found, dict) else None
    if answer.status_code != 200 or not isinstance(token, str) or not token:
        raise GitHubAppError(NOT_SIGNED_IN)
    return token


def _headers(token: str) -> dict[str, str]:
    return {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": USER_AGENT}  # fmt: skip


def _pages(http: httpx.Client, token: str, path: str, key: str) -> list[dict[str, Any]]:
    """Every item of a list of GitHub's API, 100 a page."""
    items: list[dict[str, Any]] = []
    for page in range(1, MOST_PAGES + 1):
        answer = http.get(f"{API}{path}", headers=_headers(token),
                          params={"per_page": 100, "page": page})  # fmt: skip
        if answer.status_code != 200:
            raise GitHubAppError(
                f"GitHub refused to list what your account can reach ({answer.status_code}). "
                "Try again in a minute."
            )
        found = answer.json().get(key) or []
        items.extend(found)
        if len(found) < 100:
            break
    return items


def access(http: httpx.Client, token: str, owner: str, name: str) -> Access:
    """Whether the app is installed on the repository for this person, and whether the person
    may write to it, from the installations that the token sees and their repositories."""
    wanted = f"{owner}/{name}".lower()
    for installation in _pages(http, token, "/user/installations", "installations"):
        path = f"/user/installations/{int(installation['id'])}/repositories"
        for repository in _pages(http, token, path, "repositories"):
            if str(repository.get("full_name", "")).lower() != wanted:
                continue
            rights = repository.get("permissions") or {}
            push = any(rights.get(kind) for kind in ("push", "maintain", "admin"))
            return Access(True, push, repository.get("default_branch") or None)
    return Access(False, False, None)


def with_line(text: str, line: str) -> str:
    """The README with the line at its end, after an empty line; the rest stays as it was."""
    if not text.strip():
        return f"{line}\n"
    return f"{text}{'' if text.endswith(chr(10)) else chr(10)}\n{line}\n"


def add_line(
    http: httpx.Client, token: str, owner: str, name: str, line: str, branch: str | None
) -> str | None:
    """Add the line at the end of the README of the default branch, as a commit of the person's
    own. Returns the commit's ID, or None when the README holds the line already. A repository
    with no README gets one with the line. A README that changes in between is read again once."""
    where = f"{API}/repos/{quote(owner)}/{quote(name)}"
    for _ in range(2):
        readme = http.get(f"{where}/readme", headers=_headers(token),
                          params={"ref": branch} if branch else None)  # fmt: skip
        if readme.status_code == 404:
            path, sha, text = "README.md", None, ""
        elif readme.status_code == 200:
            found = readme.json()
            if found.get("encoding") != "base64" or not isinstance(found.get("content"), str):
                raise GitHubAppError(NOT_TEXT)
            try:
                text = base64.b64decode(found["content"]).decode("utf-8")
            except (binascii.Error, ValueError):  # UnicodeDecodeError is a ValueError
                raise GitHubAppError(NOT_TEXT) from None
            path, sha = found["path"], found["sha"]
        else:
            raise GitHubAppError(
                f"GitHub did not give the README ({readme.status_code}). Try again in a minute."
            )
        if carries_line(text, line):
            return None
        body: dict[str, str] = {
            "message": COMMIT_MESSAGE,
            "content": base64.b64encode(with_line(text, line).encode("utf-8")).decode("ascii"),
        }
        if sha:
            body["sha"] = sha
        if branch:
            body["branch"] = branch
        written = http.put(f"{where}/contents/{quote(path)}", headers=_headers(token), json=body)
        if written.status_code in (200, 201):
            return str(written.json()["commit"]["sha"])
        if written.status_code != 409:  # 409: the README changed since it was read
            raise GitHubAppError(
                f"GitHub refused to add the line ({written.status_code}). Add it yourself, then "
                "click the button of the register."
            )
    raise GitHubAppError(CHANGED)
