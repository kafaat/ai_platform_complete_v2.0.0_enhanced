"""Run the complete v9 gateway config, including TLS, against loopback fixtures.

Use test_nginx_runtime.py --profile v9 with --nginx or --docker. The production
auth/proxy/rewrite/resolver directives are retained. Only process, listener,
service port, template-secret and filesystem inputs are adapted. Static assets,
MIME mappings, production certificates and the future scoped-token exchange are
outside this contract. Fixture auth responses do not certify the real service.
"""

from __future__ import annotations

import contextlib
import http.client
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

from test_nginx_runtime import FRONTEND, Backend, DNSFixture, serve


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class V9RuntimeContract(unittest.TestCase):
    command = None
    config = FRONTEND.parent / "nginx/nginx.v9.conf"

    def request(self, path, headers=None, method="GET", body=None, *, plain=False):
        if plain:
            connection = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=3)
        else:
            connection = http.client.HTTPSConnection(
                "127.0.0.1", self.port, context=self.tls_context, timeout=3
            )
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

    def test_v9_tls_identity_cookie_post_and_auth_dns_recovery(self):
        with contextlib.ExitStack() as cleanup:
            directory = Path(cleanup.enter_context(tempfile.TemporaryDirectory()))
            (directory / "logs").mkdir()
            dns = serve(DNSFixture(), cleanup)
            source = self.config.read_text(encoding="utf-8")
            uncommented = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
            ports = dict(re.findall(r"server\s+(sahool-[a-z0-9-]+):(\d+)", uncommented))
            self.assertTrue(
                {"sahool-auth", "sahool-ai-agronomist", "sahool-raster-service"} <= ports.keys()
            )
            backends = {name: serve(Backend(name), cleanup) for name in ports}
            self.port, self.http_port, status_port = free_port(), free_port(), free_port()
            self.assertEqual(len({self.port, self.http_port, status_port}), 3)
            cert, key = directory / "fullchain.pem", directory / "privkey.pem"
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
                    "/CN=127.0.0.1",
                    "-addext",
                    "subjectAltName=IP:127.0.0.1",
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            self.tls_context = ssl.create_default_context(cafile=str(cert))
            proxy = directory / "proxy_params.conf"
            proxy.write_bytes((FRONTEND.parent / "nginx/proxy_params.conf").read_bytes())
            (directory / "mime.types").write_text("types {}\n", encoding="utf-8")
            conf = source.replace("worker_processes auto;", "worker_processes 1;")
            self.assertNotEqual(conf, source, "full main-config profile is required")
            conf = conf.replace("127.0.0.11", f"127.0.0.1:{dns.server_address[1]}")
            conf = conf.replace("listen 8081;", f"listen 127.0.0.1:{status_port};")
            conf = conf.replace("listen 80;", f"listen 127.0.0.1:{self.http_port};")
            conf = conf.replace("listen [::]:80;", "")
            conf = conf.replace("listen 443 ssl http2;", f"listen 127.0.0.1:{self.port} ssl http2;")
            conf = conf.replace("listen [::]:443 ssl http2;", "")
            for name, port in ports.items():
                conf = conf.replace(f"{name}:{port}", f"{name}:{backends[name].server_port}")
            for name, value in {
                "DOMAIN": "localhost",
                "SAHOOL_AGENT_TOKEN": "fixture-service-token",
                "FIELD_TASKS_SERVICE_TOKEN": "fixture-field-tasks-token",
                "SCOUT_MEDIA_SERVICE_TOKEN": "fixture-scout-media-token",
                "SEASON_ENTRY_SERVICE_TOKEN": "fixture-season-entry-token",
            }.items():
                conf = conf.replace("${" + name + "}", value)
            # ${pre}/${post} are nginx regex variables, not environment templates.
            self.assertFalse(set(re.findall(r"\$\{([^}]+)\}", conf)) - {"pre", "post"})
            self.log = directory / "error.log"
            for old, new in {
                "/etc/nginx/ssl/fullchain.pem": str(cert),
                "/etc/nginx/ssl/privkey.pem": str(key),
                "/etc/nginx/proxy_params.conf": str(proxy),
                "/etc/nginx/mime.types": str(directory / "mime.types"),
                "/var/log/nginx/error.log": str(self.log),
                "/var/log/nginx/access.log": str(directory / "access.log"),
                "/var/www/html": str(directory / "html"),
            }.items():
                conf = conf.replace(old, new)
            temporary_paths = "\n".join(
                f"    {kind}_temp_path {directory}/{kind};"
                for kind in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi")
            )
            conf = conf.replace("http {", "http {\n" + temporary_paths, 1)
            conf = (
                ("user root;\n" if os.geteuid() == 0 else "")
                + f"daemon off;\nmaster_process off;\npid {directory}/nginx.pid;\n"
                + conf
            )
            main = directory / "nginx.conf"
            main.write_text(conf, encoding="utf-8")
            command = self.command(directory) + ["-p", str(directory), "-c", str(main)]
            checked = subprocess.run(command + ["-t"], capture_output=True, text=True, timeout=30)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
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
            self.eventually(
                lambda: self.request("/healthz", plain=True)[0] == 200, "cold HTTP liveness"
            )
            original_pid = self.process.pid
            headers = {"Authorization": "Bearer fixture-valid-token"}
            self.assertGreaterEqual(self.request("/api/ai-agronomist/chat", headers)[0], 500)
            self.assertFalse(backends["sahool-ai-agronomist"].snapshot())
            records = dict.fromkeys(backends, "127.0.0.1")
            dns.replace(records)
            self.eventually(lambda: self.request("/auth/login")[0] == 200, "late auth DNS")
            spoofed = dict(
                headers,
                **{
                    "X-Tenant-Id": "forged-tenant",
                    "X-User-Id": "forged-user",
                    "X-User-Role": "admin",
                    "X-Agent-Token": "forged-service-secret",
                    "Cookie": "theme=dark",
                },
            )
            status, _, body = self.request(
                "/api/ai-agronomist/chat?stream=0", spoofed, "POST", '{"text":"hello"}'
            )
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["service"], "sahool-ai-agronomist")
            self.assertEqual(backends["sahool-ai-agronomist"].snapshot()[-1], data)
            self.assertEqual(
                (data["path"], data["method"], data["body"]),
                ("/v1/chat?stream=0", "POST", '{"text":"hello"}'),
            )
            for key, value in {
                "x-tenant-id": "verified-tenant",
                "x-user-id": "verified-user",
                "x-user-role": "farmer",
            }.items():
                self.assertEqual(data["headers"][key], value)
            for key in ("x-agent-token", "cookie"):
                self.assertNotIn(key, data["headers"])
            count = len(backends["sahool-ai-agronomist"].snapshot())
            self.assertEqual(
                self.request("/api/ai-agronomist/chat", {"Authorization": "Bearer invalid"})[0], 401
            )
            self.assertEqual(len(backends["sahool-ai-agronomist"].snapshot()), count)
            status, _, body = self.request(
                "/api/raster/example",
                {
                    "Cookie": "sahool_at=fixture-valid-token",
                    "Authorization": "Bearer invalid",
                    "X-Tenant-Id": "forged-tenant",
                    "X-Agent-Token": "forged-secret",
                },
            )
            self.assertEqual(status, 200)
            data = json.loads(body)
            self.assertEqual(data["service"], "sahool-raster-service")
            self.assertEqual(backends["sahool-raster-service"].snapshot()[-1], data)
            self.assertEqual(data["headers"]["x-tenant-id"], "verified-tenant")
            self.assertEqual(data["headers"]["authorization"], "Bearer fixture-valid-token")
            self.assertNotIn("x-agent-token", data["headers"])
            self.assertNotIn("cookie", data["headers"])
            for request in backends["sahool-auth"].snapshot():
                if request["path"] == "/v1/auth/verify":
                    for key in ("x-agent-token", "x-tenant-id", "x-user-id", "cookie"):
                        self.assertNotIn(key, request["headers"])
            dns.replace(
                {name: address for name, address in records.items() if name != "sahool-auth"}
            )
            self.eventually(lambda: self.request("/auth/login")[0] == 502, "auth DNS loss")
            count = len(backends["sahool-ai-agronomist"].snapshot())
            self.assertGreaterEqual(self.request("/api/ai-agronomist/chat", headers)[0], 500)
            self.assertEqual(len(backends["sahool-ai-agronomist"].snapshot()), count)
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
                "auth replacement IP recovery",
            )
            self.assertEqual(self.request("/api/ai-agronomist/chat", headers)[0], 200)
            self.assertTrue(replacement.snapshot())
            self.assertEqual(self.process.pid, original_pid)
            self.assertNotIn("[emerg]", self.log.read_text())
