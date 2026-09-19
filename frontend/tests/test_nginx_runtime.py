"""Exercise the serving nginx config with real DNS and HTTP, without the stack.

CI: python3 frontend/tests/test_nginx_runtime.py --docker
Local equivalent: ... --nginx /path/to/nginx (>= 1.27.3, auth_request enabled).
Only listener addresses, service ports and filesystem paths are adapted. URI,
auth, redirect and resolver timing directives are the production configuration.
Missing tooling is an error, never a skipped/green test.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import http.server
import json
import os
import re
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1]
SERVICES = {
    "sahool-rag-retrieval": 8000,
    "sahool-tts-service": 8000,
    "sahool-ai-agronomist": 8000,
    "sahool-auth": 8000,
    "sahool-raster-service": 8001,
    "sahool-vegetation-analysis": 8000,
    "sahool-remote-sensing-workspace-bff": 8185,
    "sahool-platform": 8000,
    "sahool-supervisor-agent": 8000,
    "sahool-guardrails-engine": 8000,
    "sahool-notification-agent": 8123,
}


class DNSHandler(socketserver.BaseRequestHandler):
    def handle(self):
        packet, sock = self.request
        offset, labels = 12, []
        while packet[offset]:
            size = packet[offset]
            labels.append(packet[offset + 1 : offset + 1 + size].decode())
            offset += size + 1
        end = offset + 5  # zero byte, qtype, qclass
        host = ".".join(labels)
        kind = struct.unpack("!H", packet[offset + 1 : offset + 3])[0]
        with self.server.lock:
            address = self.server.records.get(host)
        answer = b""
        if address and kind == 1:
            answer = struct.pack("!HHHIH", 0xC00C, 1, 1, 1, 4)
            answer += socket.inet_aton(address)
        header = packet[:2] + struct.pack(
            "!HHHHH", 0x8180 if address else 0x8183, 1, bool(answer), 0, 0
        )
        sock.sendto(header + packet[12:end] + answer, self.client_address)


class DNSFixture(socketserver.UDPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), DNSHandler)
        self.records = {}
        self.lock = threading.Lock()

    def replace(self, records):
        with self.lock:
            self.records = records.copy()


class BackendHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        size = int(self.headers.get("Content-Length", "0"))
        request = {
            "service": self.server.service,
            "instance": self.server.instance,
            "method": self.command,
            "path": self.path,
            "headers": {key.lower(): value for key, value in self.headers.items()},
            "body": self.rfile.read(size).decode(),
        }
        with self.server.lock:
            self.server.requests.append(request)
        if self.server.service == "sahool-auth" and self.path == "/v1/auth/verify":
            allowed = self.headers.get("Authorization") == "Bearer fixture-valid-token"
            self.send_response(204 if allowed else 401)
            if allowed:
                self.send_header("X-Tenant-ID", "verified-tenant")
                self.send_header("X-User-ID", "verified-user")
                self.send_header("X-User-Role", "farmer")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.endswith("/redirect"):
            target = self.path.removesuffix("redirect") + "destination"
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://{self.server.service}:{self.server.server_port}{target}",
            )
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps(request).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET


class Backend(http.server.ThreadingHTTPServer):
    def __init__(self, service, address="127.0.0.1", port=0, instance="original"):
        super().__init__((address, port), BackendHandler)
        self.service, self.instance = service, instance
        self.requests, self.lock = [], threading.Lock()

    def snapshot(self):
        with self.lock:
            return list(self.requests)


def serve(server, cleanup):
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()

    def stop():
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    cleanup.callback(stop)
    return server


class RuntimeContract(unittest.TestCase):
    command = None
    config = FRONTEND / "nginx.conf"

    def request(self, path, headers=None, method="GET", body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def eventually(self, predicate, description):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            self.assertIsNone(self.process.poll(), self.log.read_text())
            try:
                if predicate():
                    return
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(0.1)
        self.fail(f"Timed out: {description}\n{self.log.read_text()[-6000:]}")

    def test_cold_start_routing_auth_and_dns_recovery(self):
        with contextlib.ExitStack() as cleanup:
            directory = Path(cleanup.enter_context(tempfile.TemporaryDirectory()))
            (directory / "logs").mkdir()
            dns = serve(DNSFixture(), cleanup)
            backends = {name: serve(Backend(name), cleanup) for name in SERVICES}
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                self.port = listener.getsockname()[1]
            assets = directory / "html"
            assets.mkdir()
            (assets / "index.html").write_text("frontend fixture shell")
            conf = self.config.read_text()
            conf = conf.replace("127.0.0.11", f"127.0.0.1:{dns.server_address[1]}")
            conf = conf.replace("listen 8080;", f"listen 127.0.0.1:{self.port};")
            conf = conf.replace("listen [::]:8080;", "")
            conf = conf.replace("/usr/share/nginx/html", str(assets))
            for name, port in SERVICES.items():
                conf = conf.replace(f"{name}:{port}", f"{name}:{backends[name].server_port}")
            (directory / "frontend.conf").write_text(conf)
            self.log = directory / "error.log"
            main = directory / "nginx.conf"
            main.write_text(
                ("user root;\n" if os.geteuid() == 0 else "") + "daemon off;\nmaster_process off;\n"
                f"pid {directory}/nginx.pid;\n"
                f"error_log {self.log} notice;\n"
                "events { worker_connections 128; }\n"
                "http {\n"
                f"access_log {directory}/access.log;\n"
                f"client_body_temp_path {directory}/client;\n"
                f"proxy_temp_path {directory}/proxy;\n"
                f"fastcgi_temp_path {directory}/fastcgi;\n"
                f"uwsgi_temp_path {directory}/uwsgi;\n"
                f"scgi_temp_path {directory}/scgi;\n"
                f"include {directory}/frontend.conf;\n}}\n"
            )
            command = self.command(directory) + ["-p", str(directory), "-c", str(main)]
            validation = subprocess.run(
                command + ["-t"], capture_output=True, text=True, timeout=30
            )
            self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)
            output = cleanup.enter_context((directory / "process.log").open("w+"))
            self.process = subprocess.Popen(command, stdout=output, stderr=output)

            def stop_nginx():
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)

            cleanup.callback(stop_nginx)
            self.eventually(lambda: self.request("/healthz")[0] == 200, "local liveness")
            original_pid = self.process.pid
            self.assertEqual(self.request("/")[2], b"frontend fixture shell")
            self.assertEqual(self.request("/fields/example")[2], b"frontend fixture shell")
            for path in ("/readyz", "/runtime-identity", "/api/agent/health", "/auth/login"):
                with self.subTest(missing_backend=path):
                    self.assertEqual(self.request(path)[0], 502)

            records = dict.fromkeys(SERVICES, "127.0.0.1")
            dns.replace(records)
            self.eventually(lambda: self.request("/readyz")[0] == 200, "late platform DNS")
            self.eventually(
                lambda: self.request("/api/agent/health")[0] == 200, "late supervisor DNS"
            )
            headers = {
                "Authorization": "Bearer fixture-valid-token",
                "X-Tenant-Id": "spoofed-tenant",
                "X-User-Id": "spoofed-user",
                "X-Agent-Token": "spoofed-agent",
            }
            routes = [
                ("/api/rag/search", "sahool-rag-retrieval", "/v1/search"),
                ("/tts/synthesize", "sahool-tts-service", "/v1/tts/synthesize"),
                ("/api/ai-agronomist/chat", "sahool-ai-agronomist", "/v1/chat"),
                ("/api/raster/v1/tiles/1/2/3.png", "sahool-raster-service", "/v1/tiles/1/2/3.png"),
                ("/api/vegetation/v1/indices", "sahool-vegetation-analysis", "/v1/indices"),
                (
                    "/api/remote-sensing-workspace/fields",
                    "sahool-remote-sensing-workspace-bff",
                    "/fields",
                ),
                ("/api/indicators/fields", "sahool-platform", "/api/v1/indicators/fields"),
                ("/api/weather/forecast", "sahool-platform", "/api/v1/weather/forecast"),
                ("/api/agent/health", "sahool-supervisor-agent", "/health"),
                ("/api/agent/chat", "sahool-supervisor-agent", "/v1/agent/chat"),
                ("/api/guardrails/validate", "sahool-guardrails-engine", "/validate"),
                ("/api/segmentation/segment", "sahool-platform", "/api/segmentation/segment"),
                ("/api/fields/a%20b", "sahool-platform", "/api/fields/a%20b"),
                ("/auth/login", "sahool-auth", "/v1/auth/login"),
                ("/auth/auth/register", "sahool-auth", "/v1/auth/register"),
                ("/ws/notifications", "sahool-notification-agent", "/ws/notifications"),
                ("/readyz", "sahool-platform", "/readyz"),
                ("/runtime-identity", "sahool-platform", "/runtime-identity"),
            ]
            query = "?field=a%2Fb&day=1&day=2"
            for path, service, target in routes:
                with self.subTest(route=path):
                    self.eventually(
                        lambda p=path: self.request(p, headers)[0] == 200,
                        f"late DNS for {service}",
                    )
                    status, _, body = self.request(path + query, headers)
                    self.assertEqual(status, 200)
                    data = json.loads(body)
                    self.assertEqual((data["service"], data["path"]), (service, target + query))
                    self.assertEqual(data["headers"]["host"], "127.0.0.1")
                    if service in {
                        "sahool-rag-retrieval",
                        "sahool-tts-service",
                        "sahool-ai-agronomist",
                        "sahool-raster-service",
                        "sahool-remote-sensing-workspace-bff",
                    }:
                        self.assertEqual(data["headers"]["x-tenant-id"], "verified-tenant")
                    if service == "sahool-ai-agronomist":
                        self.assertEqual(data["headers"]["x-user-id"], "verified-user")
                        self.assertNotIn("x-agent-token", data["headers"])

            # Cookie auth survives query/header disagreement and the subrequest.
            cookie_headers = dict(headers, Cookie="sahool_at=fixture-valid-token")
            cookie_headers["Authorization"] = "Bearer invalid"
            status, _, body = self.request(
                "/api/raster/v1/tiles/1.png?access_token=invalid", cookie_headers
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                json.loads(body)["headers"]["authorization"], "Bearer fixture-valid-token"
            )
            auth_requests = backends["sahool-auth"].snapshot()
            verified = [r for r in auth_requests if r["path"] == "/v1/auth/verify"]
            self.assertTrue(verified)
            for request in verified:
                self.assertNotIn("x-tenant-id", request["headers"])
                self.assertNotIn("x-user-id", request["headers"])
                self.assertNotIn("x-agent-token", request["headers"])
                self.assertEqual(
                    request["headers"]["host"], f"sahool-auth:{backends['sahool-auth'].server_port}"
                )
            for path in (
                "/api/rag/search",
                "/tts/synthesize",
                "/api/ai-agronomist/chat",
                "/api/raster/v1/tile.png",
                "/api/remote-sensing-workspace/fields",
            ):
                self.assertEqual(self.request(path)[0], 401)
            for path, service in (
                ("/api/rag/search", "sahool-rag-retrieval"),
                ("/tts/synthesize", "sahool-tts-service"),
            ):
                status, _, body = self.request(path, cookie_headers, "POST", '{"text":"fixture"}')
                self.assertEqual(status, 200)
                data = json.loads(body)
                self.assertEqual(data["service"], service)
                self.assertEqual(data["method"], "POST")
                self.assertEqual(data["body"], '{"text":"fixture"}')
                self.assertEqual(data["headers"]["authorization"], "Bearer fixture-valid-token")
                for key in ("x-agent-token", "x-user-id", "x-user-role"):
                    self.assertNotIn(key, data["headers"])
            self.assertEqual(self.request("/_auth_verify", headers)[0], 404)
            status, _, body = self.request(
                "/api/ai-agronomist/chat?stream=0", headers, "POST", '{"text":"hello"}'
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["body"], '{"text":"hello"}')
            self.assertEqual(json.loads(body)["method"], "POST")
            status, _, body = self.request(
                "/ws/notifications?token=x", {"Upgrade": "websocket", "Connection": "upgrade"}
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["headers"]["upgrade"], "websocket")
            self.assertEqual(json.loads(body)["headers"]["connection"], "upgrade")
            for path, expected in (
                ("/api/indicators/redirect", "/api/indicators/destination"),
                ("/api/raster/redirect", "/api/raster/destination"),
                ("/auth/login/redirect", "/v1/auth/login/destination"),
            ):
                status, response_headers, _ = self.request(path, headers)
                self.assertEqual(status, 302)
                self.assertEqual(
                    response_headers["Location"], f"http://127.0.0.1:{self.port}{expected}"
                )

            # A missing auth backend must never authorize a protected request.
            dns.replace(
                {name: address for name, address in records.items() if name != "sahool-auth"}
            )
            self.eventually(lambda: self.request("/auth/login")[0] == 502, "auth DNS removal")
            count = len(backends["sahool-ai-agronomist"].snapshot())
            self.assertGreaterEqual(self.request("/api/ai-agronomist/chat", headers)[0], 500)
            self.assertEqual(len(backends["sahool-ai-agronomist"].snapshot()), count)
            self.assertEqual(self.request("/healthz")[0], 200)
            self.assertEqual(self.request("/api/weather/forecast")[0], 200)

            # Container replacement: the same service name/port now has a new IP.
            replacement = serve(
                Backend(
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
                "auth recovery on replacement IP",
            )
            self.assertEqual(self.request("/api/ai-agronomist/chat", headers)[0], 200)
            self.assertTrue(replacement.snapshot())
            self.assertEqual(self.process.pid, original_pid)
            self.assertIsNone(self.process.poll())
            self.assertNotIn("[emerg]", self.log.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--docker", action="store_true")
    mode.add_argument("--nginx", help="nginx binary compiled with http_auth_request_module")
    parser.add_argument("--config", type=Path, default=FRONTEND / "nginx.conf")
    args = parser.parse_args()
    RuntimeContract.config = args.config
    if args.docker:
        image = re.findall(r"^FROM (nginx:\S+)", (FRONTEND / "Dockerfile").read_text(), re.M)[-1]
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

    RuntimeContract.command = staticmethod(command)
    unittest.main(argv=[__file__], verbosity=2)


if __name__ == "__main__":
    main()
