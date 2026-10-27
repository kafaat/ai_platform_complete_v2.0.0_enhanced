"""فحص صحّة حاوية raster-service يجب أن يفشل على أيّ ردّ HTTP غير 2xx (C2).

العطل: ``HEALTHCHECK`` في ``Dockerfile`` وفحص ``sahool-raster-service`` في
``docker-compose.v9.yml`` كانا ``httpx.get('/healthz')`` بلا ``raise_for_status()``.
``httpx`` لا يرفع استثناءً على 503، فالعمليّة تخرج بـ0 وتُعلَن الحاوية «سليمة» وهي
تردّ خطأً — فتبدأ الخدمات التابعة (``depends_on: condition: service_healthy``).

الاختبار **سلوكيّ لا نصّيّ**: يستخرج أمر الفحص كما هو من الملفّين، ويوجّهه إلى خادم
HTTP محلّيّ مؤقّت (loopback فقط) يردّ بالحالة المطلوبة، ويقيس رمز الخروج الفعليّ.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

_SERVICE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SERVICE_DIR.parents[1]
_PROBE_ORIGIN = "http://localhost:8001"


def _dockerfile_probe() -> str:
    """كود python في ``HEALTHCHECK ... CMD python -c "<code>"`` من Dockerfile الخدمة."""
    for line in (_SERVICE_DIR / "Dockerfile").read_text(encoding="utf-8").splitlines():
        if line.startswith("HEALTHCHECK"):
            argv = shlex.split(line.split(" CMD ", 1)[1])
            assert argv[:2] == ["python", "-c"], argv
            return argv[2]
    raise AssertionError("لا HEALTHCHECK في services/raster-service/Dockerfile")


def _compose_probe() -> str:
    """كود python في فحص ``sahool-raster-service`` من docker-compose.v9.yml."""
    compose = yaml.safe_load((_REPO_ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    test = compose["services"]["sahool-raster-service"]["healthcheck"]["test"]
    assert test[:3] == ["CMD", "python", "-c"], test
    return test[3]


class _StatusServer:
    """خادم loopback يردّ على كلّ GET بالحالة المضبوطة (لا شبكة خارجيّة)."""

    def __init__(self) -> None:
        self.status = 200
        owner = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 — اسم واجهة http.server
                body = b'{"status":"probe"}'
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.origin = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture(scope="module")
def status_server():
    srv = _StatusServer()
    try:
        yield srv
    finally:
        srv.close()


def _run_probe(code: str, server: _StatusServer, status: int) -> int:
    assert _PROBE_ORIGIN in code, f"الفحص لم يعد يستهدف {_PROBE_ORIGIN}: {code}"
    server.status = status
    proc = subprocess.run(
        [sys.executable, "-c", code.replace(_PROBE_ORIGIN, server.origin)],
        capture_output=True,
        timeout=30,
        check=False,
    )
    return proc.returncode


_PROBES = {"dockerfile": _dockerfile_probe, "compose": _compose_probe}


@pytest.mark.parametrize("source", sorted(_PROBES))
@pytest.mark.parametrize("status", [500, 503, 404])
def test_healthcheck_exits_nonzero_on_http_error(source, status, status_server):
    code = _PROBES[source]()
    rc = _run_probe(code, status_server, status)
    assert rc != 0, f"{source} healthcheck خرج بـ0 على HTTP {status}: {code}"


@pytest.mark.parametrize("source", sorted(_PROBES))
def test_healthcheck_exits_zero_on_http_200(source, status_server):
    code = _PROBES[source]()
    assert _run_probe(code, status_server, 200) == 0


def test_no_dockerfile_healthcheck_uses_unchecked_python_http_client():
    """النمط نفسه في أيّ Dockerfile آخر: ``httpx``/``requests`` لا يرفعان على 5xx.

    ``urllib.request.urlopen`` يرفع ``HTTPError`` على ≥400، و``curl -f``/``wget`` يفشلان؛
    أمّا ``httpx.get``/``requests.get`` فيحتاجان ``raise_for_status()`` صراحةً.
    """
    offenders: list[str] = []
    for dockerfile in sorted(_REPO_ROOT.glob("**/Dockerfile*")):
        if "node_modules" in dockerfile.parts or ".git" in dockerfile.parts:
            continue
        text = dockerfile.read_text(encoding="utf-8", errors="replace").replace("\\\n", " ")
        for line in text.splitlines():
            if not line.lstrip().startswith("HEALTHCHECK"):
                continue
            if ("httpx." in line or "requests." in line) and "raise_for_status" not in line:
                offenders.append(f"{dockerfile.relative_to(_REPO_ROOT)}: {line.strip()}")
    assert not offenders, "HEALTHCHECK بعميل HTTP لا يفشل على 5xx:\n" + "\n".join(offenders)
