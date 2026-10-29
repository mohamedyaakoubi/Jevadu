"""The public copy's project on Vercel, from this computer (design 12.5, 29 October 2026): its
team, its settings and a new deployment, for `python -m hackathon_memory.llm.account switch`.

Vercel's REST API, read on 29 October 2026 at vercel.com/docs/rest-api: GET /v2/user gives the
default team, GET /v2/teams/{id} its slug, POST /v10/projects/{project}/env?upsert=true sets a
variable. A deployment is made with Vercel's own CLI, 64.2.0, from this folder: a redeployment
through the API keeps the variables of the deployment it copies, and a new account needs the new
ones. The token travels in VERCEL_TOKEN, never on a command line, and no value is printed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

import httpx

API = "https://api.vercel.com"
PROJECT = "jevadu"
CLI = ("npx", "--yes", "vercel@64.2.0")
ROOT = Path(__file__).resolve().parents[3]  # the project folder


class VercelError(Exception):
    """What Vercel refused, in plain words, with no secret in them."""


def client(token: str) -> httpx.Client:
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {token}"}, timeout=60)


def _answer(response: httpx.Response) -> dict:
    if response.is_success:
        return response.json()
    try:
        said = response.json().get("error", {}).get("message", "")
    except ValueError:
        said = ""
    raise VercelError(f"Vercel refused {response.request.method} {response.request.url.path}: "
                      f"{response.status_code} {said}".strip())  # fmt: skip


def team(api: httpx.Client) -> tuple[str, str]:
    """The id and the slug of the default team of the token's user: the slug names the issuer of
    its tokens (https://oidc.vercel.com/{slug})."""
    team_id = _answer(api.get("/v2/user"))["user"]["defaultTeamId"]
    return team_id, _answer(api.get(f"/v2/teams/{team_id}"))["slug"]


def project_id(api: httpx.Client, team_id: str, name: str = PROJECT) -> str:
    return _answer(api.get(f"/v9/projects/{name}", params={"teamId": team_id}))["id"]


def set_values(api: httpx.Client, team_id: str, values: Mapping[str, tuple[str, bool]],
               name: str = PROJECT) -> None:  # fmt: skip
    """Set each variable of production, in place of an older one; a secret one is "sensitive",
    which Vercel never shows again."""
    for key, (value, secret) in values.items():
        _answer(api.post(f"/v10/projects/{name}/env", params={"teamId": team_id, "upsert": "true"},
                         json={"key": key, "value": value, "target": ["production"],
                               "type": "sensitive" if secret else "encrypted"}))  # fmt: skip


def deploy(token: str, team_id: str, project: str) -> int:
    """A new deployment of production, from this folder, with the project's variables as they are
    now. The exit code of the CLI."""
    installed = Path(os.environ.get("ProgramFiles", "")) / "nodejs" / "npx.cmd"
    npx = shutil.which("npx") or str(installed)
    environment = {**os.environ, "VERCEL_TOKEN": token, "VERCEL_ORG_ID": team_id,
                   "VERCEL_PROJECT_ID": project}  # fmt: skip
    command = [npx, *CLI[1:], "deploy", "--prod", "--yes", "--archive=tgz", "--non-interactive"]
    done = subprocess.run(command, cwd=ROOT, env=environment, check=False)  # noqa: S603
    return done.returncode
