#!/usr/bin/env python3
"""
اختبارات وحدة لموجّه النوايا (router.py) — منطق التصنيف (offline).
تغطّي classify_intent بالعربي والإنجليزي + تحمي من خطأ tatweel المُصلَح.
ترفع تغطية supervisor-agent (كان router.py 0%).

التشغيل:
  pytest services/supervisor-agent/test_router.py -v
  أو offline: python3 services/supervisor-agent/test_router.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from router import HierarchicalRouter  # noqa: E402


def _classify(query):
    r = HierarchicalRouter(skill_libraries={})
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(r.classify_intent(query))
    finally:
        loop.close()


# ── ١. التصنيف العربي (الأهمّ — لغة المستخدم) ──
def test_arabic_ndvi_routes_remote_sensing():
    d, s, c = _classify("ما هو NDVI لحقلي؟")
    assert d == "remote_sensing"


def test_arabic_price_routes_market():
    d, s, c = _classify("ما سعر القمح في السوق؟")
    assert d == "market"
    assert s == "price_current"


def test_arabic_pest_routes_advisory():
    d, s, c = _classify("لدي آفة في الحقل ماذا أفعل؟")
    assert d == "advisory"
    assert s == "pest_id"


def test_arabic_irrigation_routes_crop_model():
    """صيغة الفعل 'أسقي' تُوجَّه للري (إصلاح نمط)."""
    d, s, c = _classify("متى أسقي المحصول؟")
    assert d == "crop_model"
    assert s == "irrigation_advice"


def test_arabic_simulation_routes_crop_model():
    d, s, c = _classify("نموذج محاكاة الإنتاج")
    assert d == "crop_model"


# ── ٢. حماية من رجوع خطأ tatweel (regression guard) ──
def test_no_tatweel_in_patterns():
    """الأنماط خالية من tatweel (يكسر مطابقة العربي الطبيعي)."""
    src = open(os.path.join(os.path.dirname(__file__), "router.py"),
               encoding="utf-8").read()
    assert "\u0640" not in src, "tatweel رجع للأنماط — يكسر التصنيف العربي"


def test_natural_arabic_not_all_default():
    """استعلامات عربيّة متنوّعة لا تسقط كلّها في advisory الافتراضي."""
    queries = ["ما سعر القمح؟", "متى أسقي؟", "تحليل NDVI",
               "محاكاة الإنتاج"]
    domains = {_classify(q)[0] for q in queries}
    # لو كانت كلّها advisory → خطأ tatweel رجع
    assert len(domains) > 1, "كلّ الاستعلامات سقطت في domain واحد (خطأ tatweel؟)"


# ── ٣. التصنيف الإنجليزي ──
def test_english_ndvi():
    d, s, c = _classify("show me NDVI for my field")
    assert d == "remote_sensing"
    assert s == "ndvi"


def test_english_price():
    d, s, c = _classify("what is the market price")
    assert d == "market"


def test_english_irrigation():
    """'irrigation' (الاسم) يُوجَّه للري. ملاحظة: 'irrigate' (الفعل)
    لا يطابق حاليّاً — فجوة نمط إنجليزي معروفة (وثّقناها)."""
    d, s, c = _classify("irrigation schedule for my crop")
    assert d == "crop_model"
    assert s == "irrigation_advice"


# ── ٤. السلوك الافتراضي والثقة ──
def test_unknown_query_defaults_advisory():
    d, s, c = _classify("مرحبا كيف حالك")
    assert d == "advisory"
    assert s == "general_advice"
    assert c == 0.5  # ثقة منخفضة للافتراضي


def test_confidence_in_valid_range():
    """الثقة دائماً ضمن [0, 1]."""
    for q in ["ما سعر القمح؟", "NDVI", "آفة", "xyz random"]:
        _, _, c = _classify(q)
        assert 0.0 <= c <= 1.0


def test_matched_query_higher_confidence_than_default():
    """استعلام مطابق ثقته أعلى من الافتراضي."""
    _, _, c_matched = _classify("ما سعر القمح في السوق؟")
    _, _, c_default = _classify("مرحبا")
    assert c_matched > c_default


# ── ٥. تصنيف ثنائي اللغة (عربي + إنجليزي مختلط) ──
def test_mixed_language_price_query():
    """استعلام إنجليزي صريح للسعر يُوجَّه للسوق."""
    d, s, c = _classify("market price for wheat")
    assert d == "market"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
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
