"""حُرّاس كاشف تعارض الاستشعار مع المرحلة (EO ↔ Stage) — منطق نقيّ."""

from __future__ import annotations

from core.eo_stage_mismatch import detect_eo_stage_mismatch


class TestMismatchDetection:
    def test_active_stage_low_ndvi_is_mismatch(self):
        # mid يتوقّع NDVI≥0.55؛ المرصود 0.40 وجودة جيّدة ⇒ below_expected.
        r = detect_eo_stage_mismatch("mid", 0.40, valid_pixel_ratio=0.9, cloud_pct=5)
        assert r["status"] == "below_expected"
        assert r["severity"] == "medium"

    def test_ndmi_escalates_to_high(self):
        # نفس التعارض + NDMI منخفض (إجهاد مائيّ) ⇒ high + corroborated.
        r = detect_eo_stage_mismatch("mid", 0.40, 0.05, valid_pixel_ratio=0.9, cloud_pct=5)
        assert r["severity"] == "high"
        assert r["corroborated_by_ndmi"] is True

    def test_aligned_when_ndvi_in_range(self):
        r = detect_eo_stage_mismatch("mid", 0.72, valid_pixel_ratio=0.95, cloud_pct=2)
        assert r["status"] == "aligned" and r["severity"] == "none"

    def test_low_ndvi_normal_at_initial(self):
        # الانخفاض طبيعيّ في التأسيس ⇒ لا إنذار.
        r = detect_eo_stage_mismatch("initial", 0.15, valid_pixel_ratio=0.9, cloud_pct=5)
        assert r["status"] == "aligned"

    def test_low_ndvi_normal_at_late(self):
        r = detect_eo_stage_mismatch("late", 0.35, valid_pixel_ratio=0.9, cloud_pct=5)
        assert r["status"] == "aligned"

    def test_above_expected_flags_low_severity(self):
        r = detect_eo_stage_mismatch("initial", 0.55, valid_pixel_ratio=0.9, cloud_pct=5)
        assert r["status"] == "above_expected" and r["severity"] == "low"


class TestSceneQualityGuard:
    def test_poor_quality_gives_no_strong_alarm(self):
        # جوهر القاعدة: NDVI منخفض لكن جودة ضعيفة (سُحُب عالية) ⇒ inconclusive لا إنذار.
        r = detect_eo_stage_mismatch("mid", 0.30, 0.05, valid_pixel_ratio=0.3, cloud_pct=80)
        assert r["status"] == "inconclusive"
        assert r["severity"] == "none"
        assert r["scene_quality_ok"] is False
        assert r["confidence"] == "low"

    def test_low_valid_pixels_alone_blocks_alarm(self):
        r = detect_eo_stage_mismatch("mid", 0.30, valid_pixel_ratio=0.4)
        assert r["status"] == "inconclusive"

    def test_unknown_quality_lowers_confidence(self):
        # لا إشارات جودة ⇒ التقييم يمضي لكنّ scene_quality في evidence_missing وثقة منخفضة.
        r = detect_eo_stage_mismatch("mid", 0.40)
        assert r["scene_quality_ok"] is None
        assert "scene_quality" in r["evidence_missing"]
        assert r["confidence"] == "low"


class TestHonesty:
    def test_no_stage_inconclusive(self):
        r = detect_eo_stage_mismatch(None, 0.4)
        assert r["status"] == "inconclusive" and "current_stage" in r["evidence_missing"]

    def test_no_ndvi_inconclusive(self):
        r = detect_eo_stage_mismatch("mid", None)
        assert r["status"] == "inconclusive" and "ndvi" in r["evidence_missing"]

    def test_confidence_never_high(self):
        r = detect_eo_stage_mismatch("mid", 0.4, 0.05, valid_pixel_ratio=0.95, cloud_pct=1)
        assert r["confidence"] in ("low", "medium") and r["confidence"] != "high"

    def test_reports_baseline_limitation_honestly(self):
        r = detect_eo_stage_mismatch("mid", 0.72, valid_pixel_ratio=0.9)
        assert "أساس السلوك الطبيعيّ" in r["baseline_note_ar"]
