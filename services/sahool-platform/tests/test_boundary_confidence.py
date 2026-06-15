"""اختبارات محرّك ثقة الحدود (api.boundary_confidence) — منطق نقيّ offline.

يغطّي: حدّ نظيف صالح ⇒ ثقة عالية بلا توصية مراجعة؛ حدّ غير صالح/متقاطع ذاتيّاً
⇒ ثقة منخفضة + توصية مراجعة؛ مفاتيح ناقصة/فاسدة لا ترمي وتُنتج عامل بيانات
مفقودة؛ الاتّفاق الزمنيّ يرفع الثقة عند توفّره. لا قاعدة ولا شبكة — كلّه حتميّ.

تذكير صدق: هذه قابليّة معقوليّة هندسيّة حتميّة (heuristic) لا ثقة ML.
"""

from api.boundary_confidence import (
    CONFIDENCE_REVIEW_THRESHOLD,
    score_boundary,
)


def _clean_props() -> dict:
    """حدّ نظيف معقول: صالح، بلا تقاطع، مساحة معقولة، رؤوس معقولة."""
    return {
        "vertex_count": 12,
        "area_ha": 4.5,
        "is_valid": True,
        "ring_count": 1,
        "self_intersections": 0,
    }


class TestCleanBoundary:
    def test_high_confidence(self):
        out = score_boundary(_clean_props())
        assert out["confidence"] >= 0.8

    def test_no_review_recommended(self):
        out = score_boundary(_clean_props())
        assert out["review_recommended"] is False

    def test_returns_factors_list(self):
        out = score_boundary(_clean_props())
        assert isinstance(out["factors"], list)


class TestBadBoundary:
    def test_invalid_geometry_low_confidence(self):
        props = _clean_props()
        props["is_valid"] = False
        out = score_boundary(props)
        assert out["confidence"] < CONFIDENCE_REVIEW_THRESHOLD
        assert out["review_recommended"] is True

    def test_self_intersection_flagged(self):
        props = _clean_props()
        props["is_valid"] = False
        props["self_intersections"] = 3
        out = score_boundary(props)
        assert out["confidence"] < CONFIDENCE_REVIEW_THRESHOLD
        assert out["review_recommended"] is True

    def test_implausible_area_penalised(self):
        props = _clean_props()
        props["area_ha"] = 999999.0
        out = score_boundary(props)
        clean = score_boundary(_clean_props())
        assert out["confidence"] < clean["confidence"]

    def test_too_few_vertices_penalised(self):
        props = _clean_props()
        props["vertex_count"] = 2
        out = score_boundary(props)
        assert out["confidence"] < score_boundary(_clean_props())["confidence"]


class TestSafeDefaults:
    def test_missing_keys_does_not_raise(self):
        out = score_boundary({})
        assert 0.0 <= out["confidence"] <= 1.0

    def test_missing_keys_notes_missing_data(self):
        out = score_boundary({})
        joined = " ".join(f["name_ar"] for f in out["factors"])
        assert "مفقودة" in joined

    def test_garbage_values_does_not_raise(self):
        out = score_boundary(
            {
                "vertex_count": "abc",
                "area_ha": "xyz",
                "is_valid": "maybe",
                "ring_count": None,
                "self_intersections": [],
            }
        )
        assert 0.0 <= out["confidence"] <= 1.0

    def test_non_dict_input_does_not_raise(self):
        out = score_boundary(None)  # type: ignore[arg-type]
        assert 0.0 <= out["confidence"] <= 1.0


class TestTemporalAgreement:
    def test_temporal_agreement_raises_confidence(self):
        """على حدّ ضعيف هندسيّاً، اتّفاق زمنيّ عالٍ يرفع الثقة."""
        props = _clean_props()
        props["area_ha"] = 999999.0  # عقوبة تُنزل الثقة الهندسيّة
        without = score_boundary(dict(props))
        props_with = dict(props)
        props_with["temporal_agreement"] = 1.0
        with_temporal = score_boundary(props_with)
        assert with_temporal["confidence"] > without["confidence"]

    def test_temporal_none_notes_single_date(self):
        props = _clean_props()
        props["temporal_agreement"] = None
        out = score_boundary(props)
        joined = " ".join(f["name_ar"] for f in out["factors"])
        assert "أحاديّ التاريخ" in joined

    def test_temporal_out_of_range_clamped(self):
        props = _clean_props()
        props["temporal_agreement"] = 5.0  # يُقصّ إلى 1.0
        out = score_boundary(props)
        assert 0.0 <= out["confidence"] <= 1.0


class TestThreshold:
    def test_threshold_value(self):
        assert CONFIDENCE_REVIEW_THRESHOLD == 0.6
