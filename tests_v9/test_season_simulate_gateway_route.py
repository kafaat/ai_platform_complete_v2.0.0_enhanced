"""محاكاة الموسم تصل مالكها (المنصّة) خلف البوّابة، ونقاط إدخال المواسم تبقى لـscout-ingest.

العطل: المنصّة تعلن ``POST /api/v1/seasons/{season_id}/simulate``
(``services/sahool-platform/api/routers/seasons.py``، c46322c18)، لكنّ
``location ~ ^/api/v1/seasons`` في ``nginx/nginx.v9.conf`` (d9f5aa42a) مع خريطة
``$season_canonical_path`` يرسلانه إلى scout-ingest بمسار ``/internal/seasons/{id}/simulate``
الذي لا تعلنه scout-ingest ⇒ 404 خلف البوّابة (يعمل في dev-direct فقط).

اختباران متكاملان:
  ① محاكاة ساكنة لاختيار nginx للموقع (regex بترتيب الملفّ بعد بادئات ``^~``) — تعمل في كلّ بيئة.
  ② nginx حقيقيّ بخريطة المستودع ومواقعه الحرفيّة ومنبعَين وهميَّين يردّان باسمهما والمسار
     الذي استلماه. يُتخطّى فقط إن غاب ثنائيّ ``nginx`` عن البيئة.
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_CONF = Path(__file__).resolve().parents[1] / "nginx" / "nginx.v9.conf"

_SIMULATE = "/api/v1/seasons/s-123/simulate"
# مسارات scout-ingest المعلنة في route_inventory.generated.json (/internal/seasons*) بصيغتها العامّة.
_SCOUT_PATHS = {
    "/api/v1/seasons": "/internal/seasons",
    "/api/v1/seasons/s-123": "/internal/seasons/s-123",
    "/api/v1/seasons/s-123/logbook": "/internal/seasons/s-123/logbook",
    "/api/v1/seasons/s-123/events": "/internal/seasons/s-123/events",
    "/api/v1/seasons/s-123/harvest": "/internal/seasons/s-123/harvest",
    "/api/v1/seasons/s-123/costs": "/internal/seasons/s-123/costs",
    "/api/v1/seasons/s-123/detail": "/internal/seasons/s-123/detail",
    "/api/v1/seasons/s-123/accept": "/internal/seasons/s-123/accept",
}
# مسارات مواسم المنصّة الأخرى (route_inventory) — يجب ألّا تُظلَّل.
_PLATFORM_FIELD_SEASON_PATHS = (
    "/api/v1/fields/f-1/seasons",
    "/api/v1/fields/f-1/seasons/s-123",
    "/api/v1/fields/f-1/seasons/s-123/state",
)


def _conf() -> str:
    return _CONF.read_text(encoding="utf-8")


def _block(conf: str, start: int) -> tuple[str, int]:
    """الكتلة المتوازنة الأقواس التي تبدأ ترويستها عند start: (النصّ الكامل، نهايتها)."""
    i = conf.index("{", start)
    depth = 0
    for j in range(i, len(conf)):
        if conf[j] == "{":
            depth += 1
        elif conf[j] == "}":
            depth -= 1
            if depth == 0:
                return conf[start : j + 1], j + 1
    raise AssertionError(f"unbalanced braces at {start}")


def _locations(conf: str) -> list[tuple[str, str, str]]:
    """(المعدِّل، النمط، النصّ الكامل) لكلّ location في الملفّ بترتيبه."""
    out = []
    for m in re.finditer(r"^\s*location\s+(=|\^~|~\*|~)?\s*(\S+)\s*\{", conf, re.M):
        text, _ = _block(conf, m.start())
        out.append((m.group(1) or "", m.group(2), text))
    return out


def _select(conf: str, uri: str) -> str:
    """اختيار nginx: مطابقة تامّة، ثمّ أطول بادئة؛ ^~ تُوقف البحث، وإلّا أوّل regex بالترتيب."""
    locs = _locations(conf)
    for mod, pat, text in locs:
        if mod == "=" and pat == uri:
            return text
    prefixes = [
        (pat, mod, text) for mod, pat, text in locs if mod in ("", "^~") and uri.startswith(pat)
    ]
    best = max(prefixes, key=lambda p: len(p[0]), default=None)
    if best and best[1] == "^~":
        return best[2]
    for mod, pat, text in locs:
        if mod == "~" and re.search(pat, uri):
            return text
        if mod == "~*" and re.search(pat, uri, re.I):
            return text
    assert best, f"no location for {uri}"
    return best[2]


def _upstream_of(location_text: str) -> str:
    m = re.search(r"proxy_pass\s+http://([A-Za-z0-9_]+)", location_text)
    assert m, location_text
    return m.group(1)


def test_simulate_selects_platform_location_statically() -> None:
    conf = _conf()
    assert _upstream_of(_select(conf, _SIMULATE)) == "platform_backend"


def test_scout_ingest_season_paths_still_select_scout_ingest_statically() -> None:
    conf = _conf()
    for public in _SCOUT_PATHS:
        assert _upstream_of(_select(conf, public)) == "scout_ingest_backend", public


def test_platform_field_season_paths_select_platform_statically() -> None:
    conf = _conf()
    for public in _PLATFORM_FIELD_SEASON_PATHS:
        assert _upstream_of(_select(conf, public)) == "platform_backend", public


def test_simulate_location_carries_no_season_entry_trust() -> None:
    """المحاكاة على نموذج ثقة المنصّة: لا توكن خدمة مواسم ولا تصديق حافّة يُحقَن نحو المنصّة."""
    text = _select(_conf(), _SIMULATE)
    assert "SEASON_ENTRY_SERVICE_TOKEN" not in text
    assert "_auth_edge_sign" not in text
    assert "include    /etc/nginx/proxy_params.conf;" in text


# ── ② nginx حقيقيّ ────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _real_conf(tmp: Path, port: int, platform_port: int, scout_port: int) -> str:
    conf = _conf()
    m = re.search(r"map\s+\$request_uri\s+\$season_canonical_path\s*\{", conf)
    assert m
    season_map, _ = _block(conf, m.start())
    wanted = []
    for mod, pat, text in _locations(conf):
        if pat.startswith("^/api/v1/seasons") or (mod == "" and pat == "/api/v1/"):
            wanted.append(text)
    assert len(wanted) >= 3, wanted
    body = "\n".join(wanted).replace("/etc/nginx/proxy_params.conf", str(tmp / "proxy_params.conf"))
    # envsubst يملأها عند الإقلاع؛ هنا قيمة ثابتة كي لا يقرأها nginx متغيّراً مجهولاً.
    body = body.replace("${SEASON_ENTRY_SERVICE_TOKEN}", "stub-token")
    stub = 'return 200 "{name} $request_method $request_uri\\n";'
    return f"""
