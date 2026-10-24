"""Actual native RTC/SFU probes. Private config and tokens stay outside artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import aiohttp
import httpx
import jwt
from aiohttp import web
from cryptography.hazmat.primitives.asymmetric import rsa
from livekit import rtc
from livekit.protocol import rtc as signal

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/realtime-session"))
from realtime_session.contracts import SessionError  # noqa: E402
from realtime_session.engine import SessionService  # noqa: E402
from realtime_session.livekit_adapter import LiveKitGateway  # noqa: E402
from realtime_session.platform import PlatformAuthority  # noqa: E402
from realtime_session.store import SessionStore  # noqa: E402


class Relay:
    """Forward native SDK Authorization only to the fixed loopback SFU origin.

    The SDK uses a header, not necessarily an access_token query parameter.
    Both /rtc validation HTTP and binary WebSocket signaling retain that header.
    No Cookie, arbitrary upstream URL or caller tenant header is forwarded.
    """

    def __init__(self, upstream: str):
        self.upstream = upstream
        self.refreshed = asyncio.get_running_loop().create_future()
        self.client = None
        self.runner = None
        self.admission_rejections = []

    async def start(self) -> str:
        self.client = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))
        app = web.Application(client_max_size=65536)
        app.router.add_route("*", "/{path:.*}", self.handle)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        return f"ws://127.0.0.1:{port}"

    async def handle(self, request):
        target = self.upstream + request.path_qs
        headers = {}
        if request.headers.get("Authorization"):
            headers["Authorization"] = request.headers["Authorization"]
        if request.headers.get("Upgrade", "").lower() != "websocket":
            async with self.client.request(
                request.method, target, headers=headers, allow_redirects=False
            ) as upstream:
                if upstream.status in {401, 403, 404}:
                    self.admission_rejections.append(upstream.status)
                return web.Response(status=upstream.status, body=await upstream.read())
        try:
            remote = await self.client.ws_connect(
                target, headers=headers, max_msg_size=8 * 1024 * 1024
            )
        except aiohttp.WSServerHandshakeError as exc:
            if exc.status in {401, 403, 404}:
                self.admission_rejections.append(exc.status)
            return web.Response(status=exc.status)
        async with remote:
            local = web.WebSocketResponse(max_msg_size=8 * 1024 * 1024)
            await local.prepare(request)

            async def forward(source, destination, capture=False):
                async for message in source:
                    if message.type == aiohttp.WSMsgType.BINARY:
                        if capture:
                            response = signal.SignalResponse()
                            response.ParseFromString(message.data)
                            if (
                                response.WhichOneof("message") == "refresh_token"
                                and response.refresh_token
                            ):
                                if not self.refreshed.done():
                                    self.refreshed.set_result(response.refresh_token)
                        await destination.send_bytes(message.data)
                    elif message.type == aiohttp.WSMsgType.TEXT:
                        await destination.send_str(message.data)
                await destination.close()

            tasks = [
                asyncio.create_task(forward(local, remote)),
                asyncio.create_task(forward(remote, local, True)),
            ]
            try:
                await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            return local

    async def close(self):
        if self.runner:
            await self.runner.cleanup()
        if self.client:
            await self.client.close()


async def join(url: str, token: str):
    room = rtc.Room()
    try:
        await asyncio.wait_for(room.connect(url, token), 20)
        return room
    except BaseException:
        await room.disconnect()
        raise


async def denied_join(url: str, token: str, relay: Relay) -> bool:
    before = len(relay.admission_rejections)
    try:
        room = await join(url, token)
    except rtc.ConnectError:
        # A timeout, ICE problem or proxy500 must never count as admission denial.
        return len(relay.admission_rejections) > before
    await room.disconnect()
    return False


def claims(token: str, key: str, secret: str):
    return jwt.decode(token, secret, algorithms=["HS256"], issuer=key)


async def normal(config: dict) -> dict:
    cases = []

    def passed(name, condition=True):
        if not condition:
            raise RuntimeError("probe_failed_" + name)
        cases.append({"name": name, "passed": True})

    private = Path(config["private"])
    key, secret, origin = config["key"], config["secret"], config["url"]
    # Cryptographically authenticated fixture HTTP authority, deliberately NOT
    # deployed SAHOOL or a proof that PostgreSQL tenant RLS is operational.
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tokens = {
        tenant: jwt.encode(
            {
                "sub": "user-" + tenant,
                "tenant_id": tenant,
                "aud": "sahool",
                "iss": "synthetic-fixture",
                "exp": int(time.time()) + 300,
            },
            rsa_key,
            algorithm="RS256",
        )
        for tenant in ("a", "b")
    }

    def platform(request):
        try:
            bearer = request.headers["authorization"].removeprefix("Bearer ")
            principal = jwt.decode(
                bearer,
                rsa_key.public_key(),
                algorithms=["RS256"],
                audience="sahool",
                issuer="synthetic-fixture",
            )
        except Exception:
            return httpx.Response(401)
        tenant = principal["tenant_id"]
        if request.url.path == "/api/v1/me":
            return httpx.Response(
                200,
                json={
                    "tenant_id": tenant,
                    "user_id": principal["sub"],
                    "ai_policy_envelope": {
                        "tenant_id": tenant,
                        "contract": "sahool.ai_policy_envelope",
                        "contract_version": 2,
                        "allowed_tools": [],
                    },
                },
            )
        field = request.url.path.rsplit("/", 1)[-1]
        return (
            httpx.Response(200, json={"field_id": field})
            if field == "field-" + tenant
            else httpx.Response(403)
        )

    gateway = LiveKitGateway(origin, key, secret)
    store = SessionStore(private / "sessions.sqlite")
    await store.initialize()
    relay = Relay(origin)
    rooms = []
    try:
        url = await relay.start()
        async with httpx.AsyncClient(transport=httpx.MockTransport(platform)) as client:
            authority = PlatformAuthority("http://sahool-platform:8000", client)
            service = SessionService(authority, store, gateway, url, session_ttl=180, token_ttl=60)
            try:
                await service.create(tokens["a"], "field-b", True)
            except SessionError as exc:
                passed("field_authorization_denied", exc.status == 403)
            else:
                raise RuntimeError("cross_tenant_field_accepted")
            a = await service.create(tokens["a"], "field-a", True)
            b = await service.create(tokens["b"], "field-b", True)
            sa = await store.get(a["session_id"])
            sb = await store.get(b["session_id"])
            passed("tenant_rooms_isolated", sa.room_name != sb.room_name)
            try:
                await service.get(tokens["b"], a["session_id"])
            except SessionError as exc:
                passed("tenant_ownership_denied", exc.status == 404)
            else:
                raise RuntimeError("cross_tenant_session_read")
            room_a = await join(url, a["participant_token"])
            rooms.append(room_a)
            passed("initial_join", room_a.name == sa.room_name)
            refreshed = await asyncio.wait_for(asyncio.shield(relay.refreshed), 35)
            initial_claims = claims(a["participant_token"], key, secret)
            refreshed_claims = claims(refreshed, key, secret)
            passed(
                "actual_refreshed_token",
                refreshed != a["participant_token"]
                and refreshed_claims["exp"] > initial_claims["exp"]
                and refreshed_claims["sub"] == initial_claims["sub"]
                and refreshed_claims["video"]["room"] == sa.room_name,
            )
            room_b = await join(origin.replace("http:", "ws:"), b["participant_token"])
            rooms.append(room_b)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as http:
                for service_name, method, body, case in [
                    ("RoomService", "DeleteRoom", {"room": sb.room_name}, "room_admin_denied"),
                    (
                        "AgentDispatchService",
                        "CreateDispatch",
                        {"room": sa.room_name, "agent_name": "sahool-agronomist"},
                        "agent_dispatch_denied",
                    ),
                ]:
                    async with http.post(
                        origin + f"/twirp/livekit.{service_name}/{method}",
                        json=body,
                        headers={"Authorization": "Bearer " + a["participant_token"]},
                    ) as response:
                        passed(case, response.status in {401, 403})
            await service.close(tokens["a"], a["session_id"])
            await room_a.disconnect()
            if initial_claims["exp"] <= int(time.time()) + 5:
                raise RuntimeError("fresh_admission_probe_too_late")
            passed(
                "fresh_rejoin_after_delete_denied",
                await denied_join(url, a["participant_token"], relay),
            )
            passed("refreshed_rejoin_after_delete_denied", await denied_join(url, refreshed, relay))
            passed(
                "other_tenant_survives_delete",
                room_b.connection_state == rtc.ConnectionState.CONN_CONNECTED,
            )
            # Private handoff crosses server restart solely to prove the control
            # counterexample. It is never placed in the uploaded receipt directory.
            (private / "refresh.json").write_text(
                json.dumps({"token": refreshed, "room": sa.room_name}), encoding="utf-8"
            )
            await service.close(tokens["b"], b["session_id"])
        return {
            "cases": cases,
            "actual_server_refresh_observed": True,
            "authority": "synthetic RS256 HTTP fixture, not deployed Platform RLS",
        }
    finally:
        for room in rooms:
            await room.disconnect()
        await relay.close()
        await gateway.close()


async def mutation(config: dict):
    handoff = json.loads((Path(config["private"]) / "refresh.json").read_text(encoding="utf-8"))
    room = await join(config["url"].replace("http:", "ws:"), handoff["token"])
    try:
        if room.name != handoff["room"]:
            raise RuntimeError("counterexample_wrong_room")
        return {"cases": [{"name": "auto_create_true_refreshed_rejoin_succeeds", "passed": True}]}
    finally:
        await room.disconnect()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("normal", "mutation"), required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    report = await (normal(config) if args.mode == "normal" else mutation(config))
    args.receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        code = (
            str(error)
            if isinstance(error, RuntimeError) and re.fullmatch(r"[a-z0-9_]+", str(error))
            else type(error).__name__
        )
        print("Native SFU acceptance failed: " + code, file=sys.stderr)
        raise SystemExit(1) from None
