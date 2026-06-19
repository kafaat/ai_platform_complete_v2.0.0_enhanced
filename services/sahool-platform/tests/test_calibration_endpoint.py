"""اختبار نقطتَي المعايرة (routers/calibration) — استدعاء مباشر.

يثبت: (أ) قائمة الملفّات (عامّ + 5 مناطق) مع validated_count=0 الآن؛ (ب) ملفّ منطقة
واحدة (عربيّة مقبولة)؛ (ج) المجهولة ⇒ عامّ. بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.calibration import get_region_calibration, list_calibration
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-cal",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="معايرة",
)


def test_list_calibration():
    out = list_calibration(user=_USER)
    assert "generic" in out
    assert len(out["regions"]) == 5
    assert out["validated_count"] == 0  # لا منطقة مُعايَرة بعد
    assert out["generic"]["validated"] is False


def test_get_region_arabic():
    out = get_region_calibration(region="الجوف", user=_USER)
    assert out["region"] == "jawf"
    assert out["validated"] is False


def test_unknown_region_generic():
    out = get_region_calibration(region="nowhere", user=_USER)
    assert out["region"] == "_generic"