daemon off;
master_process off;
pid {tmp}/nginx.pid;
error_log {tmp}/error.log warn;
events {{ worker_connections 64; }}
http {{
    access_log off;
    client_body_temp_path {tmp}/cb; proxy_temp_path {tmp}/px;
    fastcgi_temp_path {tmp}/fc; uwsgi_temp_path {tmp}/uw; scgi_temp_path {tmp}/sc;
    limit_req_zone $binary_remote_addr zone=api_limit:1m rate=6000r/m;
    {season_map}
    upstream platform_backend     {{ server 127.0.0.1:{platform_port}; }}
    upstream scout_ingest_backend {{ server 127.0.0.1:{scout_port}; }}
    server {{ listen 127.0.0.1:{platform_port}; location / {{ {stub.format(name="platform")} }} }}
    server {{ listen 127.0.0.1:{scout_port};    location / {{ {stub.format(name="scout")} }} }}
    server {{
        listen 127.0.0.1:{port};
        location = /_auth_verify     {{ internal; return 200; }}
        location = /_auth_edge_sign  {{ internal; return 200; }}
        {body}
    }}
}}
"""


@pytest.mark.skipif(shutil.which("nginx") is None, reason="nginx binary not installed")
def test_real_nginx_routes_simulate_to_platform_and_entry_to_scout(tmp_path: Path) -> None:
    repo_params = _CONF.parent / "proxy_params.conf"
    (tmp_path / "proxy_params.conf").write_text(
        repo_params.read_text(encoding="utf-8"), encoding="utf-8"
    )
    port, pport, sport = _free_port(), _free_port(), _free_port()
    conf_path = tmp_path / "nginx.conf"
    conf_path.write_text(_real_conf(tmp_path, port, pport, sport), encoding="utf-8")
    check = subprocess.run(
        ["nginx", "-t", "-p", str(tmp_path), "-c", str(conf_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert check.returncode == 0, check.stderr
    proc = subprocess.Popen(
        ["nginx", "-p", str(tmp_path), "-c", str(conf_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:

        def call(path: str, method: str = "POST") -> str:
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"", method=method)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(50):
                try:
                    with opener.open(req, timeout=5) as r:
                        return r.read().decode().strip()
                except urllib.error.URLError as e:
                    if isinstance(e, urllib.error.HTTPError):
                        raise
                    time.sleep(0.1)
            raise AssertionError(f"nginx did not answer on {port}")

        assert call(_SIMULATE) == f"platform POST {_SIMULATE}"
        for public, internal in _SCOUT_PATHS.items():
            assert call(public) == f"scout POST {internal}", public
        for public in _PLATFORM_FIELD_SEASON_PATHS:
            assert call(public, "GET") == f"platform GET {public}", public
    finally:
        proc.terminate()
        proc.wait(timeout=10)
