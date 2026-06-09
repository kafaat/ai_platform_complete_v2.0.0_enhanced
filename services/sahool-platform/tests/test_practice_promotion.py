"""Tests for crowd-practice promotion ladder. Guards: 0.65 ceiling never exceeded,
PHI/FAO conflict = permanent rejection, high-variance = frozen, physics > community."""

from core.practice_promotion import (
    FSI_CEILING_COMMUNITY,
    PhysicalCompat,
    PracticeEvidence,
    evaluate_practice,
)


class TestCeiling:
    def test_never_exceeds_community_ceiling(self):
        # CRITICAL: أقصى ممارسة لا تتجاوز 0.65 (لا تبلغ الفيزياء 0.95)
        ev = PracticeEvidence(
            n_farmers=1000,
            spatial_fields=50,
            temporal_success_seasons=20,
            physical_compat=PhysicalCompat.COMPATIBLE,
            has_full_dataset=True,
            adoption_rate=1.0,
        )
        r = evaluate_practice(ev)
        assert r.fsi <= FSI_CEILING_COMMUNITY

    def test_strong_practice_reaches_medium(self):
        ev = PracticeEvidence(
            n_farmers=150,
            spatial_fields=5,
            temporal_success_seasons=8,
            physical_compat=PhysicalCompat.COMPATIBLE,
            has_full_dataset=True,
            adoption_rate=0.65,
        )
        r = evaluate_practice(ev)
        assert r.ceiling == "medium"
        assert r.show_in_farmer_view


class TestPermanentBlockers:
    def test_safety_violation_rejected(self):
        # CRITICAL: تعارض PHI/FAO → رفض نهائي مهما كان العدد
        ev = PracticeEvidence(n_farmers=1000, physical_compat=PhysicalCompat.VIOLATES_SAFETY)
        r = evaluate_practice(ev)
        assert r.fsi == 0.0
        assert not r.show_in_farmer_view
        assert "رفض" in r.reason_ar or "السلامة" in r.reason_ar

    def test_high_variance_frozen(self):
        # تباين عالٍ (std > mean) → تجميد
        ev = PracticeEvidence(n_farmers=100, yield_mean=3.0, yield_std=4.0)
        r = evaluate_practice(ev)
        assert not r.show_in_farmer_view
        assert "متباينة" in r.reason_ar or "مجمّدة" in r.status_ar

    def test_physical_conflict_drops(self):
        # تعارض فيزيائي → ينخفض (لا يُرقّى)
        ev = PracticeEvidence(n_farmers=50, physical_compat=PhysicalCompat.CONFLICTING)
        r = evaluate_practice(ev)
        assert r.fsi < 0.30
        assert not r.show_in_farmer_view


class TestAccumulation:
    def test_more_evidence_higher_fsi(self):
        weak = evaluate_practice(PracticeEvidence(n_farmers=10))
        strong = evaluate_practice(
            PracticeEvidence(
                n_farmers=200,
                spatial_fields=20,
                temporal_success_seasons=10,
                physical_compat=PhysicalCompat.COMPATIBLE,
                has_full_dataset=True,
                adoption_rate=0.7,
            )
        )
        assert strong.fsi > weak.fsi

    def test_oral_only_stays_guess(self):
        # ممارسة شفهية بلا شيء → تخمين، لا تُعرض
        r = evaluate_practice(PracticeEvidence(n_farmers=0))
        assert r.ceiling == "none"
        assert not r.show_in_farmer_view
