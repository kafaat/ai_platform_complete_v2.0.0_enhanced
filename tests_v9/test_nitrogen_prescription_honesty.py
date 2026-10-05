"""وصفة النيتروجين المتغيّرة: NDVI تشخيصيّ لا يحدّد الجرعة، والجدولُ غير المُتحقَّق مُعلَن.

``POST /api/v1/fields/{id}/prescriptions/nitrogen`` نقطةٌ حيّة. كان ``_zone_to_class``
يُحوّل ``ndvi_mean`` < 0.4 / > 0.65 مباشرةً إلى صنف «low/high» ثمّ إلى معدّل N من جدولٍ
موسوم في المصدر «UNVALIDATED DEFAULT»، بثقة 0.75 (و0.90 مع فحص التربة) — أي أنّ مؤشّر الأقمار
وحده كان يختار جرعة السماد، والثقةُ رقمٌ فوق أساسٍ لم يراجعه أحد.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/sahool-platform"))

from api.prescriptions import (  # noqa: E402
    PrescriptionGenerator,
    ZoneCharacteristics,
    ZoneClass,
    prescription_to_csv,
    prescription_to_dict,
)

pytestmark = pytest.mark.unit


def _rx(ndvi, zone_class=ZoneClass.MEDIUM, **extra):
    zone = ZoneCharacteristics(
        zone_id="z1", zone_class=zone_class, area_ha=1.0, ndvi_mean=ndvi, **extra
    )
    return PrescriptionGenerator().generate_nitrogen("f", "s", "wheat", [zone])


@pytest.mark.parametrize("ndvi", [0.2, 0.5, 0.8])
def test_ndvi_alone_does_not_change_the_nitrogen_rate(ndvi):
    """الزون نفسها بـNDVI منخفض أو متوسّط أو مرتفع ⇒ المعدّلُ نفسُه (صنف medium: 120)."""
    assert _rx(ndvi).zones[0].rate == 120.0


def test_a_diverging_ndvi_is_surfaced_as_a_diagnostic_warning():
    zone = _rx(0.2).zones[0]
    assert any("تشخيصيّ" in w and "low" in w for w in zone.warnings)
    assert not any("تشخيصيّ" in w for w in _rx(0.5).zones[0].warnings)


def test_an_explicit_zone_class_still_selects_the_rate():
    assert _rx(0.5, zone_class=ZoneClass.HIGH).zones[0].rate == 150.0


def test_no_numeric_confidence_over_an_unvalidated_table_even_with_a_soil_test():
    rx = _rx(0.5, soil_n_ppm=10)
    assert rx.zones[0].confidence is None


def test_the_response_declares_the_basis_and_requires_review():
    payload = prescription_to_dict(_rx(0.5))
    assert payload["rate_basis"] == "unvalidated_default_table"
    assert payload["authoritative"] is False
    assert payload["requires_agronomist_review"] is True
    assert "UNVALIDATED" in payload["notes_ar"] and "ليست جرعةً للتنفيذ" in payload["notes_ar"]


def test_csv_export_leaves_an_unknown_confidence_blank():
    line = prescription_to_csv(_rx(0.5)).splitlines()[-1]
    assert ",kg/ha (N),," in line
