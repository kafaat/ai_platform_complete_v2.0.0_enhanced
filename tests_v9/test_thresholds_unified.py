"""اختبار توحيد العتبات (C6/H6): مصدر واحد core.thresholds + حفظ القيم في كلّ المواقع.

يثبت: (أ) القيم المعياريّة لليمن؛ (ب) أنّ كلّ موقع كان يُعرّف العتبة محليّاً صار يشير
للمصدر الموحّد بنفس القيمة (لا انجراف، لا تغيير سلوك). حارس ضدّ عودة الازدواج.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from core import thresholds as T  # noqa: E402


def test_canonical_values_preserved():
    # القيم محفوظة كما كانت قبل التوحيد (لا تغيير سلوك).
    assert T.HEAT_STRESS_DAILY_TMAX_C == 35.0
    assert T.HEAT_STRESS_CRITICAL_DAILY_TMAX_C == 40.0
    assert T.HEAT_STRESS_HOURLY_C == 38.0
    assert T.CLIMATE_HOT_DAY_TMAX_C == 38.0
    assert T.CLIMATE_SEVERE_HEAT_TMAX_C == 42.0
    assert T.FROST_RISK_C == 2.0
    assert T.FROST_CRITICAL_C == 0.0
    assert T.SALINITY_MODERATE_ECE == 4.0
    assert T.SALINITY_CRITICAL_ECE == 8.0
    assert T.HIGH_PH_THRESHOLD == 7.8


def test_alert_rules_reference_unified_source():
    from api import alert_rules as ar

    assert ar.HEAT_STRESS_TMAX_C == T.HEAT_STRESS_DAILY_TMAX_C
    assert ar.HEAT_STRESS_CRITICAL_TMAX_C == T.HEAT_STRESS_CRITICAL_DAILY_TMAX_C
    assert ar.FROST_RISK_TMIN_C == T.FROST_RISK_C
    assert ar.FROST_RISK_CRITICAL_TMIN_C == T.FROST_CRITICAL_C


def test_weather_overlay_and_analytics_reference_unified_source():
    from api import weather_analytics as wa
    from core import weather_overlay as wo

    # weather_overlay: عدّ ساعات الإجهاد (38) + صقيع (2).
    assert wo._HEAT_C == T.HEAT_STRESS_HOURLY_C
    assert wo._FROST_C == T.FROST_RISK_C
    # weather_analytics: إحصاء مناخيّ (38/42) + صقيع (2).
    assert wa._HEAT_STRESS_C == T.CLIMATE_HOT_DAY_TMAX_C
    assert wa._SEVERE_HEAT_C == T.CLIMATE_SEVERE_HEAT_TMAX_C
    assert wa._FROST_C == T.FROST_RISK_C


def test_salinity_ph_sites_reference_unified_source():
    from core import agronomic_state_engine as ase
    from core import soil_feedback_proxy as sfp

    assert ase.SALINITY_CRITICAL_ECE == T.SALINITY_CRITICAL_ECE
    assert ase.SALINITY_MODERATE_ECE == T.SALINITY_MODERATE_ECE
    assert sfp._SALINITY_REF_DS_M == T.SALINITY_CRITICAL_ECE
