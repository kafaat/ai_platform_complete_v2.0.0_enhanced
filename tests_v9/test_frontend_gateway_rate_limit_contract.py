"""شاهد RAILWAY-GATEWAY-HAS-NO-RATE-LIMIT-01: بوّابة Railway العامّة تحدّ معدّل مسارات الوكيل.

البوّابة العامّة على Railway هي `frontend/nginx.conf` بعد تصييرها بـ
`deploy/railway/render_frontend.py` (`deploy/railway/Dockerfile.frontend`). كانت بلا أيّ
`limit_req` بينما بوّابة v9 فيها 32. يقيس هذا الشاهد الملفَّ المصدر **والناتجَ المُصيَّر**
(ما يُحمِّله nginx على Railway فعلاً):

  • `limit_req_zone` مُعرَّفة في سياق http، ومفتاحها ليس `$remote_addr` الخام ما لم يُضبط
    real_ip — خلف حافّة Railway ذلك عنوانُ الوكيل لا العميل ⇒ دلوٌ واحد لكلّ المستخدمين.
  • كلّ موقع وكيل (/api/* · /tts/ · /auth/) يحمل `limit_req` بدفعة، وحالةُ الرفض الفعّالة 429.
  • مواقع الصحّة/الجاهزيّة والأصول الساكنة وقشرة SPA بلا `limit_req`، ولا `limit_req` على
    مستوى server/http (يُورَّث إليها).
  • الإعفاء (geo) لحلقة الاسترجاع وحدها — إعفاءُ نطاقٍ خاصّ قد يشمل الحافّة فيُلغي الحدّ.

مسحٌ ساكن بمحلّلٍ صغير لصيغة nginx (كتل/توجيهات)؛ سلوكُ 429 الحيّ قيس يدويّاً بـnginx محلّيّ.
"""

from __future__ import annotations

import importlib.util
import ipaddress
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
_spec = importlib.util.spec_from_file_location(
    "railway_frontend_rate_limit", ROOT / "deploy/railway/render_frontend.py"
)
_adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_adapter)
_ENV = {
    "SAHOOL_AUTH_UPSTREAM": "sahool-auth-main.railway.internal:8000",
    "SAHOOL_PLATFORM_UPSTREAM": "sahool-platform.railway.internal:8000",
}

# مواقع وكيلٍ مُستثناة من الحدّ عمداً، بسببٍ مكتوب.
_OPERATIONAL = {"/healthz", "/readyz", "/runtime-identity"}
_EXEMPT_PROXY = {
    "/ws/": "WebSocket طويل العمر: الحدّ يمسّ المصافحة وحدها ولا يحمي شيئاً ذا قيمة",
}
_LOOPBACK = {ipaddress.ip_network("127.0.0.1/32"), ipaddress.ip_network("::1/128")}


@dataclass
class Node:
    name: str
    args: list[str]
    children: list[Node] | None = None
    parent: Node | None = field(default=None, repr=False)

    def directives(self, name: str) -> list[Node]:
        return [c for c in self.children or [] if c.name == name]


def _tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == "#":
            i = text.find("\n", i)
            i = n if i == -1 else i
        elif ch in "{};":
            yield ch
            i += 1
        elif ch in "\"'":
            j = i + 1
            while text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            yield text[i + 1 : j]
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "{};":
                j += 1
            yield text[i:j]
            i = j


def parse(text: str) -> Node:
    root = Node("http", [], [])
    stack, words = [root], []
    for tok in _tokens(text):
        if tok == ";":
            stack[-1].children.append(Node(words[0], words[1:], None, stack[-1]))
            words = []
        elif tok == "{":
            block = Node(words[0], words[1:], [], stack[-1])
            stack[-1].children.append(block)
            stack.append(block)
            words = []
        elif tok == "}":
            assert not words, f"توجيه بلا ';' قبل '}}': {words}"
            stack.pop()
        else:
            words.append(tok)
    assert len(stack) == 1 and not words, "أقواس nginx غير متوازنة"
    return root


def _gateway_server(root: Node) -> Node:
    servers = [
        s
        for s in root.directives("server")
        if not any(a.startswith("unix:") for d in s.directives("listen") for a in d.args)
    ]
    assert len(servers) == 1, "متوقَّع خادم بوّابة واحد بمنفذ TCP"
    return servers[0]


def _limit_status(node: Node | None) -> str | None:
    while node is not None:
        found = node.directives("limit_req_status")
        if found:
            return found[-1].args[0]
        node = node.parent
    return None


