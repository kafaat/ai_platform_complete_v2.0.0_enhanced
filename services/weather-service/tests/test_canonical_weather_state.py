"""عقد CanonicalWeatherState (WX-10.1) — State Product موحَّد + مُجمِّع + مستهلك واحد.

يثبت: (أ) اكتمال الغلاف (schema/owner/state_id/version/source_snapshot/availability/quality/
confidence/provenance/evidence/limitations)؛ (ب) fail-closed بلا اختلاق (مدخلات ناقصة ⇒
availability=false + قيد، لا قيمة)؛ (ج) حتميّة state_id؛ (د) المستهلك (weather_state_report)
يقرأ الحالة فقط لا المحرّك.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canonical_weather_state import (  # noqa: E402
    OWNER,
    SCHEMA_VERSION,
    STATE_SLOTS,
    STATE_VERSION,
    build_canonical_weather_state,
    current_view,
    et0_view,
    forecast_view,
    historical_view,
    vpd_view,
    weather_state_report,
)
from et0 import et0_agro_product  # noqa: E402
from vpd import compute_vpd  # noqa: E402

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
    for slot in ("heat_load", "chill_hours", "frost_risk", "operation_windows"):
        assert s["availability"][slot] is False
        assert any(slot in lim for lim in s["limitations"])


# ── WX-10.4: خانة «الآن» ─────────────────────────────────────────────────────
_OBS = {
    "location": {"lat": 24.7, "lon": 46.7},
    "temperature_c": 31.4,
    "humidity_pct": 18.0,
    "wind_speed_ms": 3.2,
    "wind_direction_deg": 310,
    "wind_gusts_ms": 6.1,
    "precipitation_mm": 0,
    "cloud_cover_pct": 12,
    "surface_pressure_hpa": 1004.2,
    "weather_code": 1,
    "is_day": True,
    "time": "2026-07-28T09:00",
    "source": "open-meteo",
    "timezone": "Asia/Riyadh",
}


def test_current_slot_absent_observation_is_unavailable_not_fabricated():
    """بلا مشاهدة تبقى الخانة غير متوفّرة بقيد صريح — لا قيمة مُختلقة (سلوك ما قبل WX-10.4)."""
    s = build_canonical_weather_state(**_FULL)
    assert s["availability"]["current"] is False
    assert any("current" in lim for lim in s["limitations"])
    assert s["products"]["current"]["quality_status"] == "insufficient"


def test_current_slot_composes_a_full_observation():
    s = build_canonical_weather_state(**_FULL, current_observation=_OBS)
    assert s["availability"]["current"] is True
    cur = s["products"]["current"]
    assert cur["quality_status"] == "validated"
    assert cur["temperature_c"] == 31.4
    assert cur["missing_fields"] == []
    assert s["provenance"]["current"]["quality_status"] == "validated"


def test_current_slot_missing_expected_fields_degrades_and_names_them():
    """الغياب يُسمّى ولا يُسقَط صامتاً، والجودة تنزل إلى degraded — لا ترقية مجّانيّة."""
    partial = {k: v for k, v in _OBS.items() if k not in ("humidity_pct", "cloud_cover_pct")}
    s = build_canonical_weather_state(**_FULL, current_observation=partial)
    cur = s["products"]["current"]
    assert s["availability"]["current"] is True
    assert cur["quality_status"] == "degraded"
    assert set(cur["missing_fields"]) == {"humidity_pct", "cloud_cover_pct"}
    assert any("missing expected fields" in lim for lim in cur["limitations"])


def test_current_slot_optional_field_absence_is_named_but_does_not_degrade():
    """حقل اختياريّ يُغفِله المزوّد يُذكَر ولا يُنزِل الجودة — لا ضجيج جودة كاذب."""
    no_optional = {k: v for k, v in _OBS.items() if k not in ("weather_code", "is_day")}
    cur = build_canonical_weather_state(current_observation=no_optional)["products"]["current"]
    assert cur["quality_status"] == "validated"
    assert set(cur["optional_missing_fields"]) == {"weather_code", "is_day"}
    assert any("omits optional fields" in lim for lim in cur["limitations"])


def test_current_slot_preserves_every_normalizer_field_not_in_the_quality_list():
    """الحارس الحقيقيّ ضدّ فقدان البيانات: قائمة الجودة تقيس ولا تُرشِّح المخرَج.

    حمولة المُطبِّع الحقيقيّة تحمل حقولاً خارج قائمة الجودة (`wind_speed_10m_kmh`,
    `soil_*`, `timestamp`, …) — إسقاطها كان سيكسر المستهلكين صامتاً.
    """
    rich = {
        **_OBS,
        "wind_speed_10m_kmh": 11.5,
        "wind_direction_10m_deg": 310,
        "wind_gusts_10m_kmh": 22.0,
        "soil_temperature_6cm_c": 20.0,
        "soil_moisture_1_to_3cm_m3m3": 0.18,
        "timestamp": "2026-07-28T09:00",
    }
    cur = build_canonical_weather_state(current_observation=rich)["products"]["current"]
    for key, value in rich.items():
        assert cur[key] == value, f"normalizer field {key} was dropped by the state slot"


def test_current_slot_envelope_wins_over_a_conflicting_observation_key():
    """مشاهدة تحمل مفتاح غلاف محجوزاً: الغلاف يسود ويُعلَن التعارض، لا يُبتلع صامتاً."""
    cur = build_canonical_weather_state(
        current_observation={**_OBS, "quality_status": "validated", "product": "spoofed"}
    )["products"]["current"]
    assert cur["product"] == "current"
    assert any("reserved envelope keys" in lim for lim in cur["limitations"])


def test_current_slot_without_core_temperature_is_insufficient():
    """درجة الحرارة هي الحدّ الأدنى؛ غيابها ⇒ insufficient مهما توفّر غيرها (fail-closed)."""
    no_temp = {k: v for k, v in _OBS.items() if k != "temperature_c"}
    s = build_canonical_weather_state(**_FULL, current_observation=no_temp)
    assert s["availability"]["current"] is False
    assert s["products"]["current"]["quality_status"] == "insufficient"


def test_current_slot_declares_the_upstream_zero_coercion_honestly():
    """صدق صريح: التطبيع الأعلى يُسقِط الغياب إلى صفر ⇒ القيد يُعلَن ولا يُدَّعى الرصد."""
    cur = build_canonical_weather_state(current_observation=_OBS)["products"]["current"]
    assert any("indistinguishable from an absent reading" in lim for lim in cur["limitations"])


def test_current_view_carries_state_lineage_and_is_a_superset():
    s = build_canonical_weather_state(**_FULL, current_observation=_OBS)
    view = current_view(s)
    assert view["derived_from"] == "canonical_weather_state"
    assert view["canonical_state_id"] == s["state_id"]
    assert view["canonical_state_version"] == s["state_version"]
    assert view["source_snapshot_id"] == s["source_snapshot_id"]
    assert view["weather_snapshot_id"] == s["source_snapshot_id"]
    # توافقيّ للخلف: كلّ حقول المشاهدة المُطبَّعة تبقى في مستواها الأعلى.
    for key in ("temperature_c", "humidity_pct", "wind_speed_ms", "weather_code", "is_day"):
        assert view[key] == _OBS[key]


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


def test_snapshot_override_is_coherent_across_state_and_view():
    # نَسَب متماسك: override يدخل products.et0.weather_snapshot_id **و**state.source_snapshot_id
    # **و**state_id — لا تناقض بين إعلان ET0 وغلاف الحالة.
    state = build_canonical_weather_state(
        **_ET0_INPUTS, weather_snapshot_id_override="consumer-snap-123"
    )
    view = et0_view(state)
    assert view["weather_snapshot_id"] == "consumer-snap-123"
    assert state["source_snapshot_id"] == "consumer-snap-123"  # الغلاف يعلن نفس اللقطة
    assert view["source_snapshot_id"] == "consumer-snap-123"  # الـView متّسق معهما


def test_different_snapshot_override_yields_different_state_id_same_values():
    # طلبان بنفس القيم العدديّة لكن بلقطتين مختلفتين ⇒ state_id مختلف (dedup/replay سليم).
    a = build_canonical_weather_state(**_ET0_INPUTS, weather_snapshot_id_override="snap-A")
    b = build_canonical_weather_state(**_ET0_INPUTS, weather_snapshot_id_override="snap-B")
    assert a["state_id"] != b["state_id"]
    assert a["source_snapshot_id"] == "snap-A" and b["source_snapshot_id"] == "snap-B"


def test_et0_view_fail_closed_when_insufficient():
    # مدخلات ناقصة ⇒ الـView يعكس insufficient بلا اختلاق (نفس عقد النواة).
    view = et0_view(build_canonical_weather_state(t_max_c=30.0))  # لا جغرافيا/رطوبة
    assert view["et0_mm"] is None
    assert view["quality_status"] == "insufficient"
    assert view["derived_from"] == "canonical_weather_state"


# ── WX-10.2 بوّابة الإغلاق: لا مسار حساب ET0 خارج المُجمِّع + لا رفع جودة ──────
def _top_level_func_body(src: str, name: str) -> str:
    """يستخرج جسم دالّة عُلويّة بالاسم (لا يفحص كامل الملفّ — دقّة أعلى، لا إيجابيّات كاذبة)."""
    lines = src.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        if line.startswith((f"async def {name}(", f"def {name}(")):
            capturing = True
            out.append(line)
            continue
        if capturing:
            # نهاية الدالّة عند أوّل تعريف عُلويّ تالٍ (عمود صفر).
            if (
                line
                and not line[0].isspace()
                and line.startswith(("def ", "async def ", "class ", "@"))
            ):
                break
            out.append(line)
    assert out, f"لم يُعثَر على الدالّة {name}"
    return "\n".join(out)


def test_agro_et0_body_has_no_direct_computation_path_outside_composer():
    # حارس ساكن مُنطاق على **جسم agro_et0 وحده** (لا كامل الملفّ): يشتقّ من الحالة فقط ولا
    # يستدعي النواة (compute_et0) ولا المنتَج الكنسيّ (et0_agro_product) مباشرةً.
    src = (Path(__file__).resolve().parent.parent / "weather_runtime.py").read_text(
        encoding="utf-8"
    )
    body = _top_level_func_body(src, "agro_et0")
    assert "et0_agro_product" not in body, "agro_et0 يجب ألّا يستدعي المنتَج الكنسيّ مباشرةً"
    assert "compute_et0" not in body, "agro_et0 يجب ألّا يستدعي النواة مباشرةً"
    assert "build_canonical_weather_state" in body and "et0_view" in body


def test_et0_view_does_not_recompute_reads_state_only():
    import inspect

    src = inspect.getsource(et0_view)
    # لا إعادة حساب: الـView لا يستدعي النواة/المنتَج/المُجمِّع — يقرأ الحالة فقط.
    assert "et0_agro_product" not in src, (
        "الـView يقرأ الحالة ولا يُعيد الحساب — نداء المنتَج يُنشئ مصدرَ حقيقةٍ ثانياً"
    )
    assert "compute_et0" not in src, "إعادة تنفيذ صيغة ET0 هنا تنحرف عن النواة بصمت"
    assert "build_canonical_weather_state" not in src, (
        "بناء الحالة من الـView يجعل القراءة كتابةً ويُخفي مَن ولّدها"
    )
    assert 'state.get("products"' in src


def test_et0_view_preserves_degraded_and_does_not_elevate_partial():
    # مدخلات جزئيّة (بلا solar/rh/wind) ⇒ hargreaves_fallback = degraded؛
    # الـView لا يرفعها إلى validated ولا يحوّل الحالة الجزئيّة إلى نجاح كامل.
    inp = dict(t_max_c=30.0, t_min_c=18.0, lat_deg=15.5, day_of_year=100)
    state = build_canonical_weather_state(**inp)
    view = et0_view(state)
    direct = et0_agro_product(**inp)
    assert view["method"] == "hargreaves_fallback"
    assert view["quality_status"] == "degraded" == direct["quality_status"]
    assert view["et0_mm"] is not None and view["et0_mm"] == direct["et0_mm"]
    assert state["availability"]["et0"] is True  # degraded مُتاح لكنّه ليس validated
    assert state["quality"] != "validated"  # الحالة الكلّيّة لم تُرفَع زوراً


# ── WX-10.3: VPD كـView مُشتقّ من الحالة (حفظ حرفيّ + إثبات الانعكاس) ──────────
_VPD_VALIDATED = dict(
    t_max_c=34.0, t_min_c=18.0, rh_mean_pct=45.0, valid_time="2026-07-11T09:00:00Z"
)
_VPD_DEGRADED = dict(t_max_c=20.0, dew_point_c=20.02)  # نقطة ندى فوق الحرارة بقليل ⇒ قصّ سالب
_VPD_INSUFFICIENT = dict(t_max_c=30.0)  # لا مصدر رطوبة


def test_vpd_view_preserves_full_contract_verbatim():
    # كامل عقد VPD == نداء النواة المباشر (حفظ حرفيّ، لا رفع/تبسيط).
    direct = compute_vpd(t_max_c=34.0, t_min_c=18.0, rh_mean_pct=45.0, dew_point_c=None)
    view = vpd_view(build_canonical_weather_state(**_VPD_VALIDATED))
    for k in (
        "vpd_kpa",
        "raw_vpd_kpa",
        "es_kpa",
        "ea_kpa",
        "method",
        "input_completeness",
        "input_consistency",
        "quality_status",
        "quality_flags",
        "limitations",
        "cross_check",
        "units",
        "formula_version",
    ):
        assert view[k] == direct[k], k


def test_vpd_view_preserves_consistency_crosscheck_flags_when_dual_source():
    # RH + نقطة ندى ⇒ cross_check + input_consistency محفوظان حرفيّاً (لا يُبسَّطان).
    inp = dict(t_max_c=34.0, t_min_c=18.0, rh_mean_pct=45.0, dew_point_c=10.0)
    direct = compute_vpd(**inp)
    view = vpd_view(build_canonical_weather_state(**inp))
    assert view["cross_check"] == direct["cross_check"]
    assert view["input_consistency"] == direct["input_consistency"]
    assert view["quality_flags"] == direct["quality_flags"]


def test_vpd_view_adds_canonical_lineage():
    state = build_canonical_weather_state(**_VPD_VALIDATED)
    view = vpd_view(state)
    assert view["derived_from"] == "canonical_weather_state"
    assert view["canonical_state_id"] == state["state_id"]
    assert view["canonical_state_version"] == state["state_version"]
    assert view["source_snapshot_id"] == state["source_snapshot_id"]
    # VPD لا يحمل weather_snapshot_id في نواته ⇒ يُضاف من لقطة الحالة (نَسَب موحَّد).
    assert view["weather_snapshot_id"] == state["source_snapshot_id"]


def test_vpd_view_quality_propagates_validated_degraded_insufficient():
    v = vpd_view(build_canonical_weather_state(**_VPD_VALIDATED))
    assert v["quality_status"] == "validated" and v["vpd_kpa"] is not None
    d = vpd_view(build_canonical_weather_state(**_VPD_DEGRADED))
    assert d["quality_status"] == "degraded"  # قصّ سالب — لا يُرفَع لvalidated
    assert "negative_vpd_clamped" in d["quality_flags"]
    i = vpd_view(build_canonical_weather_state(**_VPD_INSUFFICIENT))
    assert i["quality_status"] == "insufficient" and i["vpd_kpa"] is None


def test_vpd_view_matches_direct_kernel_for_each_quality_tier():
    for inp in (_VPD_VALIDATED, _VPD_DEGRADED, _VPD_INSUFFICIENT):
        clean = {k: v for k, v in inp.items() if k != "valid_time"}
        direct = compute_vpd(
            t_max_c=clean.get("t_max_c"),
            t_min_c=clean.get("t_min_c"),
            rh_mean_pct=clean.get("rh_mean_pct"),
            dew_point_c=clean.get("dew_point_c"),
        )
        view = vpd_view(build_canonical_weather_state(**inp))
        assert view["quality_status"] == direct["quality_status"]
        assert view["vpd_kpa"] == direct["vpd_kpa"]


def test_vpd_snapshot_override_is_coherent():
    # override = state.source_snapshot_id = vpd.weather_snapshot_id.
    state = build_canonical_weather_state(
        **_VPD_VALIDATED, weather_snapshot_id_override="snap-vpd-1"
    )
    view = vpd_view(state)
    assert state["source_snapshot_id"] == "snap-vpd-1"
    assert view["source_snapshot_id"] == "snap-vpd-1"
    assert view["weather_snapshot_id"] == "snap-vpd-1"


def test_vpd_view_deterministic_and_distinct_state_id_per_snapshot():
    a = build_canonical_weather_state(**_VPD_VALIDATED, weather_snapshot_id_override="snap-A")
    b = build_canonical_weather_state(**_VPD_VALIDATED, weather_snapshot_id_override="snap-B")
    # نفس الحالة الكنسيّة ⇒ مخرَج View متطابق (حتميّة).
    assert vpd_view(a) == vpd_view(
        build_canonical_weather_state(**_VPD_VALIDATED, weather_snapshot_id_override="snap-A")
    )
    # لقطتان مختلفتان بنفس القيم ⇒ state_id مختلف.
    assert a["state_id"] != b["state_id"]


def test_vpd_view_does_not_recompute_reads_state_only():
    import inspect

    src = inspect.getsource(vpd_view)
    assert "compute_vpd" not in src, "إعادة تنفيذ صيغة VPD هنا تنحرف عن النواة بصمت"
    assert "build_canonical_weather_state" not in src, (
        "بناء الحالة من الـView يجعل القراءة كتابةً ويُخفي مَن ولّدها"
    )
    assert 'state.get("products"' in src


def test_agro_vpd_body_has_no_direct_computation_path_outside_composer():
    src = (Path(__file__).resolve().parent.parent / "weather_runtime.py").read_text(
        encoding="utf-8"
    )
    body = _top_level_func_body(src, "agro_vpd")
    assert "compute_vpd" not in body, "agro_vpd يجب ألّا يستدعي نواة VPD مباشرةً"
    assert "build_canonical_weather_state" in body and "vpd_view" in body


# ── WX-10.5: خانتا التوقّع والأرشيف ──────────────────────────────────────────
def _day(**overrides):
    base = {
        "date": "2026-07-28",
        "temp_max_c": 41.2,
        "temp_min_c": 27.8,
        "precipitation_mm": 0.0,
        "et0_mm": 8.1,
        "sunshine_hours": 12.4,
        "wind_max_ms": 5.5,
        "wind_max_kmh": 19.8,
        "weather_code": 0,
        "sunrise": "2026-07-28T05:31",
        "sunset": "2026-07-28T18:52",
        "daylight_hours": 13.35,
        "solar_radiation_mj_m2": 28.4,
    }
    base.update(overrides)
    return base


def _series(days, **overrides):
    base = {
        "location": {"lat": 24.7, "lon": 46.7},
        "range": {"start": days[0]["date"], "end": days[-1]["date"]},
        "days": days,
        "source": "open-meteo",
        "model": "best_match",
        "timezone": "Asia/Riyadh",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("slot", ["forecast", "historical"])
def test_daily_slot_absent_series_is_unavailable_not_fabricated(slot):
    s = build_canonical_weather_state(**_FULL)
    assert s["availability"][slot] is False
    assert s["products"][slot]["quality_status"] == "insufficient"
    assert s["products"][slot]["day_count"] == 0


@pytest.mark.parametrize(
    "slot,kwarg", [("forecast", "forecast_series"), ("historical", "historical_series")]
)
def test_daily_slot_composes_a_full_series(slot, kwarg):
    s = build_canonical_weather_state(**{kwarg: _series([_day(), _day(date="2026-07-29")])})
    prod = s["products"][slot]
    assert s["availability"][slot] is True
    assert prod["quality_status"] == "validated"
    assert prod["day_count"] == 2
    assert prod["days_missing_fields"] == []
    # مجموعة فائقة: بنية السلسلة الأصليّة سليمة.
    assert len(prod["days"]) == 2
    assert prod["range"]["end"] == "2026-07-29"
    assert prod["model"] == "best_match"


def test_daily_slot_empty_days_is_insufficient_not_validated():
    """سلسلة بلا أيّام ليست «سليمة فارغة» — لا شيء رُصِد ⇒ fail-closed."""
    s = build_canonical_weather_state(forecast_series=_series([_day()]) | {"days": []})
    assert s["availability"]["forecast"] is False
    assert s["products"]["forecast"]["quality_status"] == "insufficient"


def test_daily_slot_missing_expected_field_in_any_day_degrades():
    """يوم واحد ناقص يكفي لإنزال الجودة — لا يُخفيه متوسّط الأيّام السليمة."""
    s = build_canonical_weather_state(
        forecast_series=_series([_day(), _day(date="2026-07-29", et0_mm=None)])
    )
    prod = s["products"]["forecast"]
    assert prod["quality_status"] == "degraded"
    assert "et0_mm" in prod["days_missing_fields"]


def test_historical_absence_of_forecast_only_fields_does_not_degrade():
    """الأرشيف لا يطلب sunshine/sunrise/…: غيابها يُذكَر ولا يُنزِل الجودة."""
    archive_day = {
        k: v
        for k, v in _day().items()
        if k
        not in ("sunshine_hours", "sunrise", "sunset", "daylight_hours", "solar_radiation_mj_m2")
    }
    s = build_canonical_weather_state(
        historical_series=_series([archive_day], source="open-meteo-archive", model="ERA5")
    )
    prod = s["products"]["historical"]
    assert prod["quality_status"] == "validated"
    assert prod["days_missing_fields"] == []
    assert "sunrise" in prod["optional_missing_fields"]


def test_daily_slots_declare_the_upstream_zero_coercion_honestly():
    s = build_canonical_weather_state(
        forecast_series=_series([_day()]), historical_series=_series([_day()])
    )
    for slot in ("forecast", "historical"):
        assert any(
            "indistinguishable from an absent reading" in lim
            for lim in s["products"][slot]["limitations"]
        )


@pytest.mark.parametrize(
    "slot,kwarg,view",
    [
        ("forecast", "forecast_series", forecast_view),
        ("historical", "historical_series", historical_view),
    ],
)
def test_daily_views_carry_state_lineage_and_stay_supersets(slot, kwarg, view):
    series = _series([_day()])
    s = build_canonical_weather_state(**{kwarg: series})
    v = view(s)
    assert v["derived_from"] == "canonical_weather_state"
    assert v["canonical_state_id"] == s["state_id"]
    assert v["canonical_state_version"] == s["state_version"]
    assert v["source_snapshot_id"] == s["source_snapshot_id"]
    assert v["weather_snapshot_id"] == s["source_snapshot_id"]
    for key in ("location", "range", "days", "source", "model", "timezone"):
        assert v[key] == series[key], f"normalizer field {key} was dropped by the {slot} slot"


def test_forecast_and_historical_are_independent_slots():
    """تمرير إحداهما لا يجعل الأخرى متوفّرة — لا تسرّب بين الخانتين."""
    s = build_canonical_weather_state(forecast_series=_series([_day()]))
    assert s["availability"]["forecast"] is True
    assert s["availability"]["historical"] is False
