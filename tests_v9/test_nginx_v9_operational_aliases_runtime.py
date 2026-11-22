"""Request-level proof that the six operational aliases reach the service's own handler.

Runs the real ``nginx/nginx.v9.conf`` (the pinned gateway image, or ``NGINX_BIN``) against
the loopback fixtures of ``frontend/tests/test_nginx_runtime.py``: a DNS server, an auth
backend that verifies one fixture token, and one echo backend per upstream. The config is
adapted exactly as ``frontend/tests/nginx_v9_runtime_contract.py`` adapts it (process,
listeners, service ports, template secrets, filesystem paths); every auth, proxy and
location directive is the production one.

Fixture backends echo the request they received, so the proof is the upstream path and
headers nginx sent, checked against the routes the service source declares. It does not
certify the services, the real auth service, or any deployed gateway.

Marked ``integration``: it needs docker (or ``NGINX_BIN``, an nginx >= 1.27.3 with
http_auth_request_module) and the pinned gateway image, and is skipped without both.
``SAHOOL_NGINX_RUNTIME_IMAGE`` may name a mirror of that image (same digest only).
"""

from __future__ import annotations

import contextlib
import http.client
import importlib.util
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "nginx" / "nginx.v9.conf"
VALID = {"Authorization": "Bearer fixture-valid-token"}
SERVICES = {
    "/api/rag/": ("sahool-rag-retrieval", "services/rag-retrieval/main.py"),
    "/api/knowledge-graph/": ("sahool-knowledge-graph", "services/knowledge-graph/main.py"),
    "/api/ai-agronomist/": ("sahool-ai-agronomist", "services/ai_agronomist/main.py"),
}
ALIASES = [f"{prefix}{name}" for prefix in SERVICES for name in ("readyz", "metrics")]


def _harness():
    name = "sahool_nginx_runtime_harness"
    if name not in sys.modules:
        path = ROOT / "frontend" / "tests" / "test_nginx_runtime.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _obtain(pinned: str) -> str:
    """A local reference to the pinned image. Any registry may serve it, never another digest.

    The digest is the OCI index of the Docker Official Image, so the same bytes are published
    under the same digest elsewhere; docker verifies it on pull. Public ECR alone answers
    "Data limit exceeded" to shared addresses often enough to need the alternatives.
    """
    digest = pinned.rsplit("@", 1)[1]
    if os.environ.get("GHCR_TOKEN"):
        with tempfile.TemporaryDirectory(prefix="sahool-nginx-ci-") as folder:
            receipt = Path(folder) / "nginx-id"
            script = ROOT / "scripts/ci/pull_verified_ci_image.sh"
            subprocess.run(["bash", str(script), pinned, str(receipt)], cwd=ROOT, check=True)
            return receipt.read_text(encoding="utf-8").strip()
    candidates = [
        os.environ.get("SAHOOL_NGINX_RUNTIME_IMAGE") or pinned,
        pinned,
        f"mirror.gcr.io/library/nginx@{digest}",
        f"docker.io/library/nginx@{digest}",
    ]
    errors = []
    for image in dict.fromkeys(candidates):
        assert image.endswith("@" + digest), f"{image} is not the pinned {digest}"
        if not subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, timeout=30, check=False
        ).returncode:
            return image
    for image in dict.fromkeys(candidates):
        try:
            subprocess.run(
                ["docker", "pull", image],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
            )
            return image
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{image}: {getattr(exc, 'stderr', '') or exc}")
    raise AssertionError("the pinned gateway image could not be pulled:\n" + "\n".join(errors))


