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
