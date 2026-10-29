"""The switch of the Google account (llm/account.py), with a stand-in of gcloud. Everything is
invented; the key is made for the test."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from test_llm_client import throwaway_key

from hackathon_memory.llm import account
from hackathon_memory.llm.client import project_of, service_account_key
from hackathon_memory.settings import Settings

EMAIL = "jevadu-gemini@p-one.iam.gserviceaccount.com"


class Gcloud:
    """What gcloud was asked, and its answers: `exists` says if the service account is there,
    `refuse_bindings` how many first bindings fail, as for a service account not yet known."""

    def __init__(self, projects: Sequence[str] = ("p-one",), exists: bool = False,
                 refuse_bindings: int = 0, older: Sequence[str] = ("old-1", "old-2"),
                 ) -> None:  # fmt: skip
        self.projects, self.exists, self.refuse = list(projects), exists, refuse_bindings
        self.older = list(older)
        self.asked: list[list[str]] = []
        self.key = {**throwaway_key("p-one"), "private_key_id": "new-1"}

    def __call__(self, args: Sequence[str]) -> str:
        args = list(args)
        self.asked.append(args)
        if args[:2] == ["projects", "list"]:
            return "\n".join(self.projects) + "\n"
        if args[:3] == ["iam", "service-accounts", "describe"] and not self.exists:
            raise account.AccountError("NOT_FOUND")
        if args[:2] == ["projects", "add-iam-policy-binding"] and self.refuse:
            self.refuse -= 1
            raise account.AccountError("Service account does not exist")
        if args[:4] == ["iam", "service-accounts", "keys", "create"]:
            Path(args[4]).write_text(json.dumps(self.key), encoding="utf-8")
        if args[:4] == ["iam", "service-accounts", "keys", "list"]:
            keys = [*self.older, "new-1"]
            return "\n".join(f"projects/p-one/serviceAccounts/{EMAIL}/keys/{k}" for k in keys)
        return ""

    def commands(self) -> list[str]:
        return [" ".join(args[:4]) for args in self.asked]


def test_the_project_is_the_only_one_the_account_sees_or_the_one_named() -> None:
    assert account.choose_project(Gcloud(["p-one"]), None) == "p-one"
    assert account.choose_project(Gcloud(["p-one", "p-two"]), "p-two") == "p-two"
    with pytest.raises(account.AccountError, match="2 projects: name one with --project"):
        account.choose_project(Gcloud(["p-one", "p-two"]), None)
    with pytest.raises(account.AccountError, match="does not see"):
        account.choose_project(Gcloud(["p-one"]), "p-three")


def test_the_key_may_only_call_vertex_ai_and_its_older_keys_are_deleted() -> None:
    gcloud = Gcloud(refuse_bindings=2)
    waits: list[float] = []
    key = account.make_key(gcloud, "p-one", sleep=waits.append)
    assert key["private_key_id"] == "new-1"
    assert gcloud.commands()[:4] == ["config set project p-one",
                                     "services enable iam.googleapis.com aiplatform.googleapis.com",
                                     f"iam service-accounts describe {EMAIL}",
                                     "iam service-accounts create jevadu-gemini"]  # fmt: skip
    bindings = [args for args in gcloud.asked if args[:2] == ["projects", "add-iam-policy-binding"]]
    assert len(bindings) == 3 and waits == [account.PAUSE_SECONDS] * 2  # a new account waits
    assert "--role=roles/aiplatform.user" in bindings[-1] and "--condition=None" in bindings[-1]
    deleted = [args[4] for args in gcloud.asked if args[:4] == ["iam", "service-accounts", "keys",
                                                                 "delete"]]  # fmt: skip
    assert deleted == ["old-1", "old-2"]  # never the new one
    again = Gcloud(exists=True, older=())
    account.make_key(again, "p-one", sleep=waits.append)
    assert "iam service-accounts create jevadu-gemini" not in again.commands()  # made once


def test_the_key_goes_into_env_on_one_line_and_the_client_reads_it(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\nGOOGLE_SERVICE_ACCOUNT_KEY=old\nB=2\nGOOGLE_SERVICE_ACCOUNT_KEY=again\n",
                   encoding="utf-8")  # fmt: skip
    key = throwaway_key("p-one")
    account.keep_line(env, account.KEY_SETTING, account.line_of(key))
    account.keep_line(env, account.PROJECT_SETTING, "p-one")
    lines = env.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "A=1" and lines[1].startswith("GOOGLE_SERVICE_ACCOUNT_KEY=")
    assert lines[2:] == ["B=2", "GOOGLE_CLOUD_PROJECT=p-one"]  # one line each, in place
    settings = Settings(_env_file=env)
    assert service_account_key(settings) == key and project_of(settings) == "p-one"


def test_a_key_is_proven_by_a_free_count_of_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    from hackathon_memory.finops import meter

    asked: list[str] = []

    class Models:
        def __init__(self, fails: int) -> None:
            self.fails = fails

        def count_tokens(self, *, model: str, contents: str) -> None:
            asked.append(model)
            if len(asked) <= self.fails:
                raise RuntimeError("PERMISSION_DENIED")  # a new key, not yet known

    class Counted:
        def __init__(self, fails: int) -> None:
            self.models = Models(fails)

    monkeypatch.setattr(meter, "metered_client", lambda settings, purpose: Counted(2))
    waits: list[float] = []
    assert account.proven(lambda: Settings(_env_file=None), sleep=waits.append)
    assert len(asked) == 3 and len(waits) == 2
    monkeypatch.setattr(meter, "metered_client", lambda settings, purpose: Counted(99))
    assert not account.proven(lambda: Settings(_env_file=None), tries=2, sleep=waits.append)
