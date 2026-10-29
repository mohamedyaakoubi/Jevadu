"""The public copy on Vercel (web/vercel_app.py, design 12.5): the data folder in /tmp, a check
within its request, the visitor's address that Vercel writes, and the token of each request for
the sign-in to Google with no key. Everything is invented."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import SecretStr
from test_web import HX, REPO, checkable, site  # noqa: F401  (the fixture of the website's tests)

from hackathon_memory.llm.client import vercel_token
from hackathon_memory.search import engine
from hackathon_memory.web import public, vercel_app


def can_link(folder: Path) -> bool:
    """Windows makes links only with a privilege; Vercel's Linux always can."""
    try:
        (folder / "link-probe").symlink_to(folder)
    except OSError:
        return False
    (folder / "link-probe").unlink()
    return True


def test_the_data_folder_links_the_saved_files_and_takes_new_ones(tmp_path: Path) -> None:
    if not can_link(tmp_path):
        pytest.skip("this computer makes no links without a privilege")
    bundled, writable = tmp_path / "deployment" / "data", tmp_path / "tmp" / "jevadu-data"
    (bundled / "raw" / "api.github.com").mkdir(parents=True)
    (bundled / "raw" / "api.github.com" / "readme.json").write_text("saved", encoding="utf-8")
    (bundled / "requests").mkdir()
    (bundled / "requests" / "api.github.com.json").write_text('{"count": 3}', encoding="utf-8")
    (bundled / "review").mkdir()  # not needed by the site, never made
    made = vercel_app.data_folder(bundled, writable)
    saved = made / "raw" / "api.github.com" / "readme.json"
    assert saved.is_symlink() and saved.read_text(encoding="utf-8") == "saved"
    (saved.parent / "new-answer.json").write_text("new", encoding="utf-8")  # beside the links
    count = made / "requests" / "api.github.com.json"
    assert not count.is_symlink()
    count.write_text('{"count": 4}', encoding="utf-8")  # a copy: the deployment's stays as it was
    assert (bundled / "requests" / "api.github.com.json").read_text(encoding="utf-8") == (
        '{"count": 3}')  # fmt: skip
    assert not (made / "review").exists()
    assert vercel_app.data_folder(bundled, writable) == made  # a second start keeps it


def test_the_module_makes_no_site_outside_vercel() -> None:
    assert os.environ.get("VERCEL") is None and vercel_app.app is None


def test_a_check_runs_within_its_request_on_serverless(site) -> None:  # noqa: ANN001, F811
    """A request may land on any copy of the site, so no check waits in another one."""
    client, _, _, database = site
    hosted = client.make(app_options={"serverless": True})
    asked = {"repo": REPO, "event": checkable(database), "progress": "1"}
    part = hosted.get("/check", params=asked, headers=HX)
    assert part.status_code == 200 and "Proof: found" in part.text  # the answer, not its steps
    steps = client.get("/check", params=asked, headers=HX)  # the laptop's site shows the steps
    assert "Proof: found" not in steps.text


def test_the_visitor_is_the_address_that_vercel_writes() -> None:
    headers = {"x-vercel-forwarded-for": "203.0.113.5", "cf-connecting-ip": "198.51.100.7",
               "user-agent": "Firefox"}  # fmt: skip
    vercel = public.visitor_of(headers, None, "s" * 40, "x-vercel-forwarded-for")
    assert vercel == public.visitor_of({"user-agent": "Firefox"}, "203.0.113.5", "s" * 40)
    assert vercel != public.visitor_of(headers, None, "s" * 40)  # Cloudflare's, for the tunnel


def test_each_request_carries_its_token_of_vercel_to_the_sign_in(site, monkeypatch) -> None:  # noqa: ANN001, F811
    client, _, _, database = site
    seen: list[str | None] = []

    def by_meaning(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        seen.append(vercel_token.get())
        return []

    monkeypatch.setattr(engine, "by_meaning", by_meaning)
    public.turn(database, public.AI, True)
    hosted = client.make(app_options={"public": True, "serverless": True},
                         public_salt=SecretStr("s" * 40))  # fmt: skip
    hosted.get("/", params={"idea": "pay a vendor in coins", "mode": "meaning"},
               headers={"x-vercel-oidc-token": "token-of-this-request"})  # fmt: skip
    hosted.get("/", params={"idea": "pay a vendor in coins", "mode": "meaning"})
    assert seen[0] == "token-of-this-request" and seen[-1] is None
    assert vercel_token.get() is None  # never left behind


def test_the_health_says_what_the_site_reaches_and_asks_no_model(site) -> None:  # noqa: ANN001, F811
    client, fake, _, _ = site
    asked = len(fake.requests)
    assert client.get("/health").json() == {"database": True, "google": None}  # the laptop's
    audience = ("//iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/vercel/"
                "providers/vercel")  # fmt: skip
    account = "jevadu-gemini@p.iam.gserviceaccount.com"
    hosted = client.make(google_federation_audience=audience, google_federation_account=account)
    answer = hosted.get("/health")  # no token of Vercel with this request: Google is never asked
    assert answer.status_code == 200 and answer.json() == {"database": True, "google": False}
    assert len(fake.requests) == asked  # no model was asked