def _classify(location: Node) -> str:
    path = location.args[-1]
    exact = location.args[0] == "="
    if path in _OPERATIONAL or (exact and re.search(r"/health(z)?$", path)):
        return "operational"
    if location.directives("internal"):
        return "internal"
    if not location.directives("proxy_pass"):
        return "static"
    if path in _EXEMPT_PROXY:
        return "exempt"
    return "proxy"


CONFIGS = {
    "source": SOURCE,
    "railway_rendered": _adapter.render(SOURCE, _ENV, ["10.0.0.2"]),
}


@pytest.fixture(params=sorted(CONFIGS), ids=sorted(CONFIGS))
def gateway(request):
    root = parse(CONFIGS[request.param])
    return root, _gateway_server(root)


def test_zones_are_declared_and_not_keyed_on_the_edge_proxy_address(gateway):
    root, _ = gateway
    zones = root.directives("limit_req_zone")
    assert zones, "بوّابة Railway بلا limit_req_zone (RAILWAY-GATEWAY-HAS-NO-RATE-LIMIT-01)"
    trusts_forwarded = bool(root.directives("set_real_ip_from"))
    for zone in zones:
        key = zone.args[0]
        assert trusts_forwarded or key not in {"$remote_addr", "$binary_remote_addr"}, (
            f"{zone.args}: خلف حافّة Railway `$remote_addr` عنوانُ الوكيل ⇒ دلوٌ واحد للجميع"
        )


def test_every_proxy_location_is_limited_with_burst_and_429(gateway):
    root, server = gateway
    zone_names = {
        a.split("=", 1)[1].split(":")[0]
        for z in root.directives("limit_req_zone")
        for a in z.args
        if a.startswith("zone=")
    }
    proxies = [loc for loc in server.directives("location") if _classify(loc) == "proxy"]
    paths = {loc.args[-1] for loc in proxies}
    assert {"/api/", "/auth/", "/api/raster/"} <= paths, f"مسح فارغ؟ {sorted(paths)}"
    for loc in proxies:
        path = loc.args[-1]
        limits = loc.directives("limit_req")
        assert limits, f"`location {' '.join(loc.args)}` يُوكِّل بلا limit_req"
        for lim in limits:
            opts = dict(a.split("=", 1) for a in lim.args if "=" in a)
            assert opts.get("zone") in zone_names, f"{path}: منطقة غير مُعرَّفة {opts}"
            assert int(opts.get("burst", "0")) >= 10, f"{path}: بلا دفعة ⇒ التوازي يُرفَض"
        assert _limit_status(loc) == "429", f"{path}: حالة الرفض الفعّالة ليست 429"


def test_health_readiness_static_and_spa_are_never_limited(gateway):
    root, server = gateway
    assert not root.directives("limit_req"), "limit_req في سياق http يُورَّث إلى الصحّة"
    assert not server.directives("limit_req"), "limit_req على مستوى server يُورَّث إلى الصحّة"
    seen = set()
    for loc in server.directives("location"):
        kind = _classify(loc)
        if kind in {"operational", "static", "internal", "exempt"}:
            seen.add(kind)
            assert not loc.directives("limit_req"), (
                f"`location {' '.join(loc.args)}` ({kind}) يجب ألّا يُحدّ"
            )
    assert {"operational", "static"} <= seen, "لم يُعثر على مواقع الصحّة/الساكنة — مسحٌ فارغ"


def test_rate_limit_exemption_covers_loopback_only(gateway):
    root, _ = gateway
    for geo in root.directives("geo"):
        for entry in geo.children:
            if entry.name in {"default", "proxy", "ranges", "delete", "include"}:
                continue
            if entry.args and entry.args[0] not in {"0", '""', ""}:
                net = ipaddress.ip_network(entry.name, strict=False)
                assert net in _LOOPBACK, (
                    f"geo {geo.args}: {entry.name} مُعفى — قد يشمل حافّة Railway فيُلغي الحدّ"
                )


def test_parser_sees_the_pre_fix_gap():
    """التكذيب: الشكل السابق (بلا limit_req) يجب أن يُرفض، لا أن يمرّ مسحاً فارغاً."""
    stripped = re.sub(r"(?m)^\s*limit_req(?:_zone|_status)?\s[^;]*;\n", "", SOURCE)
    root = parse(stripped)
    assert not root.directives("limit_req_zone")
    server = _gateway_server(root)
    unlimited = [
        loc.args[-1]
        for loc in server.directives("location")
        if _classify(loc) == "proxy" and not loc.directives("limit_req")
    ]
    assert "/api/" in unlimited and "/auth/" in unlimited
