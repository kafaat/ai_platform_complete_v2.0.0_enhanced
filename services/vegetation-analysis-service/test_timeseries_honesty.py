"""Guard: vegetation timeseries never presents synthetic data as real (V2 fix).

المستهلكون (رسوم NDVI في الويب/الموبايل) كانوا يستقبلون سلسلة تركيبيّة بلا وسم
مصدر ⇒ تُعرَض كأنّها رصد حقيقيّ. هذا الحارس يمنع عودة تلك الفجوة.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytestmark = pytest.mark.unit


def test_generated_timeseries_points_are_labeled_synthetic():
    import vegetation_runtime as vr

    points = vr._generate_timeseries("fld_test", 30)
    assert points, "expected at least one point"
    for p in points:
        assert p.get("source") == "synthetic_estimate", p
        assert p.get("estimated") is True, p
        assert "date" in p


def test_timeseries_route_wraps_with_honest_flags():
    from pathlib import Path

    src = (Path(__file__).resolve().parent / "routers" / "analysis.py").read_text(encoding="utf-8")
    # الرد يحمل أعلام الصدق التي تمنع «تركيبيّ يُعرَض كحقيقيّ».
    assert '"data_source": "synthetic_estimate"' in src
    assert '"real_data": False' in src
    assert '"synthetic": True' in src
    assert "raster-service:/imagery/timeseries" in src  # المصدر الحقيقيّ مُعلَن


def test_recommendations_are_hypotheses_not_executive_commands():
    import vegetation_runtime as vr

    # إجهاد مائي تقديريّ ⇒ فرضيّة + تحقّق، لا أمر «اروِ الآن».
    recs = vr._recommendations_ar({"ndvi": 0.6, "cwsi": 0.7, "ndwi": 0.1, "recl": 2.0}, {}, "wheat")
    joined = " ".join(recs)
    assert "فرضيّة" in joined  # إطار الفرضيّة
    assert "الفوري" not in joined  # لا أمر تنفيذيّ مباشر
    assert "خدمة القرار" in joined  # القرار التنفيذيّ يُحال صراحةً


def test_analyze_response_flags_estimated_and_advisory_role():
    from pathlib import Path

    src = (Path(__file__).resolve().parent / "vegetation_runtime.py").read_text(encoding="utf-8")
    assert '"estimated": index_sources.get(k, "estimate") != "raster-service"' in src  # V3
    assert '"advisory_role": "hypothesis"' in src  # V4
