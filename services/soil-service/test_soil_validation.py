#!/usr/bin/env python3
"""
اختبارات وحدة لخدمة التربة — تحقّق نموذج SoilReading (offline، pytest).
تغطّي قيود الحقول (pH 0-14، EC 0-50، الرطوبة 0-100، إلخ).
ترفع التغطية من 0% (فجوة المراجعة).

التشغيل:
  pytest services/soil-service/test_soil_validation.py -v

ملاحظة: يحتاج pydantic (متوفّر في بيئتك). يستورد SoilReading من main.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from main import SoilReading  # noqa: E402

try:
    from pydantic import ValidationError
except ImportError:  # حماية للبيئات بلا pydantic
    ValidationError = Exception


# ── ١. قراءات صحيحة ──
def test_valid_reading_accepted():
    r = SoilReading(
        field_id="F1",
        sensor_id="S1",
        temperature=25.0,
        humidity=40.0,
        moisture_pct=30.0,
        ph_level=7.5,
        ec_level=3.2,
        tenant_id="T1",
    )
    assert r.field_id == "F1"
    assert r.ph_level == 7.5


def test_optional_fields_default_none():
    """الحقول الاختياريّة تقبل الغياب."""
    r = SoilReading(field_id="F1", sensor_id="S1")
    assert r.temperature is None
    assert r.ph_level is None


# ── ٢. قيود pH (0-14) ──
def test_ph_above_14_rejected():
    with pytest.raises(ValidationError):
        SoilReading(field_id="F1", sensor_id="S1", ph_level=15.0)


def test_ph_below_0_rejected():
    with pytest.raises(ValidationError):
        SoilReading(field_id="F1", sensor_id="S1", ph_level=-1.0)


def test_ph_boundary_values_ok():
    """الحدود 0 و14 مقبولة (ge/le شامل)."""
    assert SoilReading(field_id="F1", sensor_id="S1", ph_level=0.0).ph_level == 0.0
    assert SoilReading(field_id="F1", sensor_id="S1", ph_level=14.0).ph_level == 14.0


# ── ٣. قيود EC (0-50) — مهمّ للملوحة في الجوف ──
def test_ec_above_50_rejected():
    with pytest.raises(ValidationError):
        SoilReading(field_id="F1", sensor_id="S1", ec_level=51.0)


def test_ec_negative_rejected():
    with pytest.raises(ValidationError):
        SoilReading(field_id="F1", sensor_id="S1", ec_level=-0.5)


def test_ec_high_salinity_valid():
    """EC عالٍ (تربة الجوف المالحة) ضمن النطاق المقبول."""
    r = SoilReading(field_id="F1", sensor_id="S1", ec_level=7.0)
    assert r.ec_level == 7.0  # ECe~7 شائع في السنيدار


# ── ٤. قيود الرطوبة والحرارة ──
def test_humidity_above_100_rejected():
    with pytest.raises(ValidationError):
        SoilReading(field_id="F1", sensor_id="S1", humidity=101.0)


def test_moisture_above_100_rejected():
    with pytest.raises(ValidationError):
        SoilReading(field_id="F1", sensor_id="S1", moisture_pct=120.0)


def test_temperature_extreme_rejected():
    with pytest.raises(ValidationError):
        SoilReading(field_id="F1", sensor_id="S1", temperature=100.0)


def test_temperature_valid_range():
    r = SoilReading(field_id="F1", sensor_id="S1", temperature=45.0)
    assert r.temperature == 45.0  # حرارة صيف الجوف معقولة


# ── ٥. قيود المعرّفات ──
def test_empty_field_id_rejected():
    with pytest.raises(ValidationError):
        SoilReading(field_id="", sensor_id="S1")


def test_field_id_too_long_rejected():
    with pytest.raises(ValidationError):
        SoilReading(field_id="x" * 65, sensor_id="S1")


if __name__ == "__main__":
    # تشغيل offline بلا pytest (إن لزم)
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  \u2713 {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            print(f"  \u2717 {fn.__name__}: {type(e).__name__}")
    print(f"\n{passed}/{len(fns)} \u0646\u062c\u0627\u062d")
    sys.exit(0 if passed == len(fns) else 1)
