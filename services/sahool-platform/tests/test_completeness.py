"""Tests for data completeness + motivational messaging."""

from core.data_completeness import NotificationTrigger, build_notification, compute_completeness


class TestCompleteness:
    def test_empty_low_score(self):
        r = compute_completeness(set())
        assert r.score == 0
        assert not r.is_precise

    def test_governing_fields_make_precise(self):
        r = compute_completeness({"salinity_s3", "ph_s4", "water_i3"})
        assert r.is_precise

    def test_partial_not_precise_but_motivating(self):
        r = compute_completeness({"boundary", "crop", "ph_s4"})
        assert not r.is_precise
        assert r.score > 0
        assert r.next_value  # tells farmer what to add next

    def test_next_value_points_to_highest_weight(self):
        r = compute_completeness({"organic_matter"})  # low-weight only
        # should suggest a high-weight missing field
        assert "S3" in r.next_value or "المحصول" in r.next_value or "حدود" in r.next_value

    def test_score_monotonic(self):
        a = compute_completeness({"boundary"})
        b = compute_completeness({"boundary", "crop"})
        assert b.score > a.score

    def test_notification_precise_ready(self):
        n = build_notification(NotificationTrigger.PRECISE_READY, "محوري ١")
        assert "جاهز" in n["title_ar"]
        assert n["field"] == "محوري ١"

    def test_notification_reminder_uses_next_value(self):
        c = compute_completeness({"boundary"})
        n = build_notification(NotificationTrigger.REMINDER, "حقل", c)
        assert n["body_ar"]


class TestWheatOMThreshold:
    def test_wheat_om_optimal_is_verified_value(self):
        # verified from Nature Geoscience 2023 (13,662 trials): wheat SOC optimum ~1.3%
        import yaml

        card = yaml.safe_load(open("core/crop_cards/wheat.yaml", encoding="utf-8"))
        om = card["modifying"]["organic_matter_pct"]
        assert om["optimal_min"] == 1.3
        assert "Nature Geoscience" in om["source"]
