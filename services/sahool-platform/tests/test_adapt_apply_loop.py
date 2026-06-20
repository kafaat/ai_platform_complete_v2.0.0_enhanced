"""اختبار إغلاق حلقة التعلّم: تطبيق التكيّف المحروس على متجر المعايرة (v80).

نقطة POST /api/v1/calibration/{region}/adapt-from-evidence/apply تربط طرفَي الحلقة
(نتيجة⇒دليل⇒تكيّف⇒معايرة مُدامة). الإدامة محروسة بثلاث بوّابات: تأكيد صريح + اقتراح
auto_apply_eligible + حدود أمان. مسار الكتابة تكامليّ (Postgres)؛ هنا نتحقّق من بوّابة
**التأكيد الصريح** (ترفض قبل أيّ مسّ بالقاعدة) + توصيل المسار — حتميّاً بلا قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّهات
import pytest
from api.routers.calibration import AdaptApplyRequest, apply_region_adaptation_from_evidence
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-apply",
    tenant_id="00000000-0000-0000-0000-000000000004",
    role=UserRole.OWNER,
    name_ar="تطبيق",
)


async def test_apply_requires_explicit_confirmation():
    """بلا confirm=true ⇒ 422 قبل أيّ مسّ بالقاعدة (مبدأ الصدق: لا تطبيق خفيّ)."""
    with pytest.raises(HTTPException) as ei:
        await apply_region_adaptation_from_evidence(
            region="jawf",
            req=AdaptApplyRequest(confirm=False, mean_stress_delta=2.0),
            user=_USER,
        )
    assert ei.value.status_code == 422
    assert "تأكيد" in ei.value.detail or "confirm" in str(ei.value.detail)


def test_apply_endpoint_wired():
    """نقطة تطبيق التكيّف مُضمَّنة بـPOST (تُغلق الحلقة على متجر المعايرة)."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/calibration/{region}/adapt-from-evidence/apply", "POST") in routes
