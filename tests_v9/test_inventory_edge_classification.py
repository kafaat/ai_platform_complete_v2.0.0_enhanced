"""الحافّةُ المعلَنة بلا موضع نداء ليست مُثبَتةً ولا منفيّة — فتُصنَّف ثلاثاً، ولكلٍّ دليلُه.

``A-DECLARED-EDGE-WITHOUT-A-CALL-SITE-IS-NEITHER-PROVEN-NOR-ABSENT-01``. بعد حسم نداءات الواجهة كان الباقي كلُّه
``declared`` بلا تمييز: ما يبنيه العميلُ وقتَ التشغيل، وما لا يبلغه الماسح، وما لا يُنادى أصلاً. هنا:

* **مُثبَتة** بصنف دليلٍ ثانٍ: اشتراكُ NATS في مصدر Python (جدولٌ · استيرادٌ · حلقةٌ · ``subscribe``) بأسطرها.
* **منفيّة في نطاقٍ مسمّى** (``gateway_mode``): منتِجٌ لا يوجّه إليه ``nginx.conf``، أو عمليّةٌ لا يبلغها أيُّ موقع.
* **مجهولة** بسببٍ مسمّى وموضعٍ ``path:line``، والأسبابُ المقبولة قرارٌ في ``inventory_edge_exemptions.json``.

الشاهدُ الحيّ على الشجرة الحقيقيّة: كلُّ عمليّةٍ معلَنةٍ في واحدةٍ من الثلاث بالضبط، ولا مجهولَ بلا سببٍ مُعلَن.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "build_main_inventory_classification", ROOT / "scripts/diagnostics/build_main_inventory.py"
)
inventory = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = inventory
assert _SPEC.loader is not None
_SPEC.loader.exec_module(inventory)
edges = inventory._resolver()
EXEMPTIONS = ROOT / "docs/architecture/inventory_edge_exemptions.json"


def _operations(rows):
    return {
        (row["from"], row["to"], row["capability_id"], op)
        for row in rows
        for op in row.get("entrypoints") or [None]
    }


# ── الشاهدُ الحيّ ────────────────────────────────────────────────────────────────


def test_every_declared_operation_on_the_live_tree_is_proven_refuted_or_exempted():
    classify = getattr(edges, "classify", None)
    assert classify is not None, (
        "لا تصنيفَ لما بعد الحسم: كلُّ عمليّةٍ معلَنةٍ بلا موضع نداءٍ تبقى declared — لا مُثبَتةً ولا منفيّة"
    )
    _, declared = inventory.integration_edges(inventory.load_capabilities())
    out = classify(declared, inventory.load_components(), ROOT)
    proven, refuted, unknown = (
        _operations(out["proven"]),
        _operations(out["refuted"]),
        _operations(out["unknown"]),
    )
    assert proven | refuted | unknown == _operations(declared), "عمليّةٌ ضاعت أو أضيفت"
    assert not (proven & refuted or proven & unknown or refuted & unknown), "عمليّةٌ في صنفين"
    assert refuted, "لا نفيَ على الشجرة الحيّة — مسارُ النفي منقطع"
    assert any(r["evidence"]["kind"] == "python_nats_subscription" for r in out["proven"]), (
        "صنفُ الدليل الثاني (اشتراكُ NATS) لم يُثبت حافّةً واحدة"
    )
    for row in out["refuted"]:
        assert row["refutation"]["scope"] == "gateway_mode"
        assert row["refutation"]["upstream_declarations"]
    exemptions = json.loads(EXEMPTIONS.read_text(encoding="utf-8"))
    assert edges.exemption_problems(out["unknown"], exemptions) == []
    for row in out["unknown"]:
        for entrypoint in row["entrypoints"]:
            for entry in row["unknown_reasons"][entrypoint]:
                assert all(":" in site or "#" in site for site in entry["sites"]), entry


def test_the_scanner_reads_encoded_segments_non_null_members_and_drops_queries():
    assert edges.template_path("/a/${encodeURIComponent(id ?? '')}/b") == "/a/{}/b"
    assert edges.template_path("/t/${tile!.z}/${tile!.x}") == "/t/{}/{}"
    assert edges.template_path("/h/${id}/history?limit=8") == "/h/{}/history"
    # ترميزٌ لا يملأ مقطعاً كاملاً، أو نداءٌ آخر، أو تعبيرٌ مركّب: يبقى عمىً معلَناً
    for raw in (
        "/a/${encodeURIComponent(x)}y",
        "/a/${encodeURIComponent(x) + y}",
        "/a/${choosePath()}",
        "/w/${a + b}",
    ):
        assert edges.template_path(raw) is None, raw


# ── شجرةٌ صغيرة بمُدخَلاتٍ حقيقيّة الشكل ─────────────────────────────────────────────

_NGINX = (
    "upstream backend {\n server svc:8000;\n}\n"
    "location /api/ {\n proxy_pass http://backend/v1/;\n}\n"
    "location = /api/health {\n proxy_pass http://backend/healthz;\n}\n"
)


def _tree(tmp_path: Path, body: str = "", *, nginx: str | None = _NGINX, extra=None) -> Path:
    files = {
        "frontend/src/config/endpoints.ts": "  platform: resolveHttpBase('VITE_PLATFORM', '/api', ''),\n",
        "frontend/src/services/api/client.ts": (
            "const PLATFORM_URL = ENDPOINTS.platform;\nexport const kongApi = makeClient(PLATFORM_URL);\n"
        ),
        "frontend/src/page.tsx": body + '\nimport { kongApi } from "./services/api/client";\n',
        **(extra or {}),
    }
    if nginx is not None:
        files["frontend/nginx.conf"] = nginx
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


_COMPONENTS = [
    {"component_id": "svc", "aliases": [], "compose_services": [], "source_path": "services/svc"},
    {"component_id": "other", "aliases": [], "compose_services": [], "source_path": "services/o"},
    {
        "component_id": "notifier",
        "aliases": [],
        "compose_services": [],
        "source_path": "agents/notifier",
    },
]


def _edge(producer, op, consumer="frontend"):
    return {
        "from": producer,
        "to": consumer,
        "capability_id": f"{producer}:{op}",
        "entrypoints": [op],
    }


def _reasons(out, op):
    row = next(r for r in out["unknown"] if op in r["entrypoints"])
    return row["unknown_reasons"][op]


def test_a_producer_the_gateway_never_routes_to_is_refuted_in_gateway_scope(tmp_path):
    out = edges.classify([_edge("other", "GET /v1/x")], _COMPONENTS, _tree(tmp_path))
    (row,) = out["refuted"]
    assert row["refutation"]["kind"] == "producer_has_no_gateway_upstream"
    assert row["refutation"]["scope"] == "gateway_mode"
    assert row["refutation"]["upstream_declarations"] == ["frontend/nginx.conf:2"]


def test_without_a_gateway_file_nothing_is_refuted(tmp_path):
    """غيابُ ملفّ البوّابة غيابُ قياسٍ لا دليلُ نفي."""
    out = edges.classify([_edge("other", "GET /v1/x")], _COMPONENTS, _tree(tmp_path, nginx=None))
    assert out["refuted"] == []
    assert _reasons(out, "GET /v1/x")[0]["reason"] == "no_static_evidence_class_for_this_edge_kind"


def test_an_operation_no_location_reaches_is_refuted_and_exact_locations_shadow(tmp_path):
    out = edges.classify(
        [_edge("svc", "GET /v2/thing"), _edge("svc", "GET /v1/health")],
        _COMPONENTS,
        _tree(tmp_path),
    )
    kinds = {r["entrypoints"][0]: r["refutation"]["kind"] for r in out["refuted"]}
    # /v2 لا يبلغه موقع؛ و/api/health موقعٌ تامٌّ يوجّه إلى /healthz فلا يبلغ /v1/health أحد
    assert kinds == {
        "GET /v2/thing": "operation_not_routed_by_gateway",
        "GET /v1/health": "operation_not_routed_by_gateway",
    }


def test_a_dynamic_call_keeps_a_compatible_operation_unknown_with_its_site(tmp_path):
    body = "kongApi.get(`/fields/${choose()}`);\nkongApi.post(url);"
    out = edges.classify(
        [
            _edge("svc", "GET /v1/fields/{id}"),
            _edge("svc", "GET /v1/zones"),
            _edge("svc", "POST /v1/q"),
        ],
        _COMPONENTS,
        _tree(tmp_path, body),
    )
    assert _reasons(out, "GET /v1/fields/{id}")[0] == {
        "reason": "dynamic_call_may_reach",
        "sites": ["frontend/src/page.tsx:1"],
    }
    # البادئةُ الحرفيّة /fields لا تبلغ /zones، ولا نداءَ GET آخر: تبلغها البوّابة ولم يرها الماسح
    assert _reasons(out, "GET /v1/zones") == [
        {"reason": "not_seen_by_axios_scanner", "sites": ["frontend/nginx.conf:5"]}
    ]
    assert _reasons(out, "POST /v1/q")[0]["sites"] == ["frontend/src/page.tsx:2"]


def test_a_client_passed_as_value_is_a_named_reason(tmp_path):
    body = "const SERVICES = [{ api: kongApi, path: '/x' }];"
    out = edges.classify([_edge("svc", "DELETE /v1/x")], _COMPONENTS, _tree(tmp_path, body))
    assert _reasons(out, "DELETE /v1/x") == [
        {"reason": "client_passed_as_value", "sites": ["frontend/src/page.tsx:1"]}
    ]


_TABLE = (
    'SUBSCRIPTIONS = [\n    ("sahool.events.>", "notif_domain"),\n    ("sahool.a", "notif_a"),\n]\n'
)
_AGENT = (
    "from shared.consumers import SUBSCRIPTIONS\n\n\n"
    "async def ensure(js):\n"
    "    for subject, durable in SUBSCRIPTIONS:\n"
    "        await js.subscribe(subject, durable=durable)\n"
)


def test_a_python_nats_subscription_is_a_second_evidence_class(tmp_path):
    root = _tree(
        tmp_path,
        extra={"shared/consumers.py": _TABLE, "agents/notifier/agent.py": _AGENT},
    )
    edge = _edge("producer", "NATS sahool.events.>", consumer="notifier (notif_domain)")
    out = edges.classify([edge], _COMPONENTS, root)
    (row,) = out["proven"]
    assert row["evidence"] == {
        "kind": "python_nats_subscription",
        "evidence_scope": "static_source_only",
        "subject": "sahool.events.>",
        "durable": "notif_domain",
        "table_row": "shared/consumers.py:2",
        "import": "agents/notifier/agent.py:1",
        "loop": "agents/notifier/agent.py:5",
        "subscribe_calls": ["agents/notifier/agent.py:6"],
    }
    # بلا نداء subscribe بمتغيّر الحلقة تنقطع السلسلة: لا ترقيةَ بنصفها
    (tmp_path / "agents/notifier/agent.py").write_text(
        _AGENT.replace("js.subscribe(subject", "js.subscribe('other'"), encoding="utf-8"
    )
    out = edges.classify([edge], _COMPONENTS, root)
    assert out["proven"] == []
    assert _reasons(out, "NATS sahool.events.>")[0]["reason"] == (
        "no_static_evidence_class_for_this_edge_kind"
    )


def test_exemption_problems_red_on_unlisted_unjustified_and_stale_reasons():
    unknown = [
        {
            "from": "svc",
            "entrypoints": ["GET /a", "GET /b"],
            "unknown_reasons": {
                "GET /a": [{"reason": "dynamic_call_may_reach", "sites": ["f.ts:1"]}],
                "GET /b": [],
            },
        }
    ]
    ok = {"justification": "j", "closing_condition": "c"}
    problems = edges.exemption_problems(
        unknown, {"accepted_unknown_reasons": {"client_passed_as_value": ok}}
    )
    assert "unlisted_reason: dynamic_call_may_reach" in problems
    assert "stale_reason: client_passed_as_value" in problems
    assert "unknown_without_reason: svc GET /b" in problems
    problems = edges.exemption_problems(
        [{**unknown[0], "entrypoints": ["GET /a"]}],
        {"accepted_unknown_reasons": {"dynamic_call_may_reach": {"justification": " "}}},
    )
    assert "unjustified_reason: dynamic_call_may_reach" in problems


# ── صنفُ الدليل الثالث: نداءُ HTTP في مصدر Python (خدمةٌ ⇒ خدمة) ──────────────────────────────────


def _planted_service_edge(entrypoint: str, consumer: str):
    """حافّةُ خدمةٍ تُزرع **من الجرد نفسِه**: القدرةُ التي تحمل العمليّةَ تُقرأ من الكتالوج، ويُعلَن لها مستهلكٌ
    خدميّ. الكتالوجُ اليوم لا يُعلن مستهلكاً خدميّاً لأيّ عمليّة HTTP (المستهلكون ``frontend`` أو اشتراكاتُ NATS)،
    فالزرعُ هو ما يقيس الصنفَ على الشجرة الحيّة."""
    (cap,) = [c for c in inventory.load_capabilities() if entrypoint in c["entrypoints"]]
    planted = {**cap, "consumers_declared": [consumer], "entrypoints": [entrypoint]}
    _, declared = inventory.integration_edges([planted])
    return declared


def _line_text(anchor: str) -> str:
    path, number = anchor.rsplit(":", 1)
    return (ROOT / path).read_text(encoding="utf-8").splitlines()[int(number) - 1]


@pytest.mark.parametrize(
    ("consumer", "entrypoint", "env_var", "host", "port"),
    [
        (
            "field-segmentation",
            "POST /v1/predict",
            "SEGMENTATION_INFERENCE_URL",
            "sahool-sam2-inference",
            8080,
        ),
        (
            "vegetation-analysis-service",
            "POST /api/v1/execution-requests/{execution_request_id}/verify-outcome",
            "PLATFORM_API_URL",
            "sahool-platform",
            8000,
        ),
    ],
)
def test_the_live_tree_proves_a_service_edge_from_a_python_call_site(
    consumer, entrypoint, env_var, host, port
):
    """**field-segmentation⇒SAM2 ومخرجاتُ التحليل⇒تحقّقُ المنصّة** — الحافّتان اللتان سمّتهما المدخلة، مُثبَتتان بسلسلةٍ
    كلُّ خطوةٍ فيها سطرٌ يُقرأ ويحمل ما يُدّعى عنه: النداء · قراءةُ البيئة · قيمةُ compose · المضيف · المنفذ · المسار."""
    declared = _planted_service_edge(entrypoint, consumer)
    out = edges.classify(declared, inventory.load_components(), ROOT)
    rows = [r for r in out["proven"] if r["evidence"].get("kind") == "python_http_call_site"]
    assert rows, (
        f"حافّةُ الخدمة {consumer}⇒{declared[0]['from']} ({entrypoint}) لم تُثبَت من مصدر Python: "
        f"{[r.get('unknown_reasons') for r in out['unknown']]}"
    )
    evidence = rows[0]["evidence"]
    assert rows[0]["resolved_entrypoint"] == entrypoint
    assert evidence["operation"] == entrypoint
    assert re.search(r"\.(post|get|put|patch|delete)\(", _line_text(evidence["call_site"]))
    assert "Client(" in _line_text(evidence["client_binding"])
    (step,) = [s for s in evidence["env_steps"] if s["env_var"] == env_var]
    assert env_var in _line_text(step["env_read"])
    compose_line = _line_text(step["env_value"])
    assert env_var in compose_line and f"{host}:{port}" in compose_line
    assert evidence["host"] == host and host in _line_text(evidence["host_binding"])
    assert evidence["port"] == port and str(port) in _line_text(evidence["port_binding"])
    # سطرُ المسار في الجرد هو سطرُ الدالّة أو مُزخرِفِها — فالمسارُ الحرفيُّ في أحدهما
    route_file, route_line = evidence["provider_route"].rsplit(":", 1)
    window = [_line_text(f"{route_file}:{n}") for n in (int(route_line) - 1, int(route_line))]
    assert any(entrypoint.split(None, 1)[1] in text for text in window), window


def test_the_live_tree_reports_service_edges_the_catalog_does_not_declare():
    """السلاسلُ الكاملة التي لا يقابلها إعلانٌ تُعرض اكتشافاً (``observed_undeclared``) لا ترقية — والكتالوجُ لا يُعلن
    field-segmentation مستهلكاً لـSAM2، فتظهر هناك بالضبط."""
    _, declared = inventory.integration_edges(inventory.load_capabilities())
    out = edges.classify(declared, inventory.load_components(), ROOT)
    python_http = out["report"]["classification"]["python_http"]
    assert python_http["chains_located"] > 0
    assert {
        "consumer": "field-segmentation",
        "provider": "sam2-inference",
        "operation": "POST /v1/predict",
        "call_site": "services/field-segmentation/main.py:195",
    } in python_http["observed_undeclared"]


_COMPOSE = """services:
  cons:
    environment:
      PROVIDER_URL: ${PROVIDER_URL:-http://prov:9000}
      REQUIRED_URL: ${REQUIRED_URL:?required}
      OTHER_URL: http://other:9000
      WRONG_PORT_URL: http://prov:9999
  prov:
    expose:
    - "9000"
  other:
    expose:
    - "9000"
"""

_ROUTES = [
    {
        "service": "prov",
        "file": "services/prov/main.py",
        "line": 3,
        "method": "GET",
        "path": "/v1/items/{item_id}",
    },
    {
        "service": "prov",
        "file": "services/prov/main.py",
        "line": 7,
        "method": "POST",
        "path": "/v1/run",
    },
    {
        "service": "other",
        "file": "services/other/main.py",
        "line": 3,
        "method": "POST",
        "path": "/v1/run",
    },
]

_SERVICE_COMPONENTS = [
    {
        "component_id": c,
        "component_kind": "service",
        "aliases": [],
        "compose_services": [c],
        "source_path": f"services/{c}",
    }
    for c in ("cons", "prov", "other")
]


def _service_tree(tmp_path: Path, consumer_source: str, compose: str = _COMPOSE) -> Path:
    files = {
        "docker-compose.v9.yml": compose,
        "route_inventory.generated.json": json.dumps(_ROUTES),
        "services/cons/main.py": consumer_source,
        "services/prov/main.py": "",
        "services/other/main.py": "",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def _service_out(tmp_path, source, *ops, compose=_COMPOSE):
    declared = [_edge("prov", op, consumer="cons") for op in ops]
    return edges.classify(declared, _SERVICE_COMPONENTS, _service_tree(tmp_path, source, compose))


def test_the_base_url_resolves_through_compose_then_the_code_default(tmp_path):
    source = (
        "import os\n"
        "import httpx\n"
        "BASE = os.getenv('PROVIDER_URL', 'http://nowhere:1')\n"
        "LOCAL = os.getenv('NOT_IN_COMPOSE', 'http://prov:9000').rstrip('/')\n"
        "def run():\n"
        "    with httpx.Client() as c:\n"
        "        c.post(BASE + '/v1/run')\n"
        "async def item(item_id):\n"
        "    async with httpx.AsyncClient(base_url=LOCAL) as c:\n"
        "        await c.get(f'/v1/items/{item_id}')\n"
    )
    out = _service_out(tmp_path, source, "POST /v1/run", "GET /v1/items/{item_id}")
    by_op = {r["resolved_entrypoint"]: r["evidence"] for r in out["proven"]}
    run = by_op["POST /v1/run"]
    # قيمةُ compose تغلب الافتراضيَّ في الكود — وسطرُها هو الدليل
    assert run["env_steps"] == [
        {
            "env_var": "PROVIDER_URL",
            "env_read": "services/cons/main.py:3",
            "env_value": "docker-compose.v9.yml:4",
        }
    ]
    assert run["call_site"] == "services/cons/main.py:7"
    assert run["client_binding"] == "services/cons/main.py:6"
    assert run["host_binding"] == "docker-compose.v9.yml:8"
    assert run["port_binding"] == "docker-compose.v9.yml:10"
    assert run["provider_route"] == "services/prov/main.py:7"
    # متغيّرٌ لا يُعلنه compose ⇒ الافتراضيُّ الحرفيُّ في الكود، وموضعُه سطرُ القراءة نفسُه
    item = by_op["GET /v1/items/{item_id}"]
    assert item["env_steps"][0]["env_value"] == "services/cons/main.py:4"
    assert item["provider_route"] == "services/prov/main.py:3"
    assert out["unknown"] == []


def test_an_operator_supplied_value_is_unknown_not_proven(tmp_path):
    source = (
        "import os\nimport httpx\nURL = os.environ['REQUIRED_URL']\n"
        "def run():\n    httpx.post(f'{URL}/v1/run')\n"
    )
    out = _service_out(tmp_path, source, "POST /v1/run")
    assert out["proven"] == [] and out["refuted"] == []
    assert _reasons(out, "POST /v1/run") == [
        {"reason": "base_url_unresolved", "sites": ["services/cons/main.py:5"]}
    ]


def test_a_dynamic_path_matches_only_as_a_whole_segment_template(tmp_path):
    source = (
        "import os\nimport httpx\nBASE = os.getenv('PROVIDER_URL')\n"
        "def by_path(path):\n    httpx.post(f'{BASE}/{path}')\n"
        "def partial(x):\n    httpx.get(f'{BASE}/v1/items/x{x}')\n"
    )
    out = _service_out(tmp_path, source, "POST /v1/run", "GET /v1/items/{item_id}")
    assert out["proven"] == [], "مسارٌ ديناميٌّ بلا بادئةٍ ثابتة أو بمقطعٍ جزئيّ رُقّي بالتخمين"
    assert _reasons(out, "POST /v1/run") == [
        {"reason": "dynamic_path", "sites": ["services/cons/main.py:5"]}
    ]
    assert _reasons(out, "GET /v1/items/{item_id}") == [
        {"reason": "dynamic_path", "sites": ["services/cons/main.py:7"]}
    ]


def test_a_call_to_another_host_or_port_never_proves_the_edge(tmp_path):
    source = (
        "import os\nimport httpx\n"
        "OTHER = os.getenv('OTHER_URL')\nWRONG = os.getenv('WRONG_PORT_URL')\n"
        "def run():\n    httpx.post(OTHER + '/v1/run')\n    httpx.post(WRONG + '/v1/run')\n"
    )
    out = _service_out(tmp_path, source, "POST /v1/run")
    assert out["proven"] == [] and out["refuted"] == [], (
        "مضيفٌ آخر أو منفذٌ لا يُستمع عليه ليس دليلاً — ولا نفياً"
    )
    # النداءُ إلى ``other`` حافّةٌ أخرى (مكتشَفة لا معلَنة)؛ وإلى منفذٍ لا يخدمه المنتِج: سلسلةٌ منقطعة بموضعها
    assert _reasons(out, "POST /v1/run") == [
        {"reason": "base_url_unresolved", "sites": ["services/cons/main.py:7"]}
    ]
    observed = out["report"]["classification"]["python_http"]["observed_undeclared"]
    assert {
        "consumer": "cons",
        "provider": "other",
        "operation": "POST /v1/run",
        "call_site": "services/cons/main.py:6",
    } in observed


def test_an_unseen_service_edge_stays_unknown_and_is_never_silent(tmp_path):
    """لا نداءَ يُرى ⇒ مجهولٌ بموضع مسار المنتِج — لا منفيّ. وسببٌ لم يُقرَّر في سجلّ الاستثناءات يُحمِّر: لا مجهولَ صامت."""
    source = "import httpx\nCACHE = {}\ndef f():\n    return CACHE.get('/v1/run')\n"
    out = _service_out(tmp_path, source, "POST /v1/run")
    assert out["proven"] == [] and out["refuted"] == []
    assert _reasons(out, "POST /v1/run") == [
        {"reason": "not_seen_by_python_http_scanner", "sites": ["services/prov/main.py:7"]}
    ]
    exemptions = json.loads(EXEMPTIONS.read_text(encoding="utf-8"))
    assert "unlisted_reason: not_seen_by_python_http_scanner" in edges.exemption_problems(
        out["unknown"], exemptions
    )
