"""اختبار نقطتَي المعايرة (routers/calibration) — استدعاء مباشر.

يثبت: (أ) قائمة الملفّات (عامّ + 5 مناطق) مع validated_count=0 الآن؛ (ب) ملفّ منطقة
واحدة (عربيّة مقبولة)؛ (ج) المجهولة ⇒ عامّ. بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.calibration import (
    EvidenceRequest,
    OutcomeRecord,
    compute_region_evidence,
    get_region_calibration,
    list_calibration,
)
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


def test_evidence_endpoint_aggregates():
    req = EvidenceRequest(
        region="jawf",
        outcomes=[
            OutcomeRecord(n_evaluated=4, n_success=3, success_flags=["irrigation_followed"]),
            OutcomeRecord(n_evaluated=0, n_success=0),  # فارغة لا تُحتسب
        ],
    )
    out = compute_region_evidence(region="jawf", req=req, user=_USER)
    assert out["region"] == "jawf"
    assert out["sample_count"] == 1
    assert out["evidence_level"] == "field_preliminary"
    assert out["success_flag_counts"]["irrigation_followed"] == 1
