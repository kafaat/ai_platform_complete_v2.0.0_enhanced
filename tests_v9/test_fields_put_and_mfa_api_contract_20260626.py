import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
FIELDS = (ROOT / "services/sahool-platform/api/routers/fields.py").read_text(encoding="utf-8")
AUTH = (ROOT / "services/auth/main.py").read_text(encoding="utf-8")
RASTER_AUTH_TEST = (ROOT / "tests_v9/test_raster_endpoint_auth_coverage.py").read_text(
    encoding="utf-8"
)


def test_fields_put_endpoint_exists_for_update_contract():
    assert '@router.put("/api/v1/fields/{field_id}", response_model=FieldDetail)' in FIELDS
    assert '@router.patch("/api/v1/fields/{field_id}", response_model=FieldDetail)' in FIELDS


def test_sensitive_mfa_enabled_by_default():
    assert 'os.getenv("ENFORCE_SENSITIVE_MFA", "true").lower() == "true"' in AUTH


def _function_source(package: str, name: str) -> str:
    """مصدر دالّة بالاسم في **أيّ** وحدة من الحزمة — عبر AST لا بقصّ بين نصّين.

    الصيغة السابقة كانت تقصّ `raster-service/main.py` بين مرساتين؛ فكّك التفكيكُ
    الملفّ فانتقلت الدالّة إلى `raster_main_runtime.py` و`_public_cog_url` إلى وحدة
    أخرى، فسقط الاختبار بـ`ValueError: substring not found` — أي فشل في **إعداد**
    التأكيد لا في التأكيد. القاعدة المحروسة (فشل مُغلَق بلا مستأجر) لم تتغيّر.
    """
    for module in sorted((ROOT / package).glob("*.py")):
        source = module.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
                return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"دالّة غير موجودة في {package}: {name}")


def test_layer_tenant_fallback_fails_closed_without_tenant():
    """التفويض انتقل مرّتين: من `main.py` إلى `raster_main_runtime`، ثمّ صار المُنفِّذ
    `raster_security_context.require_layer_tenant_authorized` والغلاف يفوّض إليه.

    التأكيد يقع على **المُنفِّذ** لأنّ القاعدة هناك؛ ويُتحقَّق من بقاء التفويض قائماً كي
    لا يمرّ غلاف يدّعي حمايةً لا يستدعيها.
    """
    wrapper = _function_source("services/raster-service", "_require_layer_tenant_authorized")
    assert "require_layer_tenant_authorized(" in wrapper, "الغلاف لم يعد يفوّض للمُنفِّذ"

    body = _function_source("services/raster-service", "require_layer_tenant_authorized")
    assert "db_owner = await db_persist.layer_owner_tenant(layer_id)" in body
    assert "if not req_tenant:" in body
    assert "مستأجر الطلب مطلوب لقراءة الطبقة" in body


def test_storage_and_offline_are_no_longer_public_catalog_in_guard():
    public = RASTER_AUTH_TEST[
        RASTER_AUTH_TEST.index("PUBLIC_CATALOG: set[str]") : RASTER_AUTH_TEST.index(
            "# ─────────────────────────────────────────────────────────────────────────────\n# كاشف ast"
        )
    ]
    service = RASTER_AUTH_TEST[
        RASTER_AUTH_TEST.index("SERVICE_ONLY: set[str]") : RASTER_AUTH_TEST.index(
            "# ─────────────────────────────────────────────────────────────────────────────\n# القائمة العامّة"
        )
    ]
    assert '"/v1/storage/stats"' in service
    assert '"/v1/offline/packs"' in service
    assert '"/v1/offline/packs/{pack_name}"' in service
    assert '"/storage/stats"' not in public
    assert '"/v1/storage/stats"' not in public
