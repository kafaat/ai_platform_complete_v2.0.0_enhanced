"""حُرّاس حارس تقويم الموسم (Season Calendar Guard) — منطق نقيّ.

يبني على نوافذ الزراعة الموثّقة في api.planting_calendar (قمح شتويّ نوفمبر–يناير،
ذرة شاميّة صيفيّة مارس–يونيو…). صدق: محصول بلا تقويم ⇒ unknown + requires_review.
"""

from __future__ import annotations

from datetime import date

from api.season_calendar_guard import evaluate_season_calendar


class TestSowingWindow:
    def test_wheat_optimal_sowing(self):
        # القمح: نوفمبر ضمن المثلى.
        v = evaluate_season_calendar("wheat", date(2026, 11, 15))
        assert v["supported"] and v["status"] == "optimal"
        assert v["requires_review"] is False
        assert v["confidence"] == "medium"  # سقف تقريبيّ

    def test_wheat_valid_but_not_optimal(self):
        # يناير ضمن النافذة (11,12,1) لكن ليس المثلى (11,12).
        v = evaluate_season_calendar("wheat", date(2026, 1, 20))
        assert v["status"] == "valid" and v["requires_review"] is False

    def test_wheat_out_of_window_flags_review(self):
        # مايو خارج نافذة القمح الشتويّة ⇒ out_of_window + requires_review.
        v = evaluate_season_calendar("wheat", date(2026, 5, 1))
        assert v["status"] == "out_of_window"
        assert v["requires_review"] is True
        assert "خارج نافذة" in v["reason_ar"]

    def test_maize_summer_optimal(self):
        v = evaluate_season_calendar("maize", date(2026, 4, 10))
        assert v["status"] == "optimal"

    def test_arabic_alias_resolves(self):
        v = evaluate_season_calendar("قمح", date(2026, 11, 1))
        assert v["supported"] and v["crop"] == "wheat"


class TestHarvestWindow:
    def test_harvest_in_window_stays_valid(self):
        # قمح: بذار نوفمبر (مثلى) + نهاية أبريل (حصاد 4,5) ⇒ optimal يبقى.
        v = evaluate_season_calendar("wheat", date(2025, 11, 15), date(2026, 4, 20))
        assert v["harvest_status"] == "valid"
        assert v["status"] == "optimal"

    def test_harvest_adjacent_is_unusual(self):
        # نهاية مارس (قرب حصاد القمح 4,5 بتسامح ±1) ⇒ unusual ⇒ requires_review.
        v = evaluate_season_calendar("wheat", date(2025, 11, 15), date(2026, 3, 20))
        assert v["harvest_status"] == "unusual"
        assert v["status"] == "unusual" and v["requires_review"] is True

    def test_harvest_far_is_out_of_window(self):
        # نهاية أغسطس بعيدة عن حصاد القمح (4,5) ⇒ out_of_window.
        v = evaluate_season_calendar("wheat", date(2025, 11, 15), date(2026, 8, 1))
        assert v["harvest_status"] == "out_of_window"
        assert v["status"] == "out_of_window"

    def test_worst_status_governs(self):
        # بذار مثاليّ لكن حصاد شاذّ ⇒ الحكم الموحّد يأخذ الأسوأ.
        v = evaluate_season_calendar("maize", date(2026, 4, 10), date(2026, 12, 1))
        assert v["status"] in ("unusual", "out_of_window")
        assert v["requires_review"] is True


class TestHonestUnknown:
    def test_unsupported_crop_is_unknown_requires_review(self):
        # محصول بلا تقويم (لدينا فقط حبوب رئيسة) ⇒ unknown، لا يُختلَق حكم.
        v = evaluate_season_calendar("coffee", date(2026, 4, 1))
        assert v["supported"] is False
        assert v["status"] == "unknown" and v["requires_review"] is True
        assert v["confidence"] == "low"

    def test_missing_sowing_date_unknown(self):
        v = evaluate_season_calendar("wheat", None)
        assert v["status"] == "unknown" and v["requires_review"] is True

    def test_region_flagged_as_national_not_differentiated(self):
        # صدق: تمرير region لا يُنتِج دقّة إقليميّة غير موجودة — يُصرَّح بذلك.
        v = evaluate_season_calendar("wheat", date(2026, 11, 1), region="central_highlands")
        assert v["region_note_ar"] and "وطنيّة" in v["region_note_ar"]

    def test_confidence_never_high(self):
        # السقف MEDIUM دائماً للمحاصيل المدعومة (النوافذ تقريبيّة).
        for m in (11, 12, 1, 5):
            v = evaluate_season_calendar("wheat", date(2026, m, 15))
            assert v["confidence"] in ("medium", "low")
            assert v["confidence"] != "high"
