#!/usr/bin/env python3
"""
اختبارات وحدة لخدمة تحليل الغطاء النباتي — منطق صرف (offline).
تغطّي: حساب المؤشّرات، تصنيف الصحّة، التوصيات، تحديد البذرة، النطاقات.
ترفع التغطية من 0% (فجوة المراجعة).

التشغيل:
  pytest services/vegetation-analysis-service/test_vegetation_logic.py -v
  أو offline: python3 services/vegetation-analysis-service/test_vegetation_logic.py
"""

import math
import os
import sys

# استيراد دوالّ المنطق من main (بلا تشغيل الخادم)
sys.path.insert(0, os.path.dirname(__file__))
from main import (  # noqa: E402
    _compute_indices,
    _deterministic_seed,
    _health_classification,
    _realistic_bands,
    _recommendations_ar,
)


# ── ١. حساب المؤشّرات الطيفيّة ──
def test_ndvi_formula_correct():
    """NDVI = (NIR-RED)/(NIR+RED) — التحقّق من الصيغة الأساسيّة."""
    bands = {
        "B02": 0.04,
        "B03": 0.06,
        "B04": 0.05,
        "B05": 0.2,
        "B06": 0.22,
        "B08": 0.5,
        "B11": 0.18,
        "B12": 0.15,
    }
    idx = _compute_indices(bands)
    expected_ndvi = (0.5 - 0.05) / (0.5 + 0.05)
    assert abs(idx["ndvi"] - round(expected_ndvi, 3)) < 0.01


def test_indices_within_valid_ranges():
    """كلّ المؤشّرات ضمن نطاقاتها الفيزيائيّة الصحيحة."""
    bands = {
        "B02": 0.04,
        "B03": 0.06,
        "B04": 0.05,
        "B05": 0.2,
        "B06": 0.22,
        "B08": 0.5,
        "B11": 0.18,
        "B12": 0.15,
    }
    idx = _compute_indices(bands)
    assert -1.0 <= idx["ndvi"] <= 1.0
    assert -1.0 <= idx["ndwi"] <= 1.0
    assert -1.0 <= idx["ndmi"] <= 1.0
    assert 0.0 <= idx["cwsi"] <= 1.0  # CWSI مقيّد [0,1]
    assert idx["lai"] >= 0.0  # LAI لا يكون سالباً


def test_compute_indices_returns_all_keys():
    """يُعيد كلّ المؤشّرات المتوقّعة."""
    bands = {
        "B02": 0.04,
        "B03": 0.06,
        "B04": 0.05,
        "B05": 0.2,
        "B06": 0.22,
        "B08": 0.5,
        "B11": 0.18,
        "B12": 0.15,
    }
    idx = _compute_indices(bands)
    for key in ("ndvi", "evi", "savi", "ndwi", "ndmi", "gndvi", "recl", "lai", "cwsi"):
        assert key in idx


def test_high_nir_gives_high_ndvi():
    """نبات صحّي (NIR عالٍ، RED منخفض) → NDVI عالٍ."""
    bands = {
        "B02": 0.03,
        "B03": 0.05,
        "B04": 0.04,
        "B05": 0.2,
        "B06": 0.22,
        "B08": 0.6,
        "B11": 0.18,
        "B12": 0.15,
    }
    idx = _compute_indices(bands)
    assert idx["ndvi"] > 0.7


# ── ٢. تصنيف الصحّة ──
def test_health_excellent():
    h = _health_classification(ndvi=0.75, cwsi=0.2)
    assert h["status"] == "excellent"
    assert h["score"] == 95


def test_health_critical():
    h = _health_classification(ndvi=0.15, cwsi=0.9)
    assert h["status"] == "critical"
    assert h["score"] == 10


def test_health_thresholds_ordered():
    """درجات الصحّة تنازليّة مع تدهور NDVI."""
    scores = [
        _health_classification(0.75, 0.2)["score"],  # excellent
        _health_classification(0.60, 0.4)["score"],  # good
        _health_classification(0.45, 0.6)["score"],  # fair
        _health_classification(0.25, 0.5)["score"],  # poor
        _health_classification(0.10, 0.5)["score"],  # critical
    ]
    assert scores == sorted(scores, reverse=True)


def test_health_has_arabic_label():
    h = _health_classification(0.75, 0.2)
    assert "label_ar" in h and h["label_ar"]  # تسمية عربيّة موجودة


# ── ٣. التوصيات العربيّة ──
def test_recommendation_water_stress():
    """CWSI عالٍ → توصية ري فوري."""
    idx = {"ndvi": 0.6, "cwsi": 0.7, "ndwi": 0.1, "recl": 2.0}
    recs = _recommendations_ar(idx, {}, "wheat")
    assert any("ري" in r for r in recs)


def test_recommendation_healthy_crop():
    """محصول صحّي → لا تحذيرات (توصية إيجابيّة)."""
    idx = {"ndvi": 0.75, "cwsi": 0.1, "ndwi": 0.2, "recl": 2.5}
    recs = _recommendations_ar(idx, {}, "wheat")
    assert len(recs) == 1
    assert "✅" in recs[0]


def test_recommendation_low_ndvi_pest():
    """NDVI منخفض → تحذير آفة/مرض."""
    idx = {"ndvi": 0.30, "cwsi": 0.2, "ndwi": 0.1, "recl": 2.0}
    recs = _recommendations_ar(idx, {}, "wheat")
    assert any("آفة" in r or "مرض" in r for r in recs)


# ── ٤. تحديد البذرة (تكراريّة/حتميّة) ──
def test_seed_deterministic():
    """نفس المُدخل → نفس البذرة (للتكرار)."""
    s1 = _deterministic_seed("field-A", "2026-05-18")
    s2 = _deterministic_seed("field-A", "2026-05-18")
    assert s1 == s2


def test_seed_varies_by_input():
    """حقول/تواريخ مختلفة → بذور مختلفة."""
    s1 = _deterministic_seed("field-A", "2026-05-18")
    s2 = _deterministic_seed("field-B", "2026-05-18")
    s3 = _deterministic_seed("field-A", "2026-06-18")
    assert s1 != s2 and s1 != s3


# ── ٥. توليد النطاقات ──
def test_realistic_bands_keys():
    """يُعيد كلّ نطاقات Sentinel-2 المطلوبة."""
    bands = _realistic_bands("field-A", "2026-05-18")
    for b in ("B02", "B03", "B04", "B05", "B06", "B08", "B11", "B12"):
        assert b in bands


def test_realistic_bands_deterministic():
    """نطاقات حتميّة (نفس المُدخل → نفس النطاقات)."""
    b1 = _realistic_bands("field-A", "2026-05-18")
    b2 = _realistic_bands("field-A", "2026-05-18")
    assert b1 == b2


def test_realistic_bands_physically_valid():
    """قيم الانعكاس ضمن [0,1] (فيزيائيّاً صحيحة)."""
    bands = _realistic_bands("field-A", "2026-05-18")
    for v in bands.values():
        assert 0.0 <= v <= 1.0


def test_bands_feed_indices_consistently():
    """النطاقات المولّدة تُنتج مؤشّرات صحيحة (تكامل داخلي)."""
    bands = _realistic_bands("field-A", "2026-05-18")
    idx = _compute_indices(bands)
    assert -1.0 <= idx["ndvi"] <= 1.0
    assert idx["lai"] >= 0.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  \u2713 {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            print(f"  \u2717 {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} \u0646\u062c\u0627\u062d")
    sys.exit(0 if passed == len(fns) else 1)
