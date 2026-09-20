"""Exercise the canonical v9 gateway with real nginx, TLS, DNS and HTTP fixtures.

Run with --docker (the exact Compose image), or --nginx /path/to/nginx >= 1.27.3.
Only listener addresses, service ports, template values and filesystem paths are
adapted. Auth, URI rewriting, ACLs, resolver timing and the actual route bodies
remain intact. This proves the gateway config, not the deployed v25 stack.
Missing Docker/nginx/openssl is a failure, not a skipped success.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import importlib.util
import json
import os
import re
import socket
import ssl
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "frontend_nginx_fixtures", ROOT / "frontend/tests/test_nginx_runtime.py"
)
assert _SPEC is not None and _SPEC.loader is not None
fixtures = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fixtures)


def unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class GatewayBackendHandler(fixtures.BackendHandler):
    def send_header(self, keyword, value):
        # Exercise nginx's existing default proxy_redirect against its named origin.
        if keyword.lower() == "location":
            origin = f"http://{self.server.service}:{self.server.server_port}"
            value = value.replace(origin, f"http://{self.server.upstream_name}", 1)
        super().send_header(keyword, value)


class GatewayRuntime(unittest.TestCase):
    command = None
    config = ROOT / "nginx/nginx.v9.conf"

    def request(
        self, path, headers=None, method="GET", body=None, *, secure=True, source_address=None
    ):
        if secure:
            # The fixture certificate is generated for this test only.
            connection = http.client.HTTPSConnection(
                "127.0.0.1",
                self.https_port,
                timeout=3,
                context=ssl._create_unverified_context(),
                source_address=source_address,
            )
        else:
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.http_port, timeout=3, source_address=source_address
            )
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def eventually(self, predicate, description):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            self.assertIsNone(self.process.poll(), self.log.read_text(encoding="utf-8"))
            try:
                if predicate():
                    return
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(0.1)
        self.fail(f"Timed out: {description}\n{self.log.read_text(encoding='utf-8')[-6000:]}")

    def test_cold_start_auth_isolation_routing_and_replacement(self):
        with contextlib.ExitStack() as cleanup:
            directory = Path(cleanup.enter_context(tempfile.TemporaryDirectory()))
            dns = fixtures.serve(fixtures.DNSFixture(), cleanup)
            source = self.config.read_text(encoding="utf-8")
            uncommented = re.sub(r"#[^\n]*", "", source)
            services = dict(re.findall(r"\bserver\s+(sahool-[\w-]+):(\d+)\b", uncommented))
            self.assertTrue(services, "no gateway backends parsed")
            backends = {}
            for name, group in re.findall(r"upstream\s+(\w+)\s*\{([^{}]*)\}", uncommented):
                host = re.search(r"\bserver\s+(sahool-[\w-]+):\d+\b", group)[1]
                backend = fixtures.Backend(host)
                backend.upstream_name = name
                backend.RequestHandlerClass = GatewayBackendHandler
                backends[host] = fixtures.serve(backend, cleanup)
            self.http_port, self.https_port, status_port = (
                unused_port(),
                unused_port(),
                unused_port(),
            )
            cert, key = directory / "cert.pem", directory / "key.pem"
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-keyout",
                    str(key),
                    "-out",
                    str(cert),
                    "-days",
                    "1",
                    "-subj",
                    "/CN=localhost",
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            # Template substitution is limited to the same three variables as Compose.
            conf = source.replace("${DOMAIN}", "localhost")
            conf = conf.replace("${SAHOOL_AGENT_TOKEN}", "fixture-agent-token")
            conf = conf.replace("${SEASON_ENTRY_SERVICE_TOKEN}", "fixture-season-token")
            conf = conf.replace("127.0.0.11", f"127.0.0.1:{dns.server_address[1]}")
            conf = conf.replace("listen 80;", f"listen 127.0.0.1:{self.http_port};")
            conf = conf.replace("listen [::]:80;", "")
            conf = conf.replace(
                "listen 443 ssl http2;", f"listen 127.0.0.1:{self.https_port} ssl http2;"
            )
            conf = conf.replace("listen [::]:443 ssl http2;", "")
            conf = conf.replace("listen 8081;", f"listen 127.0.0.1:{status_port};")
            conf = conf.replace("/etc/nginx/ssl/fullchain.pem", str(cert))
            conf = conf.replace("/etc/nginx/ssl/privkey.pem", str(key))
            params = directory / "proxy_params.conf"
            params.write_bytes((ROOT / "nginx/proxy_params.conf").read_bytes())
            conf = conf.replace("/etc/nginx/proxy_params.conf", str(params))
            self.log = directory / "error.log"
            conf = conf.replace("/var/log/nginx/error.log", str(self.log))
            conf = conf.replace("/var/log/nginx/access.log", str(directory / "access.log"))
            # Remove dependence on the base image's writable default temp paths.
            paths = "".join(
                f"    {kind}_temp_path {directory}/{kind};\n"
                for kind in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi")
            )
            conf = conf.replace("http {\n", "http {\n" + paths, 1)
            for name, port in services.items():
                conf = conf.replace(f"{name}:{port}", f"{name}:{backends[name].server_port}")
            main = directory / "nginx.conf"
            main.write_text(
                f"daemon off;\nmaster_process off;\npid {directory}/nginx.pid;\n" + conf,
                encoding="utf-8",
            )
            command = self.command(directory) + ["-p", str(directory), "-c", str(main)]
            validation = subprocess.run(
                command + ["-t"], capture_output=True, text=True, timeout=30
            )
            self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)
            output = cleanup.enter_context((directory / "process.log").open("w", encoding="utf-8"))
            self.process = subprocess.Popen(command, stdout=output, stderr=output)

            def stop_nginx():
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)

            cleanup.callback(stop_nginx)
            self.eventually(
                lambda: self.request("/healthz", secure=False)[0] == 200,
                "gateway liveness without DNS",
            )
            original_pid = self.process.pid
            self.assertEqual(self.request("/", secure=False)[0], 301)
            for path in ("/", "/readyz", "/runtime-identity", "/auth/login", "/api/agent/health"):
                with self.subTest(absent=path):
                    self.assertEqual(self.request(path)[0], 502)

            records = dict.fromkeys(services, "127.0.0.1")
            dns.replace(records)
            self.eventually(lambda: self.request("/readyz")[0] == 200, "late platform DNS")
            headers = {
                "Authorization": "Bearer fixture-valid-token",
                "X-Tenant-Id": "forged",
                "X-User-Id": "forged",
                "X-User-Role": "admin",
                "X-Agent-Token": "forged",
            }
            routes = [
                ("/", "sahool-frontend", "/"),
                ("/auth/login", "sahool-auth", "/v1/auth/login"),
                ("/auth/auth/register", "sahool-auth", "/v1/auth/register"),
                ("/api/v1/fields/a%20b", "sahool-platform", "/api/v1/fields/a%20b"),
                ("/api/indicators/fields", "sahool-platform", "/api/v1/indicators/fields"),
                ("/api/weather/forecast", "sahool-platform", "/api/v1/weather/forecast"),
                ("/api/rag/search", "sahool-rag-retrieval", "/v1/search"),
                ("/tts/synthesize", "sahool-tts-service", "/v1/tts/synthesize"),
                ("/api/ai-agronomist/chat", "sahool-ai-agronomist", "/v1/chat"),
                ("/api/raster/v1/tiles/1.png", "sahool-raster-service", "/v1/tiles/1.png"),
                ("/api/vegetation/v1/indices", "sahool-vegetation-analysis", "/v1/indices"),
                (
                    "/api/remote-sensing-workspace/fields",
                    "sahool-remote-sensing-workspace-bff",
                    "/fields",
                ),
                ("/api/agent/health", "sahool-supervisor-agent", "/health"),
                ("/api/agent/query", "sahool-supervisor-agent", "/v1/agent/query"),
                ("/api/guardrails/validate", "sahool-guardrails-engine", "/validate"),
                ("/api/knowledge-graph/nodes", "sahool-knowledge-graph", "/v1/nodes"),
                ("/api/video/jobs", "sahool-video-processor", "/jobs"),
                ("/api/agriai/recommend", "sahool-agriai-engine", "/v1/recommend"),
                ("/api/v1/seasons/abc", "sahool-scout-ingest", "/internal/seasons/abc"),
                ("/readyz", "sahool-platform", "/readyz"),
                ("/runtime-identity", "sahool-platform", "/runtime-identity"),
                ("/api/indicators/readyz", "sahool-indicators-service", "/readyz"),
                ("/api/weather/readyz", "sahool-weather-service", "/readyz"),
            ]
            query = "?field=a%2Fb&day=1&day=2"
            for path, service, target in routes:
                with self.subTest(route=path):
                    self.eventually(
                        lambda p=path: self.request(p, headers)[0] == 200, f"late DNS: {service}"
                    )
                    status, _, body = self.request(path + query, headers)
                    self.assertEqual(status, 200)
                    data = json.loads(body)
                    self.assertEqual((data["service"], data["path"]), (service, target + query))
                    self.assertNotIn("x-agent-token", data["headers"])
                    self.assertNotEqual(data["headers"].get("x-tenant-id"), "forged")
                    self.assertNotEqual(data["headers"].get("x-user-id"), "forged")
                    if service in {
                        "sahool-rag-retrieval",
                        "sahool-ai-agronomist",
                        "sahool-raster-service",
                        "sahool-remote-sensing-workspace-bff",
                        "sahool-knowledge-graph",
                        "sahool-scout-ingest",
                    }:
                        self.assertEqual(data["headers"]["x-tenant-id"], "verified-tenant")

            protected = (
                "/api/rag/search",
                "/api/ai-agronomist/chat",
                "/api/raster/v1/tile.png",
                "/api/remote-sensing-workspace/fields",
                "/api/knowledge-graph/nodes",
            )
            for path in protected:
                self.assertEqual(self.request(path)[0], 401)
            self.assertEqual(self.request("/_auth_verify", headers)[0], 404)
            self.assertEqual(self.request("/api/unknown-route", headers)[0], 404)
            # Bind to a real denied source: 127.0.0.2 is outside the private ACL.
            # X-Forwarded-For alone is correctly ignored from an untrusted peer.
            self.assertEqual(self.request("/readyz", source_address=("127.0.0.2", 0))[0], 403)
            self.assertEqual(
                self.request("/runtime-identity", source_address=("127.0.0.2", 0))[0], 403
            )
            for path in ("/api/rag/search", "/tts/synthesize", "/api/ai-agronomist/chat"):
                status, _, body = self.request(path + query, headers, "POST", '{"text":"fixture"}')
                self.assertEqual(status, 200)
                data = json.loads(body)
                self.assertEqual((data["method"], data["body"]), ("POST", '{"text":"fixture"}'))
            status, _, body = self.request(
                "/ws/notifications?token=fixture", {"Upgrade": "websocket", "Connection": "upgrade"}
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["headers"]["upgrade"].lower(), "websocket")
            self.assertEqual(json.loads(body)["headers"]["connection"].lower(), "upgrade")
            status, redirect, _ = self.request("/api/indicators/redirect", headers)
            self.assertEqual(status, 302)
            self.assertEqual(
                redirect["Location"],
                f"https://127.0.0.1:{self.https_port}/api/indicators/destination",
            )

            # Remove Auth and an unrelated optional backend after successful routing.
            dns.replace(
                {
                    n: ip
                    for n, ip in records.items()
                    if n not in {"sahool-auth", "sahool-video-processor"}
                }
            )
            self.eventually(lambda: self.request("/auth/login")[0] == 502, "auth disappearance")
            self.eventually(
                lambda: self.request("/api/video/jobs")[0] == 502, "optional backend disappearance"
            )
            before = len(backends["sahool-ai-agronomist"].snapshot())
            self.assertGreaterEqual(self.request("/api/ai-agronomist/chat", headers)[0], 500)
            self.assertEqual(len(backends["sahool-ai-agronomist"].snapshot()), before)
            self.assertEqual(self.request("/healthz", secure=False)[0], 200)
            self.assertEqual(self.request("/api/weather/forecast")[0], 200)
            self.assertEqual(self.request("/")[0], 200)

            replacement = fixtures.serve(
                fixtures.Backend(
                    "sahool-auth", "127.0.0.2", backends["sahool-auth"].server_port, "replacement"
                ),
                cleanup,
            )
            dns.replace(dict(records, **{"sahool-auth": "127.0.0.2"}))
            self.eventually(
                lambda: (
                    self.request("/auth/login")[0] == 200
                    and json.loads(self.request("/auth/login")[2])["instance"] == "replacement"
                ),
                "replacement auth IP",
            )
            self.assertEqual(self.request("/api/ai-agronomist/chat", headers)[0], 200)
            self.assertTrue(replacement.snapshot())
            self.assertEqual(self.process.pid, original_pid)
            self.assertIsNone(self.process.poll())
            self.assertNotIn("[emerg]", self.log.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--docker", action="store_true")
    mode.add_argument("--nginx")
    parser.add_argument("--config", type=Path, default=GatewayRuntime.config)
    args = parser.parse_args()
    GatewayRuntime.config = args.config
    if args.docker:
        # Derive the version from the actual gateway service, not a second pin.
        compose = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
        gateway = re.search(r"^  sahool-nginx:\n(.*?)(?=^  [\w-]+:|\Z)", compose, re.M | re.S)
        if gateway is None:
            raise RuntimeError("canonical gateway service is missing")
        image_match = re.search(r"^    image:\s*(\S+)$", gateway[1], re.M)
        if image_match is None:
            raise RuntimeError("canonical gateway image is missing")
        image = image_match[1]
        subprocess.run(["docker", "pull", image], check=True, timeout=180)

        def command(directory):
            return [
                "docker",
                "run",
                "--rm",
                "--network=host",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-v",
                f"{directory}:{directory}",
                "--entrypoint",
                "nginx",
                image,
            ]
    else:

        def command(_directory):
            return [args.nginx]

    GatewayRuntime.command = staticmethod(command)
    unittest.main(argv=[__file__], verbosity=2)


if __name__ == "__main__":
    main()
