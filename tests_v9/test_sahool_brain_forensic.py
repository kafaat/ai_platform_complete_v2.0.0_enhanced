"""Forensic closed-loop tests for Sahool's field brain.

These tests intentionally stay pure/offline: no DB, no network, no ERP, no MQTT.
They verify the legal decision path contracts:
observations -> fusion/arbitration -> canonical water stress -> execution gating ->
recommendation -> context/provenance/RBAC delivery.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))

from api.canonical_water_stress import canonical_water_stress  # noqa: E402
from api.field_operational_state import resolve_field_state  # noqa: E402
from core.agronomic_state_engine import SignalInput, compose_field_state  # noqa: E402
from core.canonical_schemas import UserRole, UserSchema  # noqa: E402
from core.recommendation_bridge import full_delivery_pipeline  # noqa: E402
from core.recommendation_engine import RecommendationStatus, generate_recommendation  # noqa: E402

pytestmark = pytest.mark.unit


def test_brain_arbitration_salinity_overrides_green_ndvi() -> None:
    """Critical salinity must govern even when NDVI looks healthy."""
    state = compose_field_state(
        "field-brain-1",
        [
            SignalInput(source="ndvi", value=0.82, confidence="high"),
            SignalInput(source="soil_ec", value=10.2, confidence="high"),
        ],
        tenant_id="tenant-a",
    )

    truths = state.operational_truths
    assert truths["crop_vigor"] > 0.5
    assert truths["salinity_class"] == "critical"
    assert truths["effective_status"] == "salinity_limited"
    assert truths["effective_status_rule"] == "SAL-SOIL-03"
    assert any(
        isinstance(c, dict) and c.get("type") == "positive_signal_overridden_by_salinity_critical"
        for c in state.contradictions
    )
    assert any(p.get("source") == "soil_ec" for p in state.provenance)


def test_water_stress_escalation_requires_physics_and_spectral_observation() -> None:
    """No D2b eligibility without BOTH: critical depletion and NDMI+MSI spectral confirmation."""
    physics_only = canonical_water_stress(
        {
            "depletion_mm": 86.0,
            "taw_mm": 100.0,
            "raw_fraction": 0.5,
            "depletion_confidence": 0.93,
        }
    )
    assert physics_only is not None
    assert physics_only["water_stress_class"] == "critical"
    assert physics_only["spectral_confirmation_available"] is False
    assert physics_only["spectral_stress_detected"] is None
    assert physics_only["escalation_eligible"] is False

    # التاريخان **شرطٌ في التأكيد الطيفيّ**، لا زينة: سياسة التوافق الزمنيّ
    # (`canonical_water_stress.py:133-138`، قرار مالك) لا تدمج NDMI وMSI إلّا من نافذة
    # اكتساب متوافقة — وغيابُ أحد التاريخين يُقرأ **فشلاً مغلقاً** لا «متوفّر». فبقاء
    # هذه الحالة بلا تاريخين كان يجعلها تطلب تصعيداً على دمجٍ زمنيّ غير متحقَّق.
    # والسياسة هبطت **بعد** هذا الاختبار، ولم يُحمِرّ لأنّ الملفّ بلا علامة فلم يُنفَّذ.
    full_gate = canonical_water_stress(
        {
            "depletion_mm": 86.0,
            "taw_mm": 100.0,
            "raw_fraction": 0.5,
            "depletion_confidence": 0.93,
            "ndmi": -0.08,
            "msi": 2.15,
            "ndmi_date": "2026-08-10",
            "msi_date": "2026-08-10",
        }
    )
    assert full_gate is not None
    assert full_gate["water_stress_class"] == "critical"
    assert full_gate["spectral_confirmation_available"] is True
    assert full_gate["spectral_stress_detected"] is True
    assert full_gate["escalation_eligible"] is True
    assert full_gate["calibrated"] is False


def test_operational_state_blocks_contradictory_irrigation_decision() -> None:
    """A major irrigation increase during heavy rain must not remain auto-executable."""
    state = resolve_field_state(
        "field-brain-2",
        confidence_level="high",
        irrigation_delta_pct=30.0,
        rain_forecast_mm=25.0,
        soil_moisture_ratio=0.55,
        et0_mm=5.0,
        ndvi_age_days=1.0,
        soil_age_days=1.0,
        weather_age_hours=2.0,
    ).to_dict()

    assert state["validity"] == "conflicted"
    assert state["execution_mode"] == "blocked"
    assert any(c["rule_id"] == "irrig_vs_rain" for c in state["conflicts"])


def test_recommendation_engine_preserves_blocked_vs_limited_contracts() -> None:
    """Hard missing governors block, but explicit limited/pending_lab modes stay honest."""
    validation = {
        "quality_grade": "BLOCKED",
        "blocking_observables": ["S3", "I3"],
        "missing_A": ["S3", "I3"],
    }

    blocked = generate_recommendation(validation)
    assert blocked.status is RecommendationStatus.BLOCKED
    assert blocked.confidence == "blocked"
    assert blocked.backend.governing_failures == ["S3", "I3"]

    limited = generate_recommendation(validation, field_state="limited")
    assert limited.status is RecommendationStatus.LIMITED
    assert limited.confidence == "limited"
    assert "المبيدات محجوبة" in " ".join(limited.farmer_view.alerts_ar)


def test_recommendation_bridge_adds_provenance_context_and_fail_closed_auth() -> None:
    """Brain delivery must include context/provenance and enforce tenant/farm RBAC."""
    user = UserSchema(
        user_id="u-manager",
        tenant_id="tenant-a",
        role=UserRole.MANAGER,
        name_ar="مدير",
        farm_ids_access=["farm-a"],
    )
    base = {"rec_id": "rec-1", "base": {"headline_ar": "اروِ 20 مم"}}
    history = [
        SimpleNamespace(
            rec_id="hist-1",
            tenant_id="tenant-a",
            zone_id="field-old",
            crop="wheat",
            issued_date="2099-01-01",
            district_id="al-jawf",
            provenance={"input_snapshot": {"ndvi": 0.51, "ndmi": -0.05}},
            actual_yield_t_ha=4.2,
            error_pct=8.0,
        )
    ]

    delivered = full_delivery_pipeline(
        user=user,
        tenant_id="tenant-a",
        field_id="field-a",
        farm_id="farm-a",
        crop="wheat",
        base_recommendation=base,
        recommendation_history=history,
        current_indicators={"ndvi": 0.49, "ndmi": -0.04},
        growth_stage="mid",
        issue_type="water_stress",
        engines_used=["canonical_field_state", "water_stress_d2"],
        district_id="al-jawf",
    )
    assert delivered.delivered is True
    assert delivered.auth_decision["allowed"] is True
    assert delivered.provenance["engines_used"] == ["canonical_field_state", "water_stress_d2"]
    assert "model_versions" in delivered.provenance
    assert delivered.cross_reference.get("count", 0) >= 1

    denied = full_delivery_pipeline(
        user=user,
        tenant_id="tenant-b",
        field_id="field-b",
        farm_id="farm-b",
        crop="wheat",
        base_recommendation=base,
        recommendation_history=history,
        current_indicators={"ndvi": 0.49},
    )
    assert denied.delivered is False
    assert denied.auth_decision["allowed"] is False
    assert "عزل tenant" in denied.reason_ar
