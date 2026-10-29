"""The Cloudflare tunnel of the public copy (web/tunnel.py, design 12.5), with a stand-in of
Cloudflare's API. Everything is invented."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from hackathon_memory.settings import Settings
from hackathon_memory.web import tunnel

ACCOUNT, ZONE = "a" * 32, "z" * 32
TUNNEL_ID = "11111111-2222-3333-4444-555555555555"
HOST = "jevadu.example.com"


class Cloudflare:
    """The answers of the API, and what it was asked. `refuse` refuses every request of a method,
    as a token without the permission is refused."""

    def __init__(self, records: list[dict] | None = None, refuse: str | None = None) -> None:
        self.tunnels: list[dict] = []
        self.records = list(records or [])
        self.refuse = refuse
        self.asked: list[tuple[str, str]] = []
        self.config: dict = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path.removeprefix("/client/v4"), request.method
        self.asked.append((method, path))
        if method == self.refuse:
            return httpx.Response(403, json={"success": False, "errors": [
                {"code": 10000, "message": "Authentication error"}]})  # fmt: skip
        result: object = None
        if path == "/zones":
            result = [{"id": ZONE, "name": "example.com"}]
        elif path.endswith("/cfd_tunnel"):
            if method == "POST":
                self.tunnels.append({"id": TUNNEL_ID, "name": json.loads(request.content)["name"]})
                result = self.tunnels[-1]
            else:
                result = self.tunnels
        elif path.endswith("/configurations"):
            self.config, result = json.loads(request.content), {}
        elif path.endswith("/dns_records"):
            if method == "POST":
                self.records.append(json.loads(request.content))
            result = self.records if method == "GET" else {}
        elif path.endswith("/token"):
            result = "eyJ-a-tunnel-token"
        return httpx.Response(200, json={"success": True, "result": result})


def api(cloudflare: Cloudflare) -> httpx.Client:
    return httpx.Client(base_url=tunnel.API, transport=httpx.MockTransport(cloudflare))


def test_the_setup_makes_the_tunnel_its_route_and_its_name_once() -> None:
    cloudflare = Cloudflare()
    assert tunnel.setup(api(cloudflare), ACCOUNT, HOST, 8020) == "eyJ-a-tunnel-token"
    assert cloudflare.config["config"]["ingress"] == [
        {"hostname": HOST, "service": "http://127.0.0.1:8020"},
        {"service": "http_status:404"},
    ]
    (record,) = cloudflare.records
    assert (record["type"], record["content"], record["proxied"]) == (
        "CNAME", f"{TUNNEL_ID}.cfargotunnel.com", True)  # fmt: skip
    before = len(cloudflare.asked)
    tunnel.setup(api(cloudflare), ACCOUNT, HOST, 8020)  # again: found, nothing made twice
    assert len(cloudflare.tunnels) == 1 and len(cloudflare.records) == 1
    assert ("POST", f"/accounts/{ACCOUNT}/cfd_tunnel") not in cloudflare.asked[before:]


def test_a_name_that_points_elsewhere_is_never_replaced() -> None:
    cloudflare = Cloudflare(records=[{"type": "A", "content": "192.0.2.1"}])
    with pytest.raises(tunnel.TunnelError, match="points elsewhere"):
        tunnel.setup(api(cloudflare), ACCOUNT, HOST, 8020)
    assert cloudflare.records == [{"type": "A", "content": "192.0.2.1"}]


def test_a_refusal_says_what_was_refused_and_never_the_account() -> None:
    """Matafi's token could read tunnels but not make one (30 October 2026)."""
    with pytest.raises(tunnel.TunnelError) as refused:
        tunnel.setup(api(Cloudflare(refuse="POST")), ACCOUNT, HOST, 8020)
    assert "Authentication error" in str(refused.value) and ACCOUNT not in str(refused.value)


def test_the_token_is_kept_in_env_and_never_on_the_command_line(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\nCLOUDFLARE_TUNNEL_TOKEN=old\n", encoding="utf-8")
    tunnel.keep_token(env, "new-token")
    kept = env.read_text(encoding="utf-8")
    assert kept.startswith("A=1\n") and kept.count("CLOUDFLARE_TUNNEL_TOKEN=") == 1
    assert "CLOUDFLARE_TUNNEL_TOKEN=new-token" in kept
    settings = Settings(_env_file=None, cloudflare_tunnel_token=SecretStr("new-token"),
                        cloudflared_path="C:/tools/cloudflared.exe")  # fmt: skip
    site, run, environment = tunnel.commands(settings)
    assert site[1:] == ["-m", "hackathon_memory.web", "--public", "--port", "8020"]
    assert run == ["C:/tools/cloudflared.exe", "tunnel", "--no-autoupdate", "run"]
    assert environment["TUNNEL_TOKEN"] == "new-token" and "new-token" not in " ".join(site + run)
    with pytest.raises(tunnel.TunnelError, match="run the setup first"):
        tunnel.commands(Settings(_env_file=None))
