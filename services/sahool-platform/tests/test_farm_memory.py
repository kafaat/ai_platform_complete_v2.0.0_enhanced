"""Tests for farm_memory - unified operational memory.
Realizes the 'agricultural intelligence infrastructure' from Digital Ag OS doc."""

from core.farm_memory import (
    EventKind,
    FarmMemorySnapshot,
    MemoryEvent,
    build_farm_memory,
    events_around_recommendation,
    field_timeline,
    memory_density_report,
)
from core.learning.recommendation_log import RecommendationRecord


class _FakeActivity:
    def __init__(
        self,
        tenant_id,
        field_id,
        kind="planting",
        farm_id="frm_01",
        planned="2025-04-01",
        status="completed",
        notes="",
    ):
        self.tenant_id = tenant_id
        self.farm_id = farm_id
        self.field_id = field_id
        self.kind = kind
        self.planned_for = planned
        self.completed_at = planned
        self.status = status
        self.activity_id = f"act_{kind}_{field_id}"
        self.notes_ar = notes


class _FakeObs:
    def __init__(
        self,
        tenant_id,
        field_id,
        observable="ndvi",
        value=0.55,
        farm_id="frm_01",
        measured="2025-04-10",
    ):
        self.tenant_id = tenant_id
        self.farm_id = farm_id
        self.field_id = field_id
        self.observable_id = observable
        self.value = value
        self.unit = "ratio"
        self.measured_at = measured
        self.source = "sensor"
        self.confidence = "medium"
        self.observation_id = f"obs_{observable}_{field_id}"


def _rec(rec_id, tenant_id, field_id="fld_03", actual=None, issued="2025-03-20"):
    r = RecommendationRecord(
        rec_id=rec_id,
        tenant_id=tenant_id,
        district_id="al_bayda",
        zone_id=field_id,
        crop="wheat",
        issued_date=issued,
        recommendation_ar="اروِ 15مم",
        quality_grade="READY",
        predicted_yield_t_ha=3.5,
        confidence="medium",
    )
    if actual is not None:
        r.actual_yield_t_ha = actual
    r.farm_id = "frm_01"
    return r


class TestComposition:
    """farm_memory يجمع من 3+ مصادر، لا يكرّر التخزين."""

    def test_combines_activities_observations_recommendations(self):
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            activities=[_FakeActivity("tnt_001", "fld_03")],
            observations=[_FakeObs("tnt_001", "fld_03")],
            recommendations=[_rec("r1", "tnt_001", actual=3.4)],
        )
        # 1 activity + 1 obs + 1 rec + 1 outcome = 4
        assert snap.total_events == 4
        assert "activity" in snap.events_by_kind
        assert "observation" in snap.events_by_kind
        assert "recommendation" in snap.events_by_kind
        assert "outcome" in snap.events_by_kind

    def test_outcome_separate_event_from_recommendation(self):
        # CRITICAL: التوصية + النتيجة حدثان منفصلان (timeline أوضح)
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            recommendations=[_rec("r1", "tnt_001", actual=3.4)],
        )
        assert snap.events_by_kind.get("recommendation") == 1
        assert snap.events_by_kind.get("outcome") == 1

    def test_recommendation_without_outcome_no_invention(self):
        # CRITICAL: لا outcome إن لم يُسجَّل (صفر اختراع)
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            recommendations=[_rec("r1", "tnt_001", actual=None)],
        )
        assert snap.events_by_kind.get("recommendation") == 1
        assert snap.events_by_kind.get("outcome", 0) == 0


class TestTenantIsolation:
    """الخطّ الأحمر — لا تسريب بين tenants."""

    def test_other_tenant_filtered_from_activities(self):
        # CRITICAL: نشاط في tenant آخر لا يظهر
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            activities=[
                _FakeActivity("tnt_001", "fld_03"),
                _FakeActivity("tnt_OTHER", "fld_03"),  # tenant آخر
            ],
        )
        assert snap.events_by_kind.get("activity") == 1
        assert all(e.tenant_id == "tnt_001" for e in snap.timeline)

    def test_other_tenant_filtered_from_observations(self):
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            observations=[
                _FakeObs("tnt_001", "fld_03"),
                _FakeObs("tnt_OTHER", "fld_03"),
            ],
        )
        assert all(e.tenant_id == "tnt_001" for e in snap.timeline)

    def test_other_tenant_filtered_from_recommendations(self):
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            recommendations=[
                _rec("r1", "tnt_001"),
                _rec("r2", "tnt_OTHER"),
            ],
        )
        # توصية tenant آخر يجب أن تختفي
        rec_ids = [e.event_id for e in snap.timeline if e.kind == EventKind.RECOMMENDATION]
        assert "r1" in rec_ids
        assert "r2" not in rec_ids