def _nginx_command():
    """``directory -> argv prefix`` for an nginx that understands ``server … resolve``."""
    binary = os.environ.get("NGINX_BIN")
    if binary:
        return lambda _directory: [binary]
    if not shutil.which("docker"):
        pytest.skip("needs docker or NGINX_BIN (nginx >= 1.27.3 with http_auth_request_module)")
    image = re.findall(
        r"^FROM (public\.ecr\.aws/docker/library/nginx@sha256:[0-9a-f]{64})",
        (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8"),
        re.M,
    )[-1]
    image = _obtain(image)
    return lambda directory: [
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


class Gateway:
    def __init__(self, port: int, context: ssl.SSLContext, backends: dict):
        self.port, self.context, self.backends = port, context, backends

    def request(self, path: str, headers: dict | None = None, method: str = "GET"):
        connection = http.client.HTTPSConnection(
            "127.0.0.1", self.port, context=self.context, timeout=5
        )
        try:
            connection.request(method, path, None, headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def seen(self, service: str) -> int:
        return len(self.backends[service].snapshot())


@pytest.fixture(scope="module")
def gateway():
    harness = _harness()
    command = _nginx_command()
    with contextlib.ExitStack() as cleanup:
        directory = Path(cleanup.enter_context(tempfile.TemporaryDirectory()))
        (directory / "logs").mkdir()
        dns = harness.serve(harness.DNSFixture(), cleanup)
        source = CONFIG.read_text(encoding="utf-8")
        uncommented = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
        ports = dict(re.findall(r"server\s+(sahool-[a-z0-9-]+):(\d+)", uncommented))
        assert {"sahool-auth", *(service for service, _ in SERVICES.values())} <= ports.keys()
        backends = {name: harness.serve(harness.Backend(name), cleanup) for name in ports}
        port, http_port, status_port = _free_port(), _free_port(), _free_port()
        cert, key = directory / "fullchain.pem", directory / "privkey.pem"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key)]
            + ["-out", str(cert), "-days", "1", "-subj", "/CN=127.0.0.1"]
            + ["-addext", "subjectAltName=IP:127.0.0.1"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        proxy = directory / "proxy_params.conf"
        proxy.write_bytes((ROOT / "nginx" / "proxy_params.conf").read_bytes())
        (directory / "mime.types").write_text("types {}\n", encoding="utf-8")
        log = directory / "error.log"
        conf = source.replace("worker_processes auto;", "worker_processes 1;")
        replacements = {
            "127.0.0.11": f"127.0.0.1:{dns.server_address[1]}",
            "listen 8081;": f"listen 127.0.0.1:{status_port};",
            "listen 80;": f"listen 127.0.0.1:{http_port};",
            "listen [::]:80;": "",
            "listen 443 ssl http2;": f"listen 127.0.0.1:{port} ssl http2;",
            "listen [::]:443 ssl http2;": "",
            **{
                f"{name}:{value}": f"{name}:{backends[name].server_port}"
                for name, value in ports.items()
            },
            "${DOMAIN}": "localhost",
            "${SAHOOL_AGENT_TOKEN}": "fixture-service-token",
            "${FIELD_TASKS_SERVICE_TOKEN}": "fixture-field-tasks-token",
            "${SCOUT_MEDIA_SERVICE_TOKEN}": "fixture-scout-media-token",
            "${SEASON_ENTRY_SERVICE_TOKEN}": "fixture-season-entry-token",
            "/etc/nginx/ssl/fullchain.pem": str(cert),
            "/etc/nginx/ssl/privkey.pem": str(key),
            "/etc/nginx/proxy_params.conf": str(proxy),
            "/etc/nginx/mime.types": str(directory / "mime.types"),
            "/var/log/nginx/error.log": str(log),
            "/var/log/nginx/access.log": str(directory / "access.log"),
            "/var/www/html": str(directory / "html"),
        }
        for old, new in replacements.items():
            conf = conf.replace(old, new)
        # ${pre}/${post} are nginx regex variables, not environment templates.
        assert not set(re.findall(r"\$\{([^}]+)\}", conf)) - {"pre", "post"}
        temporary = "\n".join(
            f"    {kind}_temp_path {directory}/{kind};"
            for kind in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi")
        )
        conf = conf.replace("http {", "http {\n" + temporary, 1)
        conf = (
            ("user root;\n" if os.geteuid() == 0 else "")
            + f"daemon off;\nmaster_process off;\npid {directory}/nginx.pid;\n"
            + conf
        )
        main = directory / "nginx.conf"
        main.write_text(conf, encoding="utf-8")
        argv = command(directory) + ["-p", str(directory), "-c", str(main)]
        checked = subprocess.run(
            argv + ["-t"], capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        output = cleanup.enter_context((directory / "process.log").open("w+", encoding="utf-8"))
        process = subprocess.Popen(argv, stdout=output, stderr=output)

        def stop():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        cleanup.callback(stop)
        dns.replace(dict.fromkeys(backends, "127.0.0.1"))
        running = Gateway(port, ssl.create_default_context(cafile=str(cert)), backends)

        def ready() -> bool:
            try:
                return running.request("/auth/login")[0] == 200
            except OSError:
                return False

        deadline = time.monotonic() + 30
        while not ready():
            assert process.poll() is None, (
                log.read_text(encoding="utf-8") if log.exists() else "nginx exited"
            )
            assert time.monotonic() < deadline, "gateway never resolved its upstreams"
            time.sleep(0.1)
        yield running
        assert process.poll() is None, "nginx died during the contract"
        assert "[emerg]" not in log.read_text(encoding="utf-8")


def _declared_get_routes(source: str) -> set[str]:
    text = (ROOT / source).read_text(encoding="utf-8")
    return set(re.findall(r'(?m)^@app\.get\(\s*"([^"]+)"', text))


def _service(path: str) -> tuple[str, str, str]:
    prefix = next(p for p in SERVICES if path.startswith(p))
    return (prefix, *SERVICES[prefix])


@pytest.mark.parametrize("alias", ALIASES)
def test_alias_reaches_the_service_root_handler(gateway, alias: str) -> None:
    _, service, source = _service(alias)
    spoofed = dict(
        VALID,
        **{
            "X-Tenant-Id": "forged-tenant",
            "X-User-Id": "forged-user",
            "X-User-Role": "admin",
            "X-Agent-Token": "forged-service-secret",
            "Cookie": "theme=dark",
        },
    )
    status, body = gateway.request(alias, spoofed)
    assert status == 200, body
    data = json.loads(body)
    assert data["service"] == service
    assert data["path"] == "/" + alias.rsplit("/", 1)[1]
    assert data["path"] in _declared_get_routes(source), f"{source} does not declare it"
    assert data == gateway.backends[service].snapshot()[-1]
    for header in ("x-tenant-id", "x-user-id", "x-user-role", "x-agent-token", "cookie"):
        assert header not in data["headers"], f"{alias} forwarded the client's {header}"


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer invalid"}, {"Cookie": "sahool_at=invalid"}],
    ids=["no-token", "bad-bearer", "bad-cookie"],
)
def test_alias_refuses_an_unverified_caller_before_the_service(gateway, alias, headers) -> None:
    service = _service(alias)[1]
    before = gateway.seen(service)
    assert gateway.request(alias, headers)[0] == 401
    assert gateway.seen(service) == before, f"{alias} reached {service} without identity"


@pytest.mark.parametrize("alias", ALIASES)
def test_alias_accepts_the_browser_session_cookie(gateway, alias: str) -> None:
    status, body = gateway.request(alias, {"Cookie": "sahool_at=fixture-valid-token"})
    assert status == 200, body
    data = json.loads(body)
    assert data["path"] == "/" + alias.rsplit("/", 1)[1]
    assert "cookie" not in data["headers"]


@pytest.mark.parametrize("alias", ALIASES)
@pytest.mark.parametrize("suffix", ["/", "x", "/extra"])
def test_near_miss_stays_on_the_guarded_v1_rewrite(gateway, alias: str, suffix: str) -> None:
    prefix, service, _ = _service(alias)
    path = alias + suffix
    before = gateway.seen(service)
    assert gateway.request(path)[0] == 401
    assert gateway.seen(service) == before
    status, body = gateway.request(path, VALID)
    assert status == 200, body
    assert json.loads(body)["path"] == "/v1/" + path[len(prefix) :]


def test_query_string_is_kept_and_the_prefix_is_unchanged(gateway) -> None:
    status, body = gateway.request("/api/rag/readyz?verbose=1", VALID)
    assert (status, json.loads(body)["path"]) == (200, "/readyz?verbose=1")
    status, body = gateway.request("/api/knowledge-graph/edges?limit=1", VALID)
    data = json.loads(body)
    assert (status, data["path"]) == (200, "/v1/edges?limit=1")
    assert data["headers"]["x-tenant-id"] == "verified-tenant"
    assert gateway.request("/api/knowledge-graph/edges?limit=1")[0] == 401
