"""تحقّق — شكل النشرة الإقليميّة (الشريحة C، منطق صرف): صفوف + خصوصيّة + إعلان تصنيفيّ."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bulletin_figure import bulletin_self_checks, bulletin_to_rows  # noqa: E402

pytestmark = pytest.mark.unit


def _bulletin() -> dict:
    return {
        "schema": "sahool.regional_bulletin/1",
        "period": "2026-06",
        "privacy_floor_fields": 5,
        "governorate_count": 2,
        "governorates": [
            {
                "governorate": "الجوف",
                "status": "published",
                "condition": "watch",
                "mean_ndvi_anomaly": -0.08,
                "districts": [
                    {
                        "district": "الحزم",
                        "status": "published",
                        "condition": "poor",
                        "mean_ndvi_anomaly": -0.2,
                    },
                    {
                        "district": "خبّ",
                        "status": "suppressed_for_privacy",
                        "reason": "fewer_than_5_fields",
                        "field_count": 2,
                    },
                ],
            },
            {
                "governorate": "مأرب",
                "status": "suppressed_for_privacy",
                "field_count": 3,
                "districts": [],
            },
        ],
    }


def test_rows_published_keep_value_suppressed_are_hidden():
    rows = bulletin_to_rows(_bulletin())
    by = {(r["governorate"], r["district"]): r for r in rows}
    jawf = by[("الجوف", None)]
    assert jawf["condition"] == "watch" and jawf["mean_ndvi_anomaly"] == -0.08
    khab = by[("الجوف", "خبّ")]
    assert khab["condition"] == "suppressed" and khab["mean_ndvi_anomaly"] is None
    assert khab["label"] == "مكتوم (خصوصيّة)"
    marib = by[("مأرب", None)]
    assert marib["condition"] == "suppressed" and marib["mean_ndvi_anomaly"] is None


def test_self_checks_pass_and_declare_non_geographic():
    sc = bulletin_self_checks(_bulletin())
    assert sc["passed"] is True and sc["quality"] == "good"
    geo = next(c for c in sc["checks"] if c["name"] == "admin_geometry_present")
    assert geo["passed"] is None and "شكل تصنيفيّ" in geo["detail"]


def test_privacy_leak_is_required_failure():
    b = _bulletin()
    # مجموعة مكتومة تُسرِّب رقماً ⇒ يجب أن يفشل الفحص (حماية أرضيّة الخصوصيّة).
    b["governorates"][1]["mean_ndvi_anomaly"] = -0.3
    sc = bulletin_self_checks(b)
    leak = next(c for c in sc["checks"] if c["name"] == "privacy_floor_respected")
    assert leak["passed"] is False and sc["quality"] == "failed"


def test_malformed_yields_empty_and_failed():
    assert bulletin_to_rows(None) == []
    sc = bulletin_self_checks({})
    assert sc["passed"] is False  # has_governorates required فشل
