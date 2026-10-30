"""Jevadu's GitHub App, which adds the line of the register to a team's README (web/github_app.py),
against a stand-in GitHub that answers as GitHub's docs describe (read on 30 October 2026)."""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from hackathon_memory.web import github_app

LINE = "jevadu: ABCDEFGH"
TOKEN = "ghu_STANDIN"  # noqa: S105, an invented token


class StandInGitHub:
    """GitHub as the app sees it: the sign-in, the installations that a person's token sees, and
    the README of sample-org/pebble-pay, which a PUT replaces."""

    def __init__(self, readme: str | None = "# Pebble Pay\n", *, installed: bool = True,
                 push: bool = True, conflicts: int = 0,
                 login: str = "mohamedyaakoubi") -> None:  # fmt: skip
        self.readme = readme
        self.login = login  # the account that the token belongs to (GET /user)
        self.installed = installed
        self.push = push
        self.conflicts = conflicts  # how many writes GitHub refuses with 409 first
        self.written: list[dict] = []
        self.asked: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.asked.append(f"{request.method} {request.url.host}{path}")
        if request.url.host == "github.com" and path == "/login/oauth/access_token":
            form = parse_qs(request.content.decode())
            if form.get("code") != ["the-code"] or form.get("client_secret") != ["standin-secret"]:
                return httpx.Response(200, json={"error": "bad_verification_code"})
            return httpx.Response(200, json={"access_token": TOKEN, "token_type": "bearer",
                                             "scope": ""})  # fmt: skip
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"message": "Bad credentials"})
        if path == "/user":
            return httpx.Response(200, json={"login": self.login, "id": 1})
        if path == "/user/installations":
            return httpx.Response(200, json={"total_count": 1, "installations": [{"id": 7}]})
        if path == "/user/installations/7/repositories":
            rights = {"admin": False, "push": self.push, "pull": True}
            found = [{"full_name": "sample-org/pebble-pay", "default_branch": "main",
                      "permissions": rights}]  # fmt: skip
            repositories = found if self.installed else []
            return httpx.Response(200, json={"total_count": len(repositories),
                                             "repositories": repositories})  # fmt: skip
        if path == "/repos/sample-org/pebble-pay/readme":
            if self.readme is None:
                return httpx.Response(404, json={"message": "Not Found"})
            content = base64.b64encode(self.readme.encode()).decode()
            return httpx.Response(200, json={"path": "README.md", "sha": "1" * 40,
                                             "encoding": "base64", "content": content})  # fmt: skip
        if request.method == "PUT" and path.startswith("/repos/sample-org/pebble-pay/contents/"):
            if self.conflicts:
                self.conflicts -= 1
                return httpx.Response(409, json={"message": "README.md does not match"})
            body = json.loads(request.content)
            self.written.append({"path": path.rsplit("/", 1)[-1], **body})
            self.readme = base64.b64decode(body["content"]).decode()
            return httpx.Response(200 if "sha" in body else 201,
                                  json={"commit": {"sha": "c0ffee" + "0" * 34}})  # fmt: skip
        return httpx.Response(404, json={"message": "Not Found"})


def http_of(stand_in: StandInGitHub) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(stand_in))


def test_a_request_comes_back_only_sealed_by_the_site_and_in_time() -> None:
    asked = github_app.Asked("https://github.com/sample-org/pebble-pay", "3", "", "", "s1", 100.0)
    cookie = github_app.sealed(asked, "standin-secret")
    assert github_app.opened(cookie, "standin-secret", 99.0) == asked
    assert github_app.opened(cookie, "standin-secret", 101.0) is None  # too late
    assert github_app.opened(cookie, "another-secret", 99.0) is None
    body, _, mark = cookie.rpartition(".")
    changed = base64.urlsafe_b64encode(
        base64.urlsafe_b64decode(body).replace(b"pebble-pay", b"other-repo")).decode()  # fmt: skip
    assert github_app.opened(f"{changed}.{mark}", "standin-secret", 99.0) is None
    assert github_app.opened("", "standin-secret", 99.0) is None
    assert "pebble" not in mark and len(mark) == 64  # an HMAC-SHA256, in hexadecimal


def test_the_line_goes_at_the_end_and_the_rest_stays() -> None:
    assert github_app.with_line("# Pebble Pay\n", LINE) == f"# Pebble Pay\n\n{LINE}\n"
    assert github_app.with_line("# Pebble Pay", LINE) == f"# Pebble Pay\n\n{LINE}\n"
    assert github_app.with_line("", LINE) == f"{LINE}\n"
    assert github_app.with_line("a\r\n\r\n", LINE) == f"a\r\n\r\n\n{LINE}\n"


def test_the_sign_in_gives_a_token_only_for_the_right_code() -> None:
    stand_in = StandInGitHub()
    with http_of(stand_in) as http:
        token = github_app.user_token(http, "Iv1.standin", "standin-secret", "the-code",
                                      "http://testserver/github/callback")  # fmt: skip
        assert token == TOKEN
        with pytest.raises(github_app.GitHubAppError, match="did not sign you in"):
            github_app.user_token(http, "Iv1.standin", "standin-secret", "old-code", "x")


