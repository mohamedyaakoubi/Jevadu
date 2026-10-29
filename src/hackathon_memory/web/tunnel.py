"""The Cloudflare tunnel of the public copy (design 12.5, 30 October 2026).

    python -m hackathon_memory.web.tunnel setup   once: the tunnel "jevadu", its route to the
                                                  public copy and the name in PUBLIC_HOST; the
                                                  tunnel's token is kept in .env
    python -m hackathon_memory.web.tunnel run     the public copy and the tunnel together; Ctrl+C
                                                  stops both

A tunnel is an outgoing connection from this computer to Cloudflare, which brings the visitors of
PUBLIC_HOST to the public copy on 127.0.0.1:PUBLIC_PORT: no port of the computer is opened, and
nothing of the collection leaves it. It needs, in .env, CLOUDFLARE_API_TOKEN, a token with two
permissions (Account, Cloudflare Tunnel, Edit; Zone, DNS, Edit, for the zone of PUBLIC_HOST), and
CLOUDFLARE_ACCOUNT_ID; and the program cloudflared (CLOUDFLARED_PATH, by default
.local-tools/cloudflared/cloudflared.exe or the one on the PATH).

The API's shapes, read on 30 October 2026 at developers.cloudflare.com: POST
/accounts/{account}/cfd_tunnel with config_src "cloudflare" makes a tunnel whose routes Cloudflare
keeps; PUT .../configurations sets its ingress; GET .../token gives the token that `cloudflared
tunnel run` reads from TUNNEL_TOKEN; the name is a proxied CNAME to {id}.cfargotunnel.com.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx

from hackathon_memory.settings import Settings

API = "https://api.cloudflare.com/client/v4"
NAME = "jevadu"
ROOT = Path(__file__).resolve().parents[3]  # the project folder
LOCAL_CLOUDFLARED = ROOT / ".local-tools" / "cloudflared" / "cloudflared.exe"
TOKEN_KEY = "CLOUDFLARE_TUNNEL_TOKEN"  # noqa: S105  (the name of a line of .env, not a secret)


class TunnelError(Exception):
    """What stopped the setup, in plain words, with no secret in them."""


def _call(api: httpx.Client, method: str, path: str, account: str, **options: object) -> object:
    answer = api.request(method, path, **options).json()
    if not answer.get("success"):
        errors = [(one.get("code"), one.get("message")) for one in answer.get("errors", [])]
        shown = path.split("?")[0].replace(account, "<account>")
        raise TunnelError(f"Cloudflare refused {method} {shown}: {errors}")
    return answer["result"]


def setup(api: httpx.Client, account: str, host: str, port: int) -> str:
    """Make, or find again, the tunnel of `host` with its route to the public copy and its name;
    the tunnel's token. Refuses a name that already points elsewhere: it is never replaced."""
    zone_name = host.split(".", 1)[1]
    zones = _call(api, "GET", f"/zones?name={zone_name}", account)
    if not zones:
        raise TunnelError(f"The zone {zone_name} is not in this Cloudflare account.")
    zone = zones[0]["id"]
    found = _call(api, "GET", f"/accounts/{account}/cfd_tunnel?name={NAME}&is_deleted=false",
                  account)  # fmt: skip
    tunnel = found[0] if found else _call(
        api, "POST", f"/accounts/{account}/cfd_tunnel", account,
        json={"name": NAME, "config_src": "cloudflare"})  # fmt: skip
    target = f"{tunnel['id']}.cfargotunnel.com"
    _call(api, "PUT", f"/accounts/{account}/cfd_tunnel/{tunnel['id']}/configurations", account,
          json={"config": {"ingress": [{"hostname": host, "service": f"http://127.0.0.1:{port}"},
                                       {"service": "http_status:404"}]}})  # fmt: skip
    records = _call(api, "GET", f"/zones/{zone}/dns_records?name={host}", account)
    if records and not (records[0]["type"] == "CNAME" and records[0]["content"] == target):
        raise TunnelError(f"{host} already has a DNS record of type {records[0]['type']} that "
                          "points elsewhere: it was left as it is.")  # fmt: skip
    if not records:
        _call(api, "POST", f"/zones/{zone}/dns_records", account,
              json={"type": "CNAME", "name": host, "content": target, "proxied": True,
                    "comment": "Jevadu public copy, through a Cloudflare tunnel"})  # fmt: skip
    return str(_call(api, "GET", f"/accounts/{account}/cfd_tunnel/{tunnel['id']}/token", account))


def keep_token(env: Path, token: str) -> None:
    """Write the tunnel's token into .env, in place of an older one; the rest is kept as it is."""
    lines = [line for line in env.read_text(encoding="utf-8").splitlines()
             if not line.startswith(f"{TOKEN_KEY}=")]  # fmt: skip
    lines += ["# The token of the Cloudflare tunnel of the public copy (web/tunnel.py).",
              f"{TOKEN_KEY}={token}"]  # fmt: skip
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")


def commands(settings: Settings) -> tuple[list[str], list[str], dict[str, str]]:
    """The two programs of `run` and the environment of the tunnel's: its token travels in
    TUNNEL_TOKEN, never on the command line, which any program of the computer can read."""
    token = settings.cloudflare_tunnel_token.get_secret_value().strip()
    if not token:
        raise TunnelError(f"{TOKEN_KEY} is empty in .env: run the setup first.")
    program = settings.cloudflared_path.strip() or (
        str(LOCAL_CLOUDFLARED) if LOCAL_CLOUDFLARED.exists() else shutil.which("cloudflared")
    )
    if not program:
        raise TunnelError("The program cloudflared was not found: set CLOUDFLARED_PATH in .env.")
    site = [sys.executable, "-m", "hackathon_memory.web", "--public",
            "--port", str(settings.public_port)]  # fmt: skip
    tunnel = [program, "tunnel", "--no-autoupdate", "run"]
    return site, tunnel, {**os.environ, "TUNNEL_TOKEN": token}


def main(argv: Sequence[str]) -> int:
    settings = Settings()
    try:
        if list(argv) == ["setup"]:
            token = settings.cloudflare_api_token.get_secret_value().strip()
            account = settings.cloudflare_account_id.strip()
            if not token or not account:
                raise TunnelError("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are needed in "
                                  ".env.")  # fmt: skip
            with httpx.Client(base_url=API, timeout=30,
                              headers={"Authorization": f"Bearer {token}"}) as api:  # fmt: skip
                made = setup(api, account, settings.public_host, settings.public_port)
            keep_token(ROOT / ".env", made)
            print(f"The tunnel is ready: {settings.public_host} goes to 127.0.0.1:"
                  f"{settings.public_port}. Start it with: python -m hackathon_memory.web.tunnel "
                  "run")  # fmt: skip
            return 0
        if list(argv) == ["run"]:
            site, tunnel, env = commands(settings)
            running = [subprocess.Popen(site), subprocess.Popen(tunnel, env=env)]  # noqa: S603
            print(f"The public copy is at https://{settings.public_host}. Stop with Ctrl+C.")
            try:
                running[0].wait()
            except KeyboardInterrupt:
                pass
            finally:
                for one in running:
                    one.terminate()
            return 0
    except (TunnelError, httpx.HTTPError) as error:
        print(error)
        return 1
    print("usage: python -m hackathon_memory.web.tunnel setup|run")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
