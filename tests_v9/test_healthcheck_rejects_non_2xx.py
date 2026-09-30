"""فحصُ الصحّة يفشل حين تفشل الخدمة — HEALTHCHECK-ACCEPTS-ANY-HTTP-STATUS-01.

**العطل مقيس:** `python -c "import httpx; httpx.get('http://…/healthz')"` يخرج 0 على 200
و503 و500 و404 (httpx 0.28.1 لا يرفع على رمز الحالة). فحاويةُ raster-service تُعلَن
healthy وخدمتُها تُعيد 503 أو لا تملك المسار أصلاً، و`depends_on: service_healthy`
يُطلق معتمديها على خدمةٍ عاطلة. بينما `urllib.request.urlopen` يرفع `HTTPError` على ≥400
و`curl -f` يخرج 22 — فالعطلُ في شكل المِسبار لا في الفكرة.

**الشاهد ديناميكيّ لا نصّيّ:** يستخرج كلَّ فحصٍ بـ`python -c` من كلّ ملفّ compose وكلّ
Dockerfile **بمسح الشجرة** (فالعضو الجديد يُلتقَط بلا تسجيل)، ويستبدل المضيف:المنفذ وحده
بخادم http.server محلّيّ يُعيد 200/503/500/404، ويُشغِّل الشيفرة كما هي. الخروج 0 مقبول
على 200 وحده. ومتغيّرات الوكيل تُنزَع لأنّ الهدف loopback.

والفحوص بـcurl تُفحَص نصّيّاً: بلا `-f`/`--fail` يخرج curl صفراً على أيّ رمز حالة.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import shlex
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

_COMPOSE_RE = re.compile(r"(^|/)(docker-)?compose[^/]*\.ya?ml$")
_DOCKERFILE_RE = re.compile(r"(^|/)(Dockerfile[^/]*|[^/]*\.Dockerfile)$")
_LOOPBACK_URL = re.compile(r"http://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::[^/'\"\s]+)?")
_PROXY_VARS = {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
_STATUSES = (200, 503, 500, 404)


def _tracked_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-files", "-z"], text=True, encoding="utf-8"
        )
        return [f for f in out.split("\0") if f]
    except (OSError, subprocess.CalledProcessError):
        return [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()]


def _tokens_from_test(test: object) -> list[str]:
    """شكلُ `healthcheck.test` في compose ⇒ قائمة وسائط كما يراها المُنفِّذ."""
    if isinstance(test, str):
        return shlex.split(test)
    if isinstance(test, list) and test:
        head, rest = test[0], [str(t) for t in test[1:]]
        if head == "CMD-SHELL":
            return shlex.split(" ".join(rest))
        if head == "CMD":
            return rest
    return []


def _python_c_code(tokens: list[str]) -> str | None:
    for i, tok in enumerate(tokens[:-2]):
        if re.fullmatch(r"(.*/)?python3?", tok) and tokens[i + 1] == "-c":
            return tokens[i + 2]
    return None


def _dockerfile_healthchecks(rel: str) -> list[tuple[str, list[str]]]:
    lines = (ROOT / rel).read_text(encoding="utf-8", errors="replace").split("\n")
    found: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(lines):
        if re.match(r"\s*HEALTHCHECK\b", lines[i]):
            start, buf = i, lines[i]
            while buf.rstrip().endswith("\\") and i + 1 < len(lines):
                i += 1
                buf = buf.rstrip()[:-1] + " " + lines[i].strip()
            m = re.search(r"\bCMD\s+(.*)$", buf)
            if m:
                rest = m.group(1).strip()
                tokens = json.loads(rest) if rest.startswith("[") else shlex.split(rest)
                found.append((f"{rel}:{start + 1}", tokens))
        i += 1
    return found


def _all_healthchecks() -> list[tuple[str, list[str]]]:
    """كلُّ فحص صحّة في الشجرة: (هويّة العضو، وسائطه)."""
    members: list[tuple[str, list[str]]] = []
    for rel in _tracked_files():
        if _COMPOSE_RE.search(rel):
            doc = yaml.safe_load((ROOT / rel).read_text(encoding="utf-8")) or {}
            for name, svc in (doc.get("services") or {}).items():
                hc = (svc or {}).get("healthcheck") or {}
                tokens = _tokens_from_test(hc.get("test"))
                # compose يُهرِّب `$` بـ`$$`؛ المُنفِّذ يرى `$`.
                members.append((f"{rel}::{name}", [t.replace("$$", "$") for t in tokens]))
        elif _DOCKERFILE_RE.search(rel):
            members.extend(_dockerfile_healthchecks(rel))
    return [(ident, toks) for ident, toks in members if toks]


_HEALTHCHECKS = _all_healthchecks()
_PYTHON_HTTP_MEMBERS = sorted(
    (ident, code)
    for ident, toks in _HEALTHCHECKS
    if (code := _python_c_code(toks)) is not None and "http://" in code
)
_CURL_MEMBERS = sorted(ident for ident, toks in _HEALTHCHECKS if "curl" in toks)


class _StatusHandler(http.server.BaseHTTPRequestHandler):
    def _reply(self) -> None:
        body = b'{"status":"probe-fixture"}'
        self.send_response(self.server.status)  # type: ignore[attr-defined]
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_GET = _reply
    do_HEAD = _reply

    def log_message(self, *_args: object) -> None:  # صامت
        pass


@pytest.fixture(scope="module")
def status_servers():
    servers: dict[int, http.server.ThreadingHTTPServer] = {}
    for status in _STATUSES:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _StatusHandler)
        srv.status = status  # type: ignore[attr-defined]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers[status] = srv
    yield {status: srv.server_address[1] for status, srv in servers.items()}
    for srv in servers.values():
        srv.shutdown()
        srv.server_close()


def _loopback_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.lower() not in _PROXY_VARS}
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
    return env


def _run_probe(code: str, port: int) -> subprocess.CompletedProcess:
    probe, n = _LOOPBACK_URL.subn(f"http://127.0.0.1:{port}", code)
    assert n == 1, f"expected exactly one loopback URL in the probe, found {n}: {code!r}"
    return subprocess.run(
        [sys.executable, "-c", probe],
        env=_loopback_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def test_the_scan_sees_the_production_raster_probe():
    """العضو الذي يبنيه Railway للإنتاج في المسح — وإلّا صار الشاهد أخضرَ على لا شيء."""
    idents = {ident for ident, _ in _PYTHON_HTTP_MEMBERS}
    assert any(i.startswith("services/raster-service/Dockerfile:") for i in idents), idents
    assert "docker-compose.v9.yml::sahool-raster-service" in idents


def test_the_fixture_distinguishes_the_measured_defect(status_servers):
    """الشكلُ المعيب نفسه يخرج 0 على 503 هنا — فالحالاتُ أدناه تقيس ولا تُجامل."""
    code = "import httpx; httpx.get('http://localhost:8001/healthz')"
    assert _run_probe(code, status_servers[503]).returncode == 0
    fixed = "import httpx; httpx.get('http://localhost:8001/healthz', timeout=4).raise_for_status()"
    assert _run_probe(fixed, status_servers[503]).returncode != 0


# صورةُ raster-service يبنيها Railway للإنتاج، فإصلاحُها في التزامٍ منفصل يُقرِّر المالكُ
# توقيتَه بعد قياسٍ إنتاجيّ. حتى يهبط: xfail **صارم** — العطلُ معلَنٌ لا مخفيّ، وإصلاحُه
# دون حذف هذا السطر يُحمِّر (XPASS) فلا يبقى استثناءٌ بائت.
_PENDING_RELEASE = ("services/raster-service/Dockerfile:",)


def _cases() -> list:
    cases = []
    for ident, code in _PYTHON_HTTP_MEMBERS:
        for status in _STATUSES:
            marks = ()
            if status != 200 and ident.startswith(_PENDING_RELEASE):
                marks = pytest.mark.xfail(
                    strict=True,
                    reason="HEALTHCHECK-ACCEPTS-ANY-HTTP-STATUS-01: Dockerfile fix held for release",
                )
            cases.append(pytest.param(ident, code, status, marks=marks, id=f"{ident}-{status}"))
    return cases


@pytest.mark.parametrize(("ident", "code", "status"), _cases())
def test_python_healthcheck_exits_zero_only_on_2xx(ident, code, status, status_servers):
    proc = _run_probe(code, status_servers[status])
    if status == 200:
        assert proc.returncode == 0, f"{ident}: healthy service judged unhealthy\n{proc.stderr}"
    else:
        assert proc.returncode != 0, (
            f"{ident}: probe exits 0 on HTTP {status} — the container would be marked healthy "
            f"while its service fails. Make the probe fail on non-2xx (e.g. raise_for_status())."
        )


@pytest.mark.parametrize("ident", _CURL_MEMBERS)
def test_curl_healthcheck_fails_on_http_error(ident):
    """curl بلا `-f`/`--fail` يخرج 0 على أيّ رمز حالة."""
    toks = dict(_HEALTHCHECKS)[ident]
    flags = toks[toks.index("curl") + 1 :]
    has_fail = any(
        t in ("--fail", "--fail-with-body") or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", t)
        for t in flags
    )
    assert has_fail, f"{ident}: curl healthcheck without -f/--fail accepts any HTTP status: {toks}"