def test_a_form_encoded_answer_of_the_sign_in_is_read_too() -> None:
    def answer(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=f"access_token={TOKEN}&scope=&token_type=bearer")

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        assert github_app.user_token(http, "a", "b", "c", "d") == TOKEN


def test_access_tells_installed_and_the_right_to_write() -> None:
    with http_of(StandInGitHub()) as http:
        assert github_app.access(http, TOKEN, "Sample-Org", "Pebble-Pay") == github_app.Access(
            True, True, "main")  # fmt: skip
    with http_of(StandInGitHub(push=False)) as http:
        assert github_app.access(http, TOKEN, "sample-org", "pebble-pay").push is False
    with http_of(StandInGitHub(installed=False)) as http:
        assert github_app.access(http, TOKEN, "sample-org", "pebble-pay") == github_app.Access(
            False, False, None)  # fmt: skip


def test_the_line_is_added_once_as_a_commit_of_the_person() -> None:
    stand_in = StandInGitHub()
    with http_of(stand_in) as http:
        commit = github_app.add_line(http, TOKEN, "sample-org", "pebble-pay", LINE, "main")
        assert commit == "c0ffee" + "0" * 34
        (written,) = stand_in.written
        assert written["path"] == "README.md" and written["sha"] == "1" * 40
        assert written["branch"] == "main"
        assert written["message"] == "Add the line of the Jevadu register"
        assert "committer" not in written and "author" not in written  # GitHub names the person
        assert stand_in.readme == f"# Pebble Pay\n\n{LINE}\n"
        again = github_app.add_line(http, TOKEN, "sample-org", "pebble-pay", LINE, "main")
        assert again is None and len(stand_in.written) == 1  # the line is there: nothing to do


def test_a_repository_with_no_readme_gets_one_with_the_line() -> None:
    stand_in = StandInGitHub(readme=None)
    with http_of(stand_in) as http:
        assert github_app.add_line(http, TOKEN, "sample-org", "pebble-pay", LINE, None)
    (written,) = stand_in.written
    assert "sha" not in written and "branch" not in written and stand_in.readme == f"{LINE}\n"


def test_a_readme_that_changed_meanwhile_is_read_again_once() -> None:
    with http_of(StandInGitHub(conflicts=1)) as http:
        assert github_app.add_line(http, TOKEN, "sample-org", "pebble-pay", LINE, "main")
    with http_of(StandInGitHub(conflicts=2)) as http, pytest.raises(github_app.GitHubAppError,
                                                                      match="changed"):  # fmt: skip
        github_app.add_line(http, TOKEN, "sample-org", "pebble-pay", LINE, "main")


def test_a_readme_that_is_not_text_is_left_alone() -> None:
    stand_in = StandInGitHub()

    def binary(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readme"):
            content = base64.b64encode(b"\xff\xfe\x00not text").decode()
            return httpx.Response(200, json={"path": "README.md", "sha": "1" * 40,
                                             "encoding": "base64", "content": content})  # fmt: skip
        return stand_in(request)

    with httpx.Client(transport=httpx.MockTransport(binary)) as http:
        with pytest.raises(github_app.GitHubAppError, match="not text"):
            github_app.add_line(http, TOKEN, "sample-org", "pebble-pay", LINE, "main")
    assert stand_in.written == []


def test_the_links_to_github_carry_what_github_asks_for() -> None:
    address = github_app.authorize_url("Iv1.standin", "https://host.test/github/callback", "s1")
    assert address.startswith("https://github.com/login/oauth/authorize?")
    asked = parse_qs(address.split("?", 1)[1])
    assert asked == {"client_id": ["Iv1.standin"], "state": ["s1"], "allow_signup": ["false"],
                     "redirect_uri": ["https://host.test/github/callback"]}  # fmt: skip
    assert github_app.install_url("jevadu-register") == (
        "https://github.com/apps/jevadu-register/installations/new")  # fmt: skip
    assert github_app.owner_and_name("https://github.com/sample-org/pebble-pay") == (
        "sample-org", "pebble-pay")  # fmt: skip


def test_a_pass_of_the_copys_owner_holds_in_time_and_for_its_own_kind_only() -> None:
    owner = github_app.owner_pass("mohamedyaakoubi", "standin-secret", 100.0)
    assert github_app.owner_of(owner, "standin-secret", 99.0) == "mohamedyaakoubi"
    assert github_app.owner_of(owner, "standin-secret", 101.0) is None  # too old
    assert github_app.owner_of(owner, "another-secret", 99.0) is None
    asked = github_app.Asked("https://github.com/sample-org/pebble-pay", "3", "", "", "s", 100.0)
    request = github_app.sealed(asked, "standin-secret")
    assert github_app.owner_of(request, "standin-secret", 99.0) is None  # another kind of cookie
    assert github_app.opened(owner, "standin-secret", 99.0) is None
    assert github_app.owner_of("é" + owner, "standin-secret", 99.0) is None


def test_the_account_of_a_token_comes_from_github() -> None:
    with http_of(StandInGitHub(login="someone-else")) as http:
        assert github_app.login_of(http, TOKEN) == "someone-else"
        with pytest.raises(github_app.GitHubAppError, match="which account"):
            github_app.login_of(http, "ghu_WRONG")
