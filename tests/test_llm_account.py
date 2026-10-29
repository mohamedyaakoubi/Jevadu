"""The switch of the Google account (llm/account.py), with a stand-in of gcloud. Everything is
invented."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from hackathon_memory.llm import account
from hackathon_memory.settings import Settings

EMAIL = "jevadu-gemini@p-one.iam.gserviceaccount.com"


class Gcloud:
    """What gcloud was asked, and its answers. `there` names what already exists: "account",
    "pool", "provider"; `refuse_bindings` is how many first roles fail, as for a service account
    that Google does not know everywhere yet."""

    def __init__(self, projects: Sequence[str] = ("p-one",), there: Sequence[str] = (),
                 refuse_bindings: int = 0) -> None:  # fmt: skip
        self.projects, self.there, self.refuse = list(projects), set(there), refuse_bindings
        self.asked: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        args = list(args)
        self.asked.append(args)
        if args[:2] == ["projects", "list"]:
            return "\n".join(self.projects) + "\n"
        if args[:2] == ["projects", "describe"]:
            return "123456\n"
        kinds = {"service-accounts": "account", "workload-identity-pools": "pool",
                 "providers": "provider"}  # fmt: skip
        if "describe" in args:
            kind = kinds[args[args.index("describe") - 1]]
            if kind not in self.there:
                raise account.AccountError("NOT_FOUND")
        if args[:2] == ["projects", "add-iam-policy-binding"] and self.refuse:
            self.refuse -= 1
            raise account.AccountError("Service account does not exist")
        return ""

    def commands(self) -> list[str]:
        return [" ".join(args[:5]) for args in self.asked]


def test_the_project_is_the_only_one_the_account_sees_or_the_one_named() -> None:
    assert account.choose_project(Gcloud(["p-one"]), None) == "p-one"
    assert account.choose_project(Gcloud(["p-one", "p-two"]), "p-two") == "p-two"
    with pytest.raises(account.AccountError, match="2 projects: name one with --project"):
        account.choose_project(Gcloud(["p-one", "p-two"]), None)
    with pytest.raises(account.AccountError, match="does not see"):
        account.choose_project(Gcloud(["p-one"]), "p-three")


def test_the_service_account_may_only_call_vertex_ai_and_is_made_once() -> None:
    gcloud = Gcloud(refuse_bindings=2)
    waits: list[float] = []
    assert account.make_account(gcloud, "p-one", sleep=waits.append) == EMAIL
    enabled = next(args for args in gcloud.asked if args[:2] == ["services", "enable"])
    assert enabled[2:6] == ["iam.googleapis.com", "iamcredentials.googleapis.com",
                            "sts.googleapis.com", "aiplatform.googleapis.com"]  # fmt: skip
    assert "iam service-accounts create jevadu-gemini --display-name=Jevadu: Gemini only" in (
        gcloud.commands())  # fmt: skip
    bindings = [args for args in gcloud.asked if args[:2] == ["projects", "add-iam-policy-binding"]]
    assert len(bindings) == 3 and waits == [account.PAUSE_SECONDS] * 2  # a new account waits
    assert "--role=roles/aiplatform.user" in bindings[-1] and "--condition=None" in bindings[-1]
    again = Gcloud(there=["account"])
    account.make_account(again, "p-one", sleep=waits.append)
    assert not any(args[:3] == ["iam", "service-accounts", "create"] for args in again.asked)


def test_vercel_may_act_as_the_service_account_with_no_key() -> None:
    gcloud = Gcloud()
    audience = account.trust_vercel(gcloud, "p-one", "team-x", EMAIL)
    assert audience == ("//iam.googleapis.com/projects/123456/locations/global/"
                        "workloadIdentityPools/vercel/providers/vercel")  # fmt: skip
    made = next(args for args in gcloud.asked if "create-oidc" in args)
    assert "--issuer-uri=https://oidc.vercel.com/team-x" in made
    assert "--allowed-audiences=https://vercel.com/team-x" in made
    assert "--attribute-mapping=google.subject=assertion.sub" in made
    binding = ["iam", "service-accounts", "add-iam-policy-binding"]
    bound = next(args for args in gcloud.asked if args[:3] == binding)
    assert "--role=roles/iam.workloadIdentityUser" in bound
    assert ("--member=principal://iam.googleapis.com/projects/123456/locations/global/"
            "workloadIdentityPools/vercel/subject/owner:team-x:project:jevadu:environment:"
            "production") in bound  # fmt: skip
    assert not any("keys" in args for args in gcloud.asked)  # no key, ever
    again = Gcloud(there=["pool", "provider"])
    account.trust_vercel(again, "p-one", "team-y", EMAIL)
    assert not any("create" in args for args in again.asked)  # made once
    assert any("update-oidc" in args for args in again.asked)  # the team may change


def test_the_project_goes_into_env_in_place(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    before = ("A=1\nGOOGLE_CLOUD_PROJECT=old\nB=2\nGOOGLE_CLOUD_PROJECT=again\n"
              "GOOGLE_APPLICATION_CREDENTIALS=C:/somewhere/login.json\n")  # fmt: skip
    env.write_text(before, encoding="utf-8")
    account.keep_line(env, account.PROJECT_SETTING, "p-one")
    account.keep_line(env, account.SIGN_IN_SETTING, "")
    assert env.read_text(encoding="utf-8").splitlines() == [
        "A=1",
        "GOOGLE_CLOUD_PROJECT=p-one",
        "B=2",
        "GOOGLE_APPLICATION_CREDENTIALS=",
    ]
    settings = Settings(_env_file=env)
    assert settings.google_cloud_project.get_secret_value() == "p-one"


def test_a_sign_in_is_proven_by_a_free_count_of_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    from hackathon_memory.finops import meter

    asked: list[str] = []

    class Models:
        def __init__(self, fails: int) -> None:
            self.fails = fails

        def count_tokens(self, *, model: str, contents: str) -> None:
            asked.append(model)
            if len(asked) <= self.fails:
                raise RuntimeError("PERMISSION_DENIED")  # a new role, not yet applied

    class Counted:
        def __init__(self, fails: int) -> None:
            self.models = Models(fails)

    monkeypatch.setattr(meter, "metered_client", lambda settings, purpose: Counted(2))
    waits: list[float] = []
    assert account.proven(lambda: Settings(_env_file=None), sleep=waits.append)
    assert len(asked) == 3 and len(waits) == 2
    monkeypatch.setattr(meter, "metered_client", lambda settings, purpose: Counted(99))
    assert not account.proven(lambda: Settings(_env_file=None), tries=2, sleep=waits.append)


def test_the_public_copy_follows_the_account_with_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from hackathon_memory.web import vercel

    pushed: dict = {}
    deployed: list[tuple] = []

    class Api:
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(vercel, "client", lambda token: Api())
    monkeypatch.setattr(vercel, "team", lambda api: ("team_1", "team-slug"))
    monkeypatch.setattr(vercel, "project_id", lambda api, team_id: "prj_1")
    monkeypatch.setattr(vercel, "set_values", lambda api, team_id, values: pushed.update(values))
    monkeypatch.setattr(vercel, "deploy", lambda token, team_id, project: deployed.append(
        (team_id, project)) or 0)  # fmt: skip
    monkeypatch.setattr(account, "hosted_health", lambda host: True)
    gcloud = Gcloud(there=["account"])
    account.update_host(gcloud, "p-one", EMAIL, "a-token", "jevadu.example.com")
    made = next(args for args in gcloud.asked if "create-oidc" in args)
    assert "--issuer-uri=https://oidc.vercel.com/team-slug" in made  # the token's own team
    assert pushed == {"GOOGLE_CLOUD_PROJECT": ("p-one", True),
                      "GOOGLE_FEDERATION_AUDIENCE": ("//iam.googleapis.com/projects/123456/"
                                                     "locations/global/workloadIdentityPools/"
                                                     "vercel/providers/vercel", False),
                      "GOOGLE_FEDERATION_ACCOUNT": (EMAIL, False)}  # fmt: skip
    assert deployed == [("team_1", "prj_1")]
    monkeypatch.setattr(vercel, "deploy", lambda token, team_id, project: 1)
    with pytest.raises(account.AccountError, match="deployment on Vercel failed"):
        account.update_host(Gcloud(there=["account", "pool", "provider"]), "p-one", EMAIL,
                            "a-token", "jevadu.example.com")  # fmt: skip


def test_the_copy_is_read_until_google_takes_its_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    answers = iter([{"database": True, "google": False}, {"database": True, "google": True}])

    class Answer:
        def __init__(self) -> None:
            self.data = next(answers)

        def json(self) -> dict:
            return self.data

    monkeypatch.setattr(httpx, "get", lambda url, timeout: Answer())
    waits: list[float] = []
    assert account.hosted_health("jevadu.example.com", sleep=waits.append) and waits == [10.0]