class TestOpenQuestions:
    """شفّافية: نُعلن ما لا نعرفه، لا نختلق."""

    def test_unfulfilled_recommendations_flagged(self):
        # 2 توصية، 1 نتيجة فقط → سؤال مفتوح
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            recommendations=[
                _rec("r1", "tnt_001", actual=3.4),  # مع نتيجة
                _rec("r2", "tnt_001", actual=None),  # بلا نتيجة
            ],
        )
        # CRITICAL: لا اختراع outcomes - نُعلن النقص
        assert any("لم تُسجَّل نتائجها" in q for q in snap.open_questions)

    def test_no_observations_flagged(self):
        # CRITICAL: توصيات بلا قياسات = سؤال مفتوح
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            recommendations=[_rec("r1", "tnt_001", actual=3.4)],
        )
        assert any("لا مشاهدات" in q or "بلا دليل" in q for q in snap.open_questions)


class TestTimelineOrdering:
    """الأحداث مرتّبة زمنياً."""

    def test_events_sorted_chronologically(self):
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            activities=[
                _FakeActivity("tnt_001", "fld_03", planned="2025-06-01"),
                _FakeActivity("tnt_001", "fld_03", planned="2025-03-01"),
                _FakeActivity("tnt_001", "fld_03", planned="2025-04-01"),
            ],
        )
        dates = [e.occurred_at for e in snap.timeline]
        assert dates == sorted(dates)


class TestPeriodFilter:
    def test_period_from_filter(self):
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            activities=[
                _FakeActivity("tnt_001", "fld_03", planned="2024-12-01"),
                _FakeActivity("tnt_001", "fld_03", planned="2025-05-01"),
            ],
            period_from="2025-01-01",
        )
        # واحد فقط بعد 2025-01-01
        assert snap.total_events == 1


class TestFieldTimeline:
    def test_extracts_single_field_events(self):
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            activities=[
                _FakeActivity("tnt_001", "fld_03"),
                _FakeActivity("tnt_001", "fld_04"),
            ],
        )
        tl = field_timeline(snap, "fld_03")
        assert all(e.field_id == "fld_03" for e in tl)
        assert len(tl) == 1


class TestMemoryDensity:
    """تفسير شفّاف للكثافة، لا "AI score"."""

    def test_empty_is_empty(self):
        snap = build_farm_memory(tenant_id="t", farm_id="f")
        d = memory_density_report(snap)
        assert d["density"] == "empty"

    def test_recs_with_outcomes_medium(self):
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            recommendations=[_rec("r1", "tnt_001", actual=3.4)],
        )
        d = memory_density_report(snap)
        assert d["density"] == "medium"

    def test_three_plus_with_outcomes_high(self):
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            recommendations=[
                _rec("r1", "tnt_001", actual=3.4),
                _rec("r2", "tnt_001", actual=3.5),
                _rec("r3", "tnt_001", actual=3.3),
            ],
        )
        d = memory_density_report(snap)
        assert d["density"] == "high"

    def test_activities_only_is_low(self):
        # أنشطة فقط بدون outcomes = low (لا نعرف النتيجة)
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            activities=[_FakeActivity("tnt_001", "fld_03")],
        )
        d = memory_density_report(snap)
        assert d["density"] == "low"


class TestEventsAroundRecommendation:
    """forensic: ما حدث حول توصية معيّنة."""

    def test_returns_related_events(self):
        snap = build_farm_memory(
            tenant_id="tnt_001",
            farm_id="frm_01",
            activities=[
                _FakeActivity("tnt_001", "fld_03", planned="2025-03-15"),
                _FakeActivity("tnt_001", "fld_03", planned="2025-04-15"),
            ],
            recommendations=[_rec("r1", "tnt_001", issued="2025-03-20", actual=3.4)],
        )
        around = events_around_recommendation(snap, "r1", days_before=10, days_after=60)
        # توصية + نشاط 03-15 + نشاط 04-15 + outcome
        assert len(around) >= 3

    def test_unknown_rec_returns_empty(self):
        snap = build_farm_memory(tenant_id="t", farm_id="f")
        result = events_around_recommendation(snap, "nonexistent")
        assert result == []
