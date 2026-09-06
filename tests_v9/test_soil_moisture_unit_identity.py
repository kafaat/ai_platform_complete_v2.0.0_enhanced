"""وحدةُ الرطوبة تُعلَن لا تُخمَّن، والحسّاسُ يُقارَن بالدفتر ولا يحكمه — `SOIL-MOISTURE-UNIT-IDENTITY-01`.

**العطلُ المقيس على `ad4ac5cc`:** ثلاثةُ أسماءٍ لكمّيّةٍ واحدة بثلاث دلالات:
`soil_telemetry.py:5` يقول «٪ من السعة المتاحة» · الكاتبُ القانونيّ يخزّن `"%"` عارية
(`soil-service/evidence_adapters.py:23`) · `compute_rwc` يقرأ VWC · ودفترُ `v98` يحمل
`soil_moisture_pct` بلا وحدةٍ يفسّرها `seed_initial_depletion` نسبةً من TAW. والحسّاساتُ
السعويّة تُخرِج VWC. فحزمةٌ واردة حسبت `TAW×(1−pct/100)` على قراءة VWC: 25٪ ⇒ نضوبٌ
75 مم على TAW=100 — ثمّ حجبت التوأمَ بـ409 «تعارض» على مقارنةٍ بلا معنى.

**والحقيقتان لم تكونا تلتقيان:** `water_twin.py` لا يقرأ الحسّاس البتّة؛ الحسّاس يمرّ
إلى `weather_advice.irrigation_advice` وحدَه.

**العقد:** الوحدةُ تُصنَّف ممّا أعلنه المصدر (`vwc_pct` · `available_pct` · `undeclared`)؛
التحويلُ إلى نضوبٍ بالوحدة لا بالافتراض (VWC عبر `(θFC − θ)·Zr·1000`)؛ الوصلةُ غيرُ
سلطويّة: الدفترُ بذرةٌ إن وُجد، الحسّاسُ الطازج يهيّئ عند غيابه بقيدٍ مُعلَن، والخلافُ
قيدٌ بالقيمتين لا 409؛ والطزاجةُ تُقرأ من إعلانٍ في سجلّ الأجهزة لا من رقمٍ في المستهلك.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_PLATFORM = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api import soil_telemetry as st  # noqa: E402
from api import water_twin_seed as seed  # noqa: E402
from api.device_registry import get_device_type  # noqa: E402
from api.weather_advice import irrigation_advice  # noqa: E402

_T = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)


def _row(value, unit, when=_T):
    return {"value": value, "recorded_at": when, "device_id": "dev_1", "unit": unit}


# ─── (١) الوحدةُ تُصنَّف ممّا أُعلِن ─────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ("vwc_pct", "vwc_pct"),
        ("VWC", "vwc_pct"),
        ("m3/m3", "vwc_pct"),
        ("available_pct", "available_pct"),
        ("paw_pct", "available_pct"),
        ("%", "undeclared"),
        ("pct", "undeclared"),
        (None, "undeclared"),
        ("banana", "undeclared"),
    ],
)
def test_the_unit_kind_comes_from_the_declaration_and_bare_percent_declares_nothing(raw, kind):
    assert st.classify_soil_moisture_unit(raw) == kind


def test_a_bare_percent_reading_is_kept_but_marked_undeclared():
    """الشكلُ الذي شُحِن: الكاتبُ القانونيّ يخزّن `%` — القراءةُ تبقى والحقيقةُ تُعلَن."""
    reading = st.pick_latest_soil_moisture([_row(42.0, "%")])
    assert reading is not None
    assert reading.value_pct == 42.0
    assert reading.unit_kind == "undeclared"
    assert reading.unit_declared is False
    assert reading.as_dict()["unit_kind"] == "undeclared"


def test_a_fractional_m3_per_m3_reading_is_scaled_to_percent():
    reading = st.pick_latest_soil_moisture([_row(0.23, "m3/m3")])
    assert reading is not None
    assert reading.value_pct == pytest.approx(23.0)
    assert reading.unit_kind == "vwc_pct"


# ─── (٢) النضوبُ بالوحدة لا بالافتراض ─────────────────────────────────────


def test_a_vwc_reading_is_never_read_as_a_share_of_taw():
    """25٪ VWC على TAW=100 كان يصير نضوباً 75 مم — الآن `(θFC − θ)·Zr·1000`."""
    dep, limit = seed.sensor_depletion_mm(
        value_pct=25.0, unit_kind="vwc_pct", taw_mm=100.0, root_depth_m=0.6, theta_fc=0.32
    )
    assert limit is None
    assert dep == pytest.approx((0.32 - 0.25) * 0.6 * 1000.0)  # 42 مم
    assert dep != pytest.approx(75.0)


def test_an_available_pct_reading_uses_the_taw_share():
    dep, limit = seed.sensor_depletion_mm(
        value_pct=25.0, unit_kind="available_pct", taw_mm=100.0, root_depth_m=None, theta_fc=None
    )
    assert (dep, limit) == (75.0, None)


def test_vwc_without_root_depth_or_theta_is_not_guessed():
    dep, limit = seed.sensor_depletion_mm(
        value_pct=25.0, unit_kind="vwc_pct", taw_mm=100.0, root_depth_m=None, theta_fc=0.32
    )
    assert dep is None and limit == seed.LIMIT_CONVERSION_INPUTS_MISSING


def test_an_undeclared_unit_converts_to_nothing():
    dep, limit = seed.sensor_depletion_mm(
        value_pct=25.0, unit_kind="undeclared", taw_mm=100.0, root_depth_m=0.6, theta_fc=0.32
    )
    assert dep is None and limit == seed.LIMIT_UNIT_UNDECLARED


def test_vwc_depletion_is_clamped_to_the_physical_range():
    dep, _ = seed.sensor_depletion_mm(
        value_pct=40.0, unit_kind="vwc_pct", taw_mm=100.0, root_depth_m=0.6, theta_fc=0.32
    )
    assert dep == 0.0  # أرطب من السعة الحقليّة ⇒ لا نضوب، لا سالب


# ─── (٣) الوصلةُ غيرُ سلطويّة ─────────────────────────────────────────────

_SENSOR = {"soil_moisture_pct": 25.0, "unit": "vwc_pct", "unit_kind": "vwc_pct"}


def _join(**overrides):
    base = dict(
        ledger_depletion_mm=40.0,
        ledger_source="ledger.depletion_mm",
        sensor=_SENSOR,
        sensor_depletion=42.0,
        sensor_limitation=None,
        sensor_age_s=600.0,
        max_reading_age_s=4 * 3600,
        taw_mm=100.0,
    )
    base.update(overrides)
    return seed.join_sensor_with_ledger_seed(**base)


def test_the_ledger_stays_the_seed_when_the_sensor_agrees():
    out = _join()
    assert out["source"] == "ledger.depletion_mm" and out["depletion_mm"] == 40.0
    assert out["delta_mm"] == 2.0
    assert out["limitations"] == []


def test_a_large_disagreement_is_declared_with_both_values_and_never_blocks():
    """الحزمةُ المرفوضة كانت ترفع 409 هنا؛ الوصلةُ تُعلن وتُبقي الدفترَ بذرةً."""
    out = _join(sensor_depletion=80.0)
    assert out["source"] == "ledger.depletion_mm" and out["depletion_mm"] == 40.0
    assert out["delta_mm"] == 40.0
    assert out["conflict_threshold_mm"] == 15.0  # max(10, 0.15·100)
    assert seed.LIMIT_SENSOR_DISAGREES in out["limitations"]
    assert out["sensor"]["depletion_mm"] == 80.0 and out["ledger_depletion_mm"] == 40.0


def test_a_fresh_convertible_sensor_seeds_only_when_the_ledger_is_absent():
    out = _join(ledger_depletion_mm=None, ledger_source="unavailable")
    assert out["depletion_mm"] == 42.0
    assert out["source"] == "sensor.vwc_pct"
    assert out["limitations"] == [seed.LIMIT_SEED_FROM_SENSOR]


def test_a_stale_sensor_is_neither_compared_nor_used_to_seed():
    """الطزاجةُ من الإعلان (٤ ساعات)، لا من رقمٍ في المستهلك."""
    stale = _join(sensor_age_s=5 * 3600)
    assert stale["delta_mm"] is None and seed.LIMIT_SENSOR_STALE in stale["limitations"]
    assert stale["sensor"]["stale"] is True
    no_ledger = _join(ledger_depletion_mm=None, ledger_source="unavailable", sensor_age_s=5 * 3600)
    assert no_ledger["depletion_mm"] is None and no_ledger["source"] == "unavailable"


def test_an_undeclared_sensor_cannot_seed_and_says_why():
    out = _join(
        ledger_depletion_mm=None,
        ledger_source="unavailable",
        sensor={**_SENSOR, "unit": "%", "unit_kind": "undeclared"},
        sensor_depletion=None,
        sensor_limitation=seed.LIMIT_UNIT_UNDECLARED,
    )
    assert out["depletion_mm"] is None
    assert out["limitations"] == [seed.LIMIT_UNIT_UNDECLARED]


def test_no_sensor_is_an_honest_absence():
    out = _join(sensor=None, sensor_depletion=None, sensor_age_s=None)
    assert out["source"] == "ledger.depletion_mm"
    assert out["sensor"] is None and out["limitations"] == [seed.LIMIT_NO_SENSOR]


# ─── (٤) الطزاجةُ مُعلَنة في السجلّ ───────────────────────────────────────


def test_the_soil_sensor_declares_its_cadence_and_freshness_bound():
    device = get_device_type("soil_moisture_sensor")
    assert device is not None
    assert device["expected_report_interval_s"] == 3600
    assert device["max_reading_age_s"] == 4 * device["expected_report_interval_s"]
    assert "available_pct" in device["description_ar"] and "vwc_pct" in device["description_ar"]


# ─── (٥) مسارُ الإلحاح يقرأ الوحدة ────────────────────────────────────────


def _advice(unit_kind: str, pct: float = 20.0) -> dict:
    return irrigation_advice(
        et0_mm=6.0,
        crop="wheat",
        stage="mid",
        rain_recent_mm=0.0,
        forecast_rain_mm=0.0,
        soil_moisture_pct=pct,
        soil_moisture_unit_kind=unit_kind,
    )


def test_a_vwc_reading_does_not_drive_urgency_against_available_water_thresholds():
    vwc = _advice("vwc_pct")
    available = _advice("available_pct")
    assert available["urgency"] == "high"  # 20٪ ماءٍ متاح < 30٪ ⇒ حرج
    assert vwc["urgency"] != "high"
    assert "VWC" in vwc["rationale_ar"]


def test_an_undeclared_unit_keeps_the_inherited_reading_but_names_the_assumption():
    out = _advice("undeclared")
    assert out["urgency"] == _advice("available_pct")["urgency"]
    assert "غير مُعلَنة" in out["rationale_ar"]


# ─── (٦) قاعدةُ التنبيه تقرأ الوحدة ────────────────────────────────────────

from api.alert_rules import FieldAlertContext, evaluate_field_alerts  # noqa: E402


def _low_moisture_alert(unit_kind: str, pct: float | None = 20.0, need: float | None = None):
    ctx = FieldAlertContext(
        field_id="f1",
        soil_moisture_pct=pct,
        soil_moisture_unit_kind=unit_kind,
        irrigation_need_mm=need,
    )
    return next((a for a in evaluate_field_alerts(ctx) if a.alert_type == "low_moisture"), None)


def test_a_vwc_reading_does_not_fire_the_available_water_alert():
    """20٪ VWC ليست 20٪ ماءٍ متاح — القاعدةُ تسقط إلى مسار الاحتياج وتقول لماذا."""
    assert _low_moisture_alert("vwc_pct") is None
    with_need = _low_moisture_alert("vwc_pct", need=50.0)
    assert with_need is not None and "حجميّة" in with_need.message_ar


def test_an_available_reading_still_fires_and_an_undeclared_one_names_its_assumption():
    available = _low_moisture_alert("available_pct")
    assert available is not None and "غير مُعلَنة" not in available.message_ar
    undeclared = _low_moisture_alert("undeclared")
    assert undeclared is not None and "غير مُعلَنة" in undeclared.message_ar


# ─── (٧) جانبُ الكاتب: الوحدةُ المُعلَنة تصل السجلَّ القانونيّ ──────────────

_SOIL_SERVICE = Path(__file__).resolve().parents[1] / "services" / "soil-service"


def _adapter():
    import importlib.util

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    spec = importlib.util.spec_from_file_location(
        "smui_evidence_adapters", _SOIL_SERVICE / "evidence_adapters.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_writer_stores_the_declared_unit_and_keeps_bare_percent_when_nothing_is_declared():
    adapter = _adapter()
    from shared.contracts.soil import SoilObservationSource

    common = dict(
        tenant_id="t1",
        field_id="f1",
        source_type=SoilObservationSource.SENSOR,
        source_id="dev_1",
        observed_at=_T,
    )
    declared = adapter.observations_from_properties(
        properties={"soil_moisture": 23.0}, units={"soil_moisture": "vwc_pct"}, **common
    )
    default = adapter.observations_from_properties(properties={"soil_moisture": 23.0}, **common)
    assert declared[0].unit == "vwc_pct"
    assert default[0].unit == "%"  # غيرُ مُعلَن — ولا يُخمَّن
    assert st.classify_soil_moisture_unit(declared[0].unit) == "vwc_pct"
    assert st.classify_soil_moisture_unit(default[0].unit) == "undeclared"
