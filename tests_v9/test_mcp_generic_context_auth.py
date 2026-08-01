"""‏`MCP-GENERIC-CONTEXT-AUTH-MISSING-01` — سياق المستأجِر لا يُقرأ بلا هويّة.

`generic_context_server` كان **الوحيد** بين خوادم MCP بلا أيّ مصادقة: لا `require_scope`
ولا `Depends` ولا middleware — بينما تشتقّ منه **ستّ** خدمات منشورة في
`docker-compose.rag-kg-mcp.yml` (‏`field` · `lab` · `satellite` · `iot` · `rag` ·
`knowledge-graph`). الشبكة `sahool-internal` بلا `ports:`، لكنّ **«داخليّ» ليس
«مُصادَق»**: أيّ حِمل داخل الشبكة الموثوقة كان يقرأ سياق مستأجِرين بلا هويّة.

**الاختبار الحاسم هنا اختبار الوراثة، لا اختبار الوحدة الأصليّة.** «المشتقّ» في هذه
البنية ليس صنفاً وارثاً بل **نفس الوحدة بقيمة `MCP_SERVICE` مختلفة**، فاختبارٌ يفحص
تطبيقاً واحداً يترك خمسةً بلا برهان. تُبنى الستّة هنا بإعادة تحميل الوحدة لكلّ قيمة.

وحدّ صدق صريح: هذا يُثبِت **الحراسة**، لا أنّ التوكن يحمل المستأجِر الصحيح — تحقّق
`tenant_id` داخل `require_scope` مسؤوليّة مُثبَتة في مكانها، لا هنا.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = ROOT / "services" / "mcp_servers"

# القيم الستّ المنشورة فعلاً — مأخوذة من `MCP_SERVICE` في docker-compose.rag-kg-mcp.yml،
# لا من تعداد في الكود: لو أضيفت خدمة سابعة هناك بلا حراسة وجب أن يُكشف ذلك.
DEPLOYED_SERVICES = ("field", "lab", "satellite", "iot", "rag", "knowledge-graph")

GUARDED_ROUTES = {("GET", "/v1/mcp/tools"), ("POST", "/v1/mcp/tools/call")}
OPEN_ROUTES = {("GET", "/healthz"), ("GET", "/readyz")}


@pytest.fixture(scope="module")
def mcp_on_path():
    if str(MCP_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_DIR))
    pytest.importorskip("fastapi")
    pytest.importorskip("jwt")


def _install_real_oauth_middleware() -> None:
    """يفرض الحارس **الحقيقيّ** في `sys.modules` قبل بناء التطبيق.

    ``MCP-TEST-STUB-NEUTERS-AUTH-01``: ملفّ اختبار آخر
    (`test_mcp_weather_et0_engine_delegation.py:50-53`) يحقن كعباً لـ
    `shared.oauth_middleware` في `sys.modules` **وقت الاستيراد** — أي أثناء جمع pytest،
    قبل تشغيل أيّ اختبار — و`require_scope` فيه ``lambda: None``. فأيّ خادم MCP يُستورَد
    بعده يُبنى **بلا حراسة**، ويصير اختبار الأمن أخضر على تطبيق غير محروس.

    كشفتُه لأنّ اختباراتي تؤكّد **سلوكاً** (401/403) لا بنيةً: تحت المجموعة الكاملة
    ظهر أنّ الـdependency المرتبطة بالمسار هي ``<lambda>`` من ذلك الملفّ. ولو اكتفيتُ
    بفحص «هل توجد dependency؟» لمرّ الاختبار على حارس مُبطَل.

    فيُحمَّل الملفّ الحقيقيّ بمساره ويُثبَّت — فلا تعتمد النتيجة على ترتيب الجمع.
    """
    real = MCP_DIR / "shared" / "oauth_middleware.py"
    spec = importlib.util.spec_from_file_location("shared.oauth_middleware", real)
    module = importlib.util.module_from_spec(spec)
    sys.modules["shared.oauth_middleware"] = module
    spec.loader.exec_module(module)


def _app_for(service: str):
    """يبني التطبيق كما يُبنى في الحاوية: نفس الوحدة، `MCP_SERVICE` مختلفة."""
    os.environ["MCP_SERVICE"] = service
    os.environ["JWT_SECRET"] = "x" * 40
    _install_real_oauth_middleware()
    module = importlib.import_module("generic_context_server")
    return importlib.reload(module)


def _guard_dependencies(app, method: str, path: str) -> list[str]:
    """الـdependencies المفروضة على مسار — من كائن المسار نفسه لا من نصّ الملفّ.

    الفحص على `__qualname__` للدالّة المُغلَّفة: `require_scope` مصنع يُرجِع `_check`،
    فاسمها المؤهَّل `require_scope.<locals>._check` — وهذا يميّز حارس النطاق عن أيّ
    dependency أخرى قد تُضاف لاحقاً، فلا يمرّ الاختبار بمجرّد وجود «أيّ» dependency.
    """
    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
            return [
                getattr(dep.dependency, "__qualname__", "")
                for dep in getattr(route, "dependencies", [])
            ]
    raise AssertionError(f"المسار غير موجود: {method} {path}")


@pytest.mark.parametrize("service", DEPLOYED_SERVICES)
def test_every_deployed_service_inherits_the_guard(mcp_on_path, service):
    """الوراثة: كلّ قيمة منشورة تُنتج تطبيقاً محروساً — لا التطبيق الافتراضيّ وحده."""
    module = _app_for(service)
    for method, path in GUARDED_ROUTES:
        deps = _guard_dependencies(module.app, method, path)
        assert any("require_scope" in name for name in deps), (
            f"{service}: {method} {path} بلا حارس نطاق — الحراسة لا تُورَث لهذه الخدمة"
        )


@pytest.mark.parametrize("service", DEPLOYED_SERVICES)
def test_unauthenticated_calls_are_rejected_for_every_service(mcp_on_path, service):
    """السلوك لا البنية: طلب بلا اعتماد يُرفَض على كلّ خدمة مشتقّة."""
    from fastapi.testclient import TestClient

    module = _app_for(service)
    client = TestClient(module.app, raise_server_exceptions=False)
    assert client.post("/v1/mcp/tools/call", json={"name": "x", "arguments": {}}).status_code == 401
    assert client.get("/v1/mcp/tools").status_code == 401


def test_the_status_matrix_distinguishes_identity_from_permission(mcp_on_path):
    """‏401 مقابل 403: «مَن أنت» غير «هل يُسمح لك».

    خلطهما يجعل المُشغّل يطارد مشكلة صلاحيّات وهو بلا هويّة أصلاً — وهو العيب الذي
    وُصِف خطأً في `MCP-PREAUTH-STATUS-01`.
    """
    import jwt
    from fastapi.testclient import TestClient

    secret = "x" * 40
    os.environ["JWT_SECRET"] = secret
    module = _app_for("field")
    client = TestClient(module.app, raise_server_exceptions=False)
    # اسم أداة حقيقيّ من TOOLSETS["field"] — اسم وهميّ كان سيُنتج 404 بعد الحارس
    # فيبدو الرفض نجاحاً في الاختبار الأخير بينما لم يُختبَر المرور أصلاً.
    tool = next(iter(module.TOOLSETS["field"]))
    body = {"name": tool, "arguments": {"field_id": "f1", "tenant_id": "t1"}}

    def token(scope: str) -> str:
        return jwt.encode(
            {"iss": "sahool-auth", "aud": "sahool", "scope": scope, "tenant_id": "t1"},
            secret,
            algorithm="HS256",
        )

    assert client.post("/v1/mcp/tools/call", json=body).status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.post("/v1/mcp/tools/call", json=body, headers=bad).status_code == 401
    wrong = {"Authorization": f"Bearer {token('weather:read')}"}
    assert client.post("/v1/mcp/tools/call", json=body, headers=wrong).status_code == 403
    right = {"Authorization": f"Bearer {token(module.MCP_CONTEXT_SCOPE)}"}
    assert client.post("/v1/mcp/tools/call", json=body, headers=right).status_code < 300


def test_liveness_probes_stay_open(mcp_on_path):
    """‏`/healthz`/`/readyz` تبقى بلا حراسة عمداً: مُنسّق الحاويات لا يحمل توكناً،
    وحراستها تُنتج إعادة تشغيل لا نهائيّة — وهي لا تكشف سياق مستأجِر."""
    from fastapi.testclient import TestClient

    module = _app_for("field")
    client = TestClient(module.app, raise_server_exceptions=False)
    for _method, path in OPEN_ROUTES:
        assert client.get(path).status_code == 200


def test_the_deployed_service_list_matches_compose(mcp_on_path):
    """الأساس يُشتقّ من ملفّ النشر لا من تعداد في الاختبار.

    لو أُضيفت خدمة سابعة تشتقّ من هذه الوحدة وجب أن تدخل قائمة الوراثة أعلاه — وإلّا
    نجح الاختبار على ستّة وتُركت السابعة بلا برهان.
    """
    compose = (ROOT / "docker-compose.rag-kg-mcp.yml").read_text(encoding="utf-8")
    blocks = compose.split("MCP_SERVER_MODULE: generic_context_server")
    declared = set()
    for block in blocks[1:]:
        for line in block.splitlines():
            if "MCP_SERVICE:" in line:
                declared.add(line.split("MCP_SERVICE:")[1].strip())
                break
    assert declared == set(DEPLOYED_SERVICES), (
        f"قائمة الخدمات المشتقّة تغيّرت في compose: {sorted(declared)} — "
        "حدّث DEPLOYED_SERVICES كي لا تبقى خدمة بلا برهان حراسة"
    )


def test_the_guard_bound_to_the_route_is_the_real_one(mcp_on_path):
    """‏`MCP-TEST-STUB-NEUTERS-AUTH-01` — الحارس المرتبط بالمسار من وحدته الحقيقيّة.

    كعبٌ مُحقَن في `sys.modules` يجعل `require_scope` يُرجِع dependency لا-عمل، فيبقى
    المسار «يحمل dependency» وهو بلا حراسة. الفحص هنا على **وحدة** الدالّة لا على
    وجودها — وهو ما يميّز الحارس عن شبيهه.
    """
    module = _app_for("field")
    for method, path in GUARDED_ROUTES:
        for route in module.app.routes:
            if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
                mods = [getattr(d.dependency, "__module__", "") for d in route.dependencies]
                assert any(m == "shared.oauth_middleware" for m in mods), (
                    f"{method} {path}: الحارس ليس من shared.oauth_middleware بل {mods} — "
                    "كعب اختباريّ أبطل الحراسة"
                )
