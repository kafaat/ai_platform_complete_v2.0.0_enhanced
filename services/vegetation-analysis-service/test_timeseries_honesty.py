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
    # المسار الإنتاجي يقرأ المصدر الحقيقي ولا يولّد نقاطاً تركيبية عند الغياب.
    assert "_real_timeseries_from_raster" in src
    assert '"data_source": "raster-service"' in src
    assert '"timeseries": []' in src
    assert '"synthetic": False' in src


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


def test_analyze_accepts_and_echoes_season_id():
    from pathlib import Path

    root = Path(__file__).resolve().parent
    route = (root / "routers" / "analysis.py").read_text(encoding="utf-8")
    rt = (root / "vegetation_runtime.py").read_text(encoding="utf-8")
    # V5: المسار يقبل season_id ويمرّره؛ run_analysis يقبله ويُصدّره في الرد.
    assert "season_id: str | None = Query(default=None" in route
    assert "season_id=season_id" in route
    assert "season_id: str | None = None" in rt
    assert '"season_id": season_id' in rt
