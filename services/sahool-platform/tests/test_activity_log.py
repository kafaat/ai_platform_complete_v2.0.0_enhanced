"""Tests for activity log (farmOS Log/Task inspired): closes the loop
recommendation → planned task → completed/skipped → adoption signal → learning."""

from core.activity_log import (
    ActivityStatus,
    ActivityType,
    activities_for_recommendation,
    adoption_summary,
    mark_completed,
    mark_skipped,
    new_activity_id,
    overdue_activities,
    plan_activity_from_recommendation,
)


class TestPlanFromRecommendation:
    def test_plan_creates_planned_task(self):
        t = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="rec1",
            activity_type="irrigation",
            planned_date="2026-06-01",
            quantity=20.0,
            unit="mm",
        )
        assert t.status == ActivityStatus.PLANNED
        assert t.activity_type == ActivityType.IRRIGATION
        assert t.rec_id == "rec1"
        assert t.quantity == 20.0

    def test_unknown_type_falls_to_other(self):
        # القاعدة: لا نخترع، نستخدم OTHER عند عدم التطابق
        t = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="rec1",
            activity_type="weird_unknown_type",
            planned_date="2026-06-01",
        )
        assert t.activity_type == ActivityType.OTHER

    def test_unique_activity_ids(self):
        ids = {new_activity_id() for _ in range(50)}
        assert len(ids) == 50


class TestCompletion:
    def test_mark_completed_records_actual(self):
        # CRITICAL: نحفظ الفعلي (قد يختلف عن المخطّط) — للمعايرة
        t = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="rec1",
            activity_type="irrigation",
            planned_date="2026-06-01",
            quantity=20.0,
            unit="mm",
        )
        mark_completed(t, completed_date="2026-06-01", actual_quantity=18.0)
        assert t.status == ActivityStatus.COMPLETED
        assert t.quantity == 18.0  # الفعلي يحلّ محلّ المخطّط

    def test_completion_default_date(self):
        t = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="rec1",
            activity_type="irrigation",
            planned_date="2026-06-01",
        )
        mark_completed(t)
        assert t.completed_date is not None


class TestSkipping:
    def test_skip_records_reason(self):
        # CRITICAL: الرفض معلومة — السبب يُحفظ كإشارة تعلّم
        t = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="rec1",
            activity_type="fertilization",
            planned_date="2026-06-01",
        )
        mark_skipped(t, reason_ar="السماد غير متوفّر")
        assert t.status == ActivityStatus.SKIPPED
        assert t.skip_reason == "السماد غير متوفّر"


class TestQueries:
    def test_overdue_filters_past_planned(self):
        past = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="r1",
            activity_type="irrigation",
            planned_date="2026-01-01",
        )
        future = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="r2",
            activity_type="irrigation",
            planned_date="2099-01-01",
        )
        overdue = overdue_activities([past, future], today="2026-05-27")
        assert past in overdue
        assert future not in overdue

    def test_completed_not_overdue(self):
        # المكتمل لا يُعدّ متأخّراً حتى لو تاريخه قديم
        done = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="r1",
            activity_type="irrigation",
            planned_date="2026-01-01",
        )
        mark_completed(done, completed_date="2026-01-02")
        assert done not in overdue_activities([done], today="2026-05-27")

    def test_activities_for_recommendation(self):
        a1 = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="rec_A",
            activity_type="irrigation",
            planned_date="2026-06-01",
        )
        a2 = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="rec_B",
            activity_type="irrigation",
            planned_date="2026-06-02",
        )
        result = activities_for_recommendation([a1, a2], "rec_A")
        assert a1 in result
        assert a2 not in result


class TestAdoptionSummary:
    def test_adoption_rate_calculation(self):
        # 2 منفّذ، 1 متجاوَز → معدّل 67%
        acts = []
        for i in range(2):
            t = plan_activity_from_recommendation(
                tenant_id="t1",
                field_id="f1",
                rec_id=f"r{i}",
                activity_type="irrigation",
                planned_date="2026-06-01",
            )
            mark_completed(t)
            acts.append(t)
        skipped = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="r2",
            activity_type="fertilization",
            planned_date="2026-06-01",
        )
        mark_skipped(skipped, reason_ar="غير متوفّر")
        acts.append(skipped)
        s = adoption_summary(acts)
        assert s["completed"] == 2
        assert s["skipped"] == 1
        assert s["adoption_rate"] == round(2 / 3, 2)

    def test_empty_returns_none_rate(self):
        # CRITICAL: لا اختراع — قائمة فارغة → معدّل null لا 0
        s = adoption_summary([])
        assert s["adoption_rate"] is None
        assert s["total"] == 0

    def test_all_pending_returns_none_rate(self):
        # كل المهام معلّقة → لا معدّل تبنّي بعد
        t = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="r1",
            activity_type="irrigation",
            planned_date="2026-06-01",
        )
        s = adoption_summary([t])
        assert s["adoption_rate"] is None
        assert s["pending"] == 1


class TestGeoTag:
    """ربط المهام بالإحداثيات (farmOS Logs المكانية)."""

    def test_activity_can_carry_lon_lat(self):
        t = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="r1",
            activity_type="irrigation",
            planned_date="2026-06-01",
            lon=44.5,
            lat=16.2,
        )
        assert t.lon == 44.5
        assert t.lat == 16.2

    def test_activity_geo_tag_optional(self):
        # Geo-tag اختياري — التوافق الخلفي محفوظ
        t = plan_activity_from_recommendation(
            tenant_id="t1",
            field_id="f1",
            rec_id="r1",
            activity_type="irrigation",
            planned_date="2026-06-01",
        )
        assert t.lon is None
        assert t.lat is None
