"""عقد CanonicalWeatherState (WX-10.1) — State Product موحَّد + مُجمِّع + مستهلك واحد.

يثبت: (أ) اكتمال الغلاف (schema/owner/state_id/version/source_snapshot/availability/quality/
confidence/provenance/evidence/limitations)؛ (ب) fail-closed بلا اختلاق (مدخلات ناقصة ⇒
availability=false + قيد، لا قيمة)؛ (ج) حتميّة state_id؛ (د) المستهلك (weather_state_report)
يقرأ الحالة فقط لا المحرّك.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canonical_weather_state import (  # noqa: E402
    OWNER,
    SCHEMA_VERSION,
    STATE_SLOTS,
    STATE_VERSION,
    build_canonical_weather_state,
    et0_view,
    weather_state_report,
)
from et0 import et0_agro_product  # noqa: E402

pytestmark = pytest.mark.unit

# متّجه طقس كامل (اليمن ~15.5°N) — يجعل et0/vpd/gdd/astronomy/dtr كلّها متوفّرة.
_FULL = dict(
    t_max_c=34.0,
    t_min_c=18.0,
    rh_mean_pct=45.0,
    wind_2m_ms=2.0,
    solar_rad_mj_m2=22.0,
    lat_deg=15.5,
    elevation_m=2000.0,
    day_of_year=100,
    gdd_daily_t_min=[16.0, 18.0],
    gdd_daily_t_max=[30.0, 32.0],
    gdd_base_c=10.0,
    valid_time="2026-07-11T09:00:00Z",
)

_ENVELOPE_KEYS = {
    "product_id",
    "state_id",
    "state_version",
    "schema_version",
    "owner",
    "source_snapshot_id",
    "generated_at",
    "quality",
    "confidence",
    "availability",
    "provenance",
    "evidence",
    "limitations",
    "products",
}


# ── الغلاف (State Product، لا DTO) ───────────────────────────────────────────
def test_envelope_is_complete_state_product():
    s = build_canonical_weather_state(**_FULL)
    assert _ENVELOPE_KEYS <= set(s), f"غلاف ناقص: {_ENVELOPE_KEYS - set(s)}"
    assert s["product_id"] == "canonical_weather_state"
    assert s["schema_version"] == SCHEMA_VERSION
    assert s["state_version"] == STATE_VERSION
    assert s["owner"] == OWNER == "weather-service"
    assert s["generated_at"] == _FULL["valid_time"]  # نَسَب لا ساعة مُختلقة


def test_availability_map_covers_every_slot():
    s = build_canonical_weather_state(**_FULL)
    assert set(s["availability"]) == set(STATE_SLOTS)
    assert all(isinstance(v, bool) for v in s["availability"].values())


def test_full_inputs_make_composed_products_available():
    s = build_canonical_weather_state(**_FULL)
    for slot in ("et0", "vpd", "gdd", "astronomy", "dtr"):
        assert s["availability"][slot] is True, slot
        assert slot in s["provenance"]
    # النَّسَب يحمل إصدار الصيغة + بصمة اللقطة لـET0.
    assert s["provenance"]["et0"]["formula_version"]
    assert s["provenance"]["et0"]["weather_snapshot_id"]
    assert s["quality"] in ("validated", "degraded")
    assert s["confidence"] in ("high", "medium")


def test_deferred_slots_are_declared_unavailable_not_fabricated():
    s = build_canonical_weather_state(**_FULL)
    for slot in ("current", "forecast", "historical", "operation_windows"):
        assert s["availability"][slot] is False
        assert any(slot in lim for lim in s["limitations"])


# ── fail-closed: لا اختلاق ───────────────────────────────────────────────────
def test_empty_inputs_fail_closed_no_fabrication():
    s = build_canonical_weather_state()
    assert all(v is False for v in s["availability"].values())
    assert s["quality"] == "insufficient"
    assert s["confidence"] == "low"
    assert s["provenance"] == {}
    assert s["limitations"]
    # لا قيمة مُختلقة في المنتجات.
    assert s["products"]["et0"]["et0_mm"] is None
    assert s["products"]["vpd"]["vpd_kpa"] is None
    assert s["products"]["dtr"]["dtr_c"] is None


def test_partial_inputs_reflect_honest_availability():
    # حرارة فقط ⇒ DTR متوفّر؛ ET0 (يحتاج جغرافيا) وVPD (يحتاج رطوبة) وGDD (يحتاج base_c) لا.
    s = build_canonical_weather_state(t_max_c=34.0, t_min_c=18.0)
    assert s["availability"]["dtr"] is True
    assert s["availability"]["et0"] is False
    assert s["availability"]["vpd"] is False
    assert s["availability"]["gdd"] is False
    assert s["products"]["dtr"]["dtr_c"] == 16.0


def test_inconsistent_temps_mark_dtr_invalid():
    s = build_canonical_weather_state(t_max_c=10.0, t_min_c=20.0)
    assert s["availability"]["dtr"] is False
    assert s["products"]["dtr"]["quality_status"] == "invalid"


# ── هويّة/نَسَب الحالة ───────────────────────────────────────────────────────
def test_state_id_is_deterministic_and_input_sensitive():
    a = build_canonical_weather_state(**_FULL)
    b = build_canonical_weather_state(**_FULL)
    assert a["state_id"] == b["state_id"]  # نفس المدخلات ⇒ نفس البصمة
    assert a["source_snapshot_id"] == b["source_snapshot_id"]
    changed = build_canonical_weather_state(**{**_FULL, "t_max_c": 35.0})
    assert changed["state_id"] != a["state_id"]
    assert changed["source_snapshot_id"] != a["source_snapshot_id"]


def test_evidence_echoes_only_supplied_inputs():
    s = build_canonical_weather_state(t_max_c=34.0, t_min_c=18.0, lat_deg=15.5, day_of_year=100)
    assert s["evidence"]["t_max_c"] == 34.0
    assert "rh_mean_pct" not in s["evidence"]  # لم يُمرَّر ⇒ لا يُختلق


# ── المستهلك الوحيد: يقرأ الحالة فقط ─────────────────────────────────────────
def test_report_reads_only_from_state():
    s = build_canonical_weather_state(**_FULL)
    r = weather_state_report(s)
    assert r["reads_from"] == "canonical_weather_state"
    assert r["state_id"] == s["state_id"]
    assert r["source_snapshot_id"] == s["source_snapshot_id"]
    assert r["overall_quality"] == s["quality"]
    # تقسيم المتوفّر/غير المتوفّر يطابق الحالة تماماً.
    assert set(r["available_products"]) == {k for k, v in s["availability"].items() if v}
    assert set(r["unavailable_products"]) == {k for k, v in s["availability"].items() if not v}
    # العناوين تشمل المتوفّر فقط.
    assert "et0_mm" in r["headline"] and "dtr_c" in r["headline"]


def test_report_headline_empty_when_nothing_available():
    r = weather_state_report(build_canonical_weather_state())
    assert r["headline"] == {}
    assert r["available_products"] == []
    assert r["overall_quality"] == "insufficient"


# ── WX-10.2: ET0 كـView مُشتقّ من الحالة (حفظ سلوك + إثبات الانعكاس) ──────────
_ET0_INPUTS = dict(
    t_max_c=34.0,
    t_min_c=18.0,
    solar_rad_mj_m2=22.0,
    rh_mean_pct=45.0,
    wind_2m_ms=2.0,
    t_mean_c=None,
    lat_deg=15.5,
    elevation_m=2000.0,
    day_of_year=100,
    valid_time="2026-07-11T09:00:00Z",
)


def test_et0_view_preserves_kernel_contract_fields():
    # الحقول الجوهريّة للـView == نداء النواة المباشر (حفظ سلوك تامّ).
    direct = et0_agro_product(**_ET0_INPUTS)
    state = build_canonical_weather_state(**_ET0_INPUTS)
    view = et0_view(state)
    for k in (
        "et0_mm",
        "method",
        "quality_status",
        "formula_version",
        "valid_time",
        "weather_snapshot_id",
        "limitations",
        "snapshot_source",
    ):
        assert view[k] == direct[k], k


def test_et0_view_adds_canonical_lineage():
    state = build_canonical_weather_state(**_ET0_INPUTS)
    view = et0_view(state)
    assert view["derived_from"] == "canonical_weather_state"
    assert view["canonical_state_id"] == state["state_id"]
    assert view["canonical_state_version"] == state["state_version"]
    assert view["source_snapshot_id"] == state["source_snapshot_id"]


def test_et0_view_honours_snapshot_id_override():
    # عقد ET0 يقبل weather_snapshot_id مُمرَّراً من المُستهلِك — يبقى محفوظاً عبر الحالة.
    state = build_canonical_weather_state(
        **_ET0_INPUTS, weather_snapshot_id_override="consumer-snap-123"
    )
    view = et0_view(state)
    assert view["weather_snapshot_id"] == "consumer-snap-123"


def test_et0_view_fail_closed_when_insufficient():
    # مدخلات ناقصة ⇒ الـView يعكس insufficient بلا اختلاق (نفس عقد النواة).
    view = et0_view(build_canonical_weather_state(t_max_c=30.0))  # لا جغرافيا/رطوبة
    assert view["et0_mm"] is None
    assert view["quality_status"] == "insufficient"
    assert view["derived_from"] == "canonical_weather_state"
