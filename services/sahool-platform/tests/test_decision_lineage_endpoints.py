"""اختبار نَسَب القرار عبر النقاط (Decision Lineage E2E) — استدعاء مباشر.

يثبت أنّ decision_id موحَّد يمرّ عبر السلسلة الحقيقيّة:
  decision (crop-twin/decision) → outcome (outcome/measure) → adaptation (calibration/adapt)
كلّ نقطة تُسَكّ معرّفاً إن غاب، وتُعيد المُمرَّر لإعادة استخدام السلسلة، وتُرفِق lineage
صحيحة (stage/parent/position). بلا شبكة/قاعدة.
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّهات
import pytest
from api.routers.calibration import AdaptRequest, EvidenceRecord, propose_region_adaptation
from api.routers.crop_twin import (
    ComposeForecastDay,
    ComposeManagement,
    ComposeSoil,
    CropDecisionRequest,
    compose_crop_decision,
)
from api.routers.outcome import (
    OutcomeActual,
    OutcomePlanned,
    OutcomeRequest,
    measure_decision_outcome,
)
from core.canonical_schemas import UserRole, UserSchema

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-lin",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="نَسَب",
)


def _decision_req(**kw):
    base = dict(
        crop="wheat",
        stage="mid",
        forecast=[
            ComposeForecastDay(t_min_c=12.0, t_max_c=32.0, et0_mm=8.0, kc=1.1) for _ in range(8)
        ],
        soil=ComposeSoil(texture="loam", root_depth_m=1.0),
        management=ComposeManagement(target_uptake_kg_ha=120.0, initial_depletion_mm=40.0),
    )
    base.update(kw)
    return CropDecisionRequest(**base)


def test_decision_mints_id_and_lineage():
    out = compose_crop_decision(req=_decision_req(), user=_USER)
    assert out["decision_id"].startswith("dec_")
    lin = out["lineage"]
    assert lin["decision_id"] == out["decision_id"]
    assert lin["stage"] == "decision"
    assert lin["parent_stage"] is None
    assert lin["position"] == 1


def test_decision_reuses_passed_id():
    out = compose_crop_decision(req=_decision_req(decision_id="dec_fixed123"), user=_USER)
    assert out["decision_id"] == "dec_fixed123"
    assert out["lineage"]["decision_id"] == "dec_fixed123"


def test_outcome_links_to_decision():
    out = measure_decision_outcome(
        req=OutcomeRequest(
            field_id="f1",
            decision_id="dec_fixed123",  # نفس معرّف القرار
            planned=OutcomePlanned(recommended_irrigation_mm=100.0, predicted_stress_days=3),
            actual=OutcomeActual(actual_irrigation_mm=100.0, observed_stress_days=1),
        ),
        user=_USER,
    )
    assert out["decision_id"] == "dec_fixed123"
    assert out["lineage"]["stage"] == "outcome"
    assert out["lineage"]["parent_stage"] == "decision"  # مرتبط بالقرار
    assert out["lineage"]["position"] == 2
    # القياس نفسه ما زال يعمل (نَسَب لا يكسر المنطق).
    assert "metrics" in out


def test_adaptation_links_lineage():
    req = AdaptRequest(
        evidence=EvidenceRecord(region="jawf", evidence_level="field_verified", sample_count=40),
        mean_stress_delta=2.0,
        decision_id="dec_fixed123",
    )
    out = propose_region_adaptation(region="jawf", req=req, user=_USER)
    assert out["decision_id"] == "dec_fixed123"
    assert out["lineage"]["stage"] == "adaptation"
    assert out["lineage"]["position"] == 4
    assert out["lineage"]["region"] == "jawf"


def test_full_chain_shares_one_id():
    # سلسلة كاملة بمعرّف واحد: قرار ⇒ قياس ⇒ تكيّف.
    dec = compose_crop_decision(req=_decision_req(), user=_USER)
    did = dec["decision_id"]
    oc = measure_decision_outcome(
        req=OutcomeRequest(
            field_id="f1",
            decision_id=did,
            planned=OutcomePlanned(recommended_irrigation_mm=100.0),
            actual=OutcomeActual(actual_irrigation_mm=95.0),
        ),
        user=_USER,
    )
    ad = propose_region_adaptation(
        region="jawf",
        req=AdaptRequest(
            evidence=EvidenceRecord(
                region="jawf", evidence_level="field_verified", sample_count=40
            ),
            mean_stress_delta=2.0,
            decision_id=did,
        ),
        user=_USER,
    )
    assert dec["decision_id"] == oc["decision_id"] == ad["decision_id"] == did
    assert [dec["lineage"]["stage"], oc["lineage"]["stage"], ad["lineage"]["stage"]] == [
        "decision",
        "outcome",
        "adaptation",
    ]
