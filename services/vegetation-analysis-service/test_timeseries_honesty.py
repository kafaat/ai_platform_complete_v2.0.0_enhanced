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
