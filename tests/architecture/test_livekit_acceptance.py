"""Harness integrity and an actual loopback signaling relay header regression."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "live_acceptance", ROOT / "scripts/ci/run_livekit_acceptance.py"
)
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def test_server_config_requires_explicit_auto_creation_policy():
    value = harness.server_config("fixture", "x" * 64, (8001, 8002, 8003), False)
    assert value["room"]["auto_create"] is False
    assert value["bind_addresses"] == ["127.0.0.1"]
    assert value["rtc"]["enable_loopback_candidate"] is True
    assert harness.server_config("k", "s", (1, 2, 3), True)["room"]["auto_create"] is True


def test_requires_actual_refreshed_token_and_all_cases():
    report = {
        "cases": [{"name": name, "passed": True} for name in harness.REQUIRED_NORMAL],
        "actual_server_refresh_observed": True,
    }
    harness.require_complete(report, "normal")
    report["actual_server_refresh_observed"] = False
    with pytest.raises(RuntimeError, match="actual_server_refresh_missing"):
        harness.require_complete(report, "normal")
    report["actual_server_refresh_observed"] = True
    report["cases"].pop()
    with pytest.raises(RuntimeError, match="incomplete"):
        harness.require_complete(report, "normal")


def test_output_never_changes_source_tree(tmp_path):
    with pytest.raises(ValueError):
        harness.external_output(ROOT, ROOT / "acceptance-results")
    assert harness.external_output(ROOT, tmp_path) == tmp_path.resolve()


def test_sanitizes_known_secrets_and_unknown_bearers():
    token = ".".join(["a" * 20, "b" * 25, "c" * 30])
    safe = harness.redact("access_token=" + token + " fixture-secret", ["fixture-secret"])
    assert token not in safe and "fixture-secret" not in safe


def test_exact_clean_source_required(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    head = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True, encoding="utf-8"
    ).strip()
    assert harness.git_identity(tmp_path, head)["clean"] is True
    with pytest.raises(RuntimeError, match="expected_head_mismatch"):
        harness.git_identity(tmp_path, "0" * 40)
    (tmp_path / "untracked").write_text("dirty", encoding="utf-8")
    with pytest.raises(RuntimeError, match="requires_clean_source"):
        harness.git_identity(tmp_path, head)


def test_official_image_is_digest_pinned():
    pin = json.loads((ROOT / "tests/acceptance/livekit/image.json").read_text(encoding="utf-8"))
    assert pin["repository"] == "livekit/livekit-server"
    assert len(pin["digest"]) == 71
    assert pin["version"] == "1.13.10"


def test_native_sdk_authorization_reaches_fixed_sfu_without_other_headers():
    import aiohttp
    from aiohttp import web

    # Load the actual relay, excluding native RTC imports from general unit CI.
    source = (ROOT / "tests/acceptance/livekit/live_protocol.py").read_text(encoding="utf-8")
    node = next(
        n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "Relay"
    )
    namespace = {"asyncio": asyncio, "aiohttp": aiohttp, "web": web, "signal": None}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<actual-relay>", "exec"), namespace)

    async def exercise():
        observed = []

        async def upstream(request):
            observed.append(
                (
                    request.path,
                    request.headers.get("Authorization"),
                    request.headers.get("X-Untrusted"),
                )
            )
            if request.path == "/denied":
                return web.Response(status=403)
            if request.headers.get("Upgrade", "").lower() == "websocket":
                ws = web.WebSocketResponse()
                await ws.prepare(request)
                async for message in ws:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await ws.send_str(message.data)
                return ws
            return web.Response(text="ok")

        app = web.Application()
        app.router.add_route("*", "/{path:.*}", upstream)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        relay = namespace["Relay"](
            "http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1])
        )
        try:
            url = await relay.start()
            headers = {
                "Authorization": "Bearer loopback-fixture",
                "X-Untrusted": "must-not-forward",
            }
            async with aiohttp.ClientSession() as client:
                async with client.get(
                    url.replace("ws:", "http:") + "/rtc/validate", headers=headers
                ) as response:
                    assert response.status == 200
                async with client.ws_connect(url + "/rtc", headers=headers) as ws:
                    await ws.send_str("fixture")
                    assert (await ws.receive()).data == "fixture"
                with pytest.raises(aiohttp.WSServerHandshakeError) as denied:
                    await client.ws_connect(url + "/denied", headers=headers)
                assert denied.value.status == 403
                assert relay.admission_rejections == [403]
            assert observed == [
                ("/rtc/validate", "Bearer loopback-fixture", None),
                ("/rtc", "Bearer loopback-fixture", None),
                ("/denied", "Bearer loopback-fixture", None),
            ]
        finally:
            await relay.close()
            await runner.cleanup()

    asyncio.run(exercise())
