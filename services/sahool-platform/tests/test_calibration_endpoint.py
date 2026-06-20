"""اختبار نقطتَي المعايرة (routers/calibration) — استدعاء مباشر.

يثبت: (أ) قائمة الملفّات (عامّ + 5 مناطق) مع validated_count=0 الآن؛ (ب) ملفّ منطقة
واحدة (عربيّة مقبولة)؛ (ج) المجهولة ⇒ عامّ. بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers.calibration import (
    AdaptRequest,
    EvidenceRecord,
    EvidenceRequest,
    FeedbackRequest,
    OutcomeRecord,
    ProposeValuesRequest,
    compute_learning_feedback,
    compute_region_evidence,
    get_region_calibration,
    list_calibration,
    propose_region_adaptation,
    propose_region_values,
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


def test_feedback_endpoint_suggests_no_auto_adjust():
    req = FeedbackRequest(
        evidence_records=[
            EvidenceRecord(region="jawf", evidence_level="none", sample_count=0),
            EvidenceRecord(
                region="ibb", evidence_level="field_verified", sample_count=40, success_rate=0.9
            ),
        ]
    )
    out = compute_learning_feedback(req=req, user=_USER)
    assert out["auto_adjust"] is False
    assert "jawf" in out["summary"]["regions_needing_data"]
    assert out["regions"][0]["region"] == "jawf"  # الأولويّة الأعلى أوّلاً


def test_adapt_gated_without_evidence():
    req = AdaptRequest(
        evidence=EvidenceRecord(region="jawf", evidence_level="field_preliminary", sample_count=5),
        mean_stress_delta=2.0,
    )
    out = propose_region_adaptation(region="jawf", req=req, user=_USER)
    assert out["status"] == "gated"
    assert out["applied"] is False


def test_adapt_eligible_under_evidence():
    req = AdaptRequest(
        evidence=EvidenceRecord(region="jawf", evidence_level="field_verified", sample_count=40),
        mean_stress_delta=2.0,  # إجهاد أسوأ ⇒ خفض p
    )
    out = propose_region_adaptation(region="jawf", req=req, user=_USER)
    assert out["status"] == "auto_apply_eligible"
    assert out["applied"] is False  # يقترح لا يطبّق
    assert out["proposals"][0]["proposed"] < out["proposals"][0]["current"]


def test_propose_values_accepts_good():
    req = ProposeValuesRequest(raw_fraction=0.5, source_ar="قياس ميدانيّ — مأرب")
    out = propose_region_values(region="marib", req=req, user=_USER)
    assert out["region"] == "marib"
    assert out["accepted"] == {"raw_fraction": 0.5}
    assert out["rejected"] == []
    assert out["validated"] is True
    assert out["ready_to_persist"] is True
    assert out["calibrated"] is False  # لا يكتب آليّاً


def test_propose_values_rejects_bad():
    req = ProposeValuesRequest(raw_fraction=0.9)  # خارج المدى
    out = propose_region_values(region="marib", req=req, user=_USER)
    assert out["accepted"] == {}
    assert out["rejected"][0]["field"] == "raw_fraction"
    assert out["validated"] is False
    assert out["ready_to_persist"] is False
