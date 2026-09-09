"""عقد «مساحة عمل الموسم» (Season Workspace) — نموذج قراءة موحّد لرحلة الحقل.

النقطة ``GET /api/v1/fields/{id}/season-workspace`` تجمع ملفّ الحقل + الموسم + جاهزيّة
البيانات + الحالة الموحّدة + التوصيات + المهامّ + الأنشطة + الإجراءات التالية في حمولة
واحدة صادقة (الفجوات تُبلَّغ في ``gaps``). هذه الاختبارات تثبّت:
  • المنطق النقيّ للجاهزيّة (``_readiness``) ومستوياتها (insufficient/partial/ready).
  • تجميع/ترتيب الإجراءات التالية (``_next_actions``) مع السقف.
  • تعاقُد البنية: النقطة مُسجَّلة وتتطلّب صلاحيّة عرض الحقل (لا وصول مجهول).
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_CORE = os.path.join(os.path.dirname(__file__), "..", "services", "sahool-platform")


def _load_module():
    if _CORE not in sys.path:
        sys.path.insert(0, _CORE)
    import api.main  # noqa: F401 — resolve the application's router import cycle
    import api.routers.season_workspace as sw

    return sw


_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15.01], [44, 15]]],
}


def _complete_inputs():
    return {
        "field": {"geometry": _GEOMETRY, "lat": 15.3, "lon": 44.2, "crop": "wheat"},
        "season": {
            "season_id": "s1",
            "status": "active",
            "sowing_date": (date.today() - timedelta(days=30)).isoformat(),
            "season_end": (date.today() + timedelta(days=30)).isoformat(),
            "target_yield_kg_ha": 5000,
        },
        "soil_tests": [
            {
                "status": "published",
                "result": {
                    "ec_ds_m": 2.1,
                    "water_ec_ds_m": 1.3,
                    "ph": 7.2,
                    "n_ppm": 20,
                    "p_ppm": 10,
                    "k_ppm": 180,
                },
            }
        ],
        "state": {"validity": "valid", "execution_mode": "auto", "soil_age_days": 1},
    }


def test_readiness_insufficient_when_empty():
    """حقل بلا حدود/موقع/محصول/موسم/EC/حالة ⇒ نقص حادّ (insufficient)."""
    sw = _load_module()
    r = sw._readiness(field={}, season=None, soil_tests=[], state=None)
    assert r["level"] == "insufficient"
    assert r["score"] < 60
    # فحص EC التربة إلزاميّ وغير محقَّق (المفتاح soil_ec).
    assert any(c["key"] == "soil_ec" and not c["ok"] for c in r["checks"])
    assert r["missing"], "يجب أن تُذكَر العناصر الناقصة"


def test_readiness_ready_when_complete():
    """كلّ الإلزاميّ (حدود/موقع/محصول/موسم/زراعة/EC/حالة) + اختياريّ ⇒ جاهز (ready)."""
    sw = _load_module()
    r = sw._readiness(**_complete_inputs())
    assert r["level"] == "ready", r
    assert r["score"] >= 85
    assert r["data_complete"] and r["operational_ready"]


@pytest.mark.parametrize(
    "validity,mode",
    [
        ("invalid", "auto"),
        ("degraded", "auto"),
        ("conflicted", "blocked"),
        ("insufficient", "blocked"),
        ("valid", "human_review"),
        ("valid", None),
    ],
)
def test_complete_data_does_not_override_canonical_restriction(validity, mode):
    sw = _load_module()
    values = _complete_inputs()
    values["state"] = {"validity": validity, "execution_mode": mode}
    result = sw._readiness(**values)
    assert result["data_complete"]
    assert not result["operational_ready"]
    assert result["level"] != "ready"
    assert result["quality_grade"] != "READY"


@pytest.mark.parametrize("status", ["draft", "submitted", "approved", "rejected"])
def test_unpublished_lab_cannot_supply_accepted_soil(status):
    sw = _load_module()
    values = _complete_inputs()
    values["soil_tests"][0]["status"] = status
    # Profile numbers are not proof of a published lab result either.
    values["field"].update(soil_ph=7.2, soil_ec=2.1, water_ec=1.3)
    result = sw._readiness(**values)
    assert not result["data_complete"]
    assert result["level"] != "ready"
    assert sw._latest_published_soil(values["soil_tests"]) is None


@pytest.mark.parametrize(
    "change",
    [
        {"status": "closed"},
        {"status": "planned"},
        {"sowing_date": "9999-01-01"},
        {"season_end": "2000-01-01"},
        {"sowing_date": "invalid"},
    ],
)
def test_inactive_or_out_of_date_season_is_not_ready(change):
    sw = _load_module()
    values = _complete_inputs()
    values["season"].update(change)
    result = sw._readiness(**values)
    assert not result["operational_ready"]
    assert result["level"] != "ready"


@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf")])
def test_required_ec_must_be_a_finite_accepted_number(value):
    sw = _load_module()
    values = _complete_inputs()
    values["soil_tests"][0]["result"]["ec_ds_m"] = value
    result = sw._readiness(**values)
    assert not result["operational_ready"]
    assert result["level"] != "ready", "optional points cannot compensate for missing required EC"


def test_zero_ec_and_coordinates_are_present_measurements():
    sw = _load_module()
    values = _complete_inputs()
    values["soil_tests"][0]["result"].update(ec_ds_m=0, water_ec_ds_m=0)
    values["field"].update(lat=0, lon=0)
    assert sw._readiness(**values)["level"] == "ready"


def _field_row(state=None):
    return {
        "field_id": "f1",
        "farm_id": "farm1",
        "name": "الحقل",
        "crop": "wheat",
        "area_ha": 10,
        "soil_type": None,
        "manager": None,
        "lat": 15.3,
        "lon": 44.2,
        "geometry": _GEOMETRY,
        "quality_state": state,
    }


@pytest.mark.parametrize(
    "state,expected",
    [
        (None, "LIMITED"),
        ({}, "LIMITED"),
        ("malformed", "LIMITED"),
        ({"validity": "valid", "execution_mode": "auto"}, "READY"),
        ('{"validity":"valid","execution_mode":"auto"}', "READY"),
        ({"validity": "valid", "execution_mode": "human_review"}, "LIMITED"),
        ({"validity": "invalid", "execution_mode": "auto"}, "BLOCKED"),
        ({"validity": "conflicted", "execution_mode": "blocked"}, "BLOCKED"),
        ({"validity": "insufficient", "inputs": {"soil_age_days": None}}, "PENDING_LAB"),
        ({"validity": "insufficient", "inputs": {"soil_age_days": 2}}, "LIMITED"),
        ({"validity": "insufficient", "soil_age_days": 2}, "LIMITED"),
    ],
)
def test_list_and_detail_share_canonical_quality(state, expected):
    _load_module()
    from api.field_models import _row_to_field_detail, _row_to_field_summary

    assert _row_to_field_summary(_field_row(state)).quality_grade == expected
    assert _row_to_field_detail(_field_row(state)).quality_grade == expected


class _TransactionConn:
    """Model PostgreSQL's aborted transaction until rollback to a savepoint.

    This is an injected failure unit test, not a live PostgreSQL certification.
    """

    def __init__(self):
        self.aborted = False
        self.rollbacks = 0
        self.sql = []

    @asynccontextmanager
    async def transaction(self):
        was_aborted = self.aborted
        try:
            yield self
            assert not self.aborted, "aborted transaction cannot commit"
        except Exception:
            self.aborted = was_aborted
            self.rollbacks += 1
            raise

    async def execute(self, sql, *args):
        assert not self.aborted, "current transaction is aborted"
        self.sql.append(sql)

    async def fetchrow(self, sql, *args):
        await self.execute(sql, *args)
        return None if "FROM seasons" in sql else _field_row()

    async def fetch(self, sql, *args):
        await self.execute(sql, *args)
        return []


@pytest.mark.parametrize("failed", [False, True])
async def test_create_quality_and_projection_savepoint(monkeypatch, failed):
    _load_module()
    import api.field_state_projection as projection
    import api.routers.fields as fields
    from api.field_models import _row_to_field_summary

    conn = _TransactionConn()
    state = {
        "validity": "insufficient",
        "execution_mode": "human_review",
        "inputs": {"soil_age_days": None},
    }

    async def recompute(conn, field_id):
        if failed:
            conn.aborted = True
            raise RuntimeError("injected SQL failure")
        return {"state": state, "changed": False}

    async def noop(*args, **kwargs):
        return 1

    monkeypatch.setattr(projection, "recompute_field_state", recompute)
    for name in ("_emit_domain_event", "save_field_geometry_revision", "mark_raster_cache_stale"):
        monkeypatch.setattr(fields, name, noop)
    result = await fields._insert_field_within_tx(
        conn,
        SimpleNamespace(tenant_id="tenant1", user_id=1),
        field_id="f1",
        name="الحقل",
        crop="wheat",
        geometry=_GEOMETRY,
        area_ha=10,
        lat=15.3,
        lon=44.2,
    )
    await conn.execute("SELECT 1")  # the enclosing mutation can still finish
    assert conn.rollbacks == int(failed)
    assert result["quality_grade"] == ("LIMITED" if failed else "PENDING_LAB")
    assert (
        result["quality_grade"]
        == _row_to_field_summary(_field_row(None if failed else state)).quality_grade
    )


@pytest.mark.parametrize("failure", ["field_state", "recommendation_context", None])
async def test_workspace_projection_failure_does_not_poison_context_query(monkeypatch, failure):
    sw = _load_module()
    import api.field_state_projection as projection

    conn = _TransactionConn()

    @asynccontextmanager
    async def tenant_connection(user):
        async with conn.transaction():
            yield conn

    async def assert_field(*args):
        return None

    async def recompute(conn, field_id):
        if failure == "field_state":
            conn.aborted = True
            raise RuntimeError("injected SQL failure")
        return {"state": _complete_inputs()["state"], "changed": False}

    async def context(conn, field_id):
        await conn.execute("SELECT context_after_projection_failure")
        if failure == "recommendation_context":
            conn.aborted = True
            raise RuntimeError("injected context SQL failure")
        return None, None, "wheat", None, None

    async def policy(conn):
        return []

    monkeypatch.setattr(sw, "tenant_connection", tenant_connection)
    monkeypatch.setattr(sw, "_assert_field_in_tenant", assert_field)
    monkeypatch.setattr(sw, "_field_season_context", context)
    monkeypatch.setattr(sw, "_load_recommendation_policy", policy)
    monkeypatch.setattr(projection, "recompute_field_state", recompute)
    result = await sw.season_workspace("f1", SimpleNamespace(tenant_id="tenant1"))
    assert (result["canonical_state"] is None) == (failure == "field_state")
    assert result["field"]["quality_grade"] == ("LIMITED" if failure == "field_state" else "READY")
    assert result["active_season"] is None
    assert not result["readiness"]["operational_ready"]
    assert [g["source"] for g in result["gaps"]] == ([failure] if failure else [])
    assert result["recommendations"]["requires_review"], "no active season/soil evidence"
    assert "SELECT context_after_projection_failure" in conn.sql
    assert conn.rollbacks == int(failure is not None)
    season_query = next(q for q in conn.sql if "FROM seasons" in q)
    assert "status = 'active'" in season_query
    assert "sowing_date <= CURRENT_DATE" in season_query
    assert "season_end >= CURRENT_DATE" in season_query


def test_readiness_score_monotonic_with_data():
    """إضافة بيانات لا تُنقص النقاط (اتّساق التهديف)."""
    sw = _load_module()
    empty = sw._readiness(field={}, season=None, soil_tests=[], state=None)["score"]
    partial = sw._readiness(
        field={}, season={"season_id": "s"}, soil_tests=[{"ec_ds_m": 2.0}], state=None
    )["score"]
    assert partial >= empty


def test_next_actions_prioritizes_and_caps():
    """الإجراءات تُرتَّب بالأولويّة (1 أوّلاً) وتُحَدّ بسقف 8."""
    sw = _load_module()
    readiness = {
        "missing": [
            {"key": "ec", "label_ar": "EC", "action_ar": "أضف EC", "required": True},
            {"key": "npk", "label_ar": "N/P/K", "action_ar": "أضف", "required": False},
        ]
    }
    recs = {"recommendations": [{"priority": 1, "title_ar": "ريّ"}], "requires_review": True}
    tasks = [{"task_id": f"t{i}", "priority": 2, "notes": "مهمة"} for i in range(10)]
    actions = sw._next_actions(readiness, recs, tasks)
    assert len(actions) <= 8
    prios = [a["priority"] for a in actions]
    assert prios == sorted(prios), "غير مرتّبة بالأولويّة"
    # فجوة بيانات إلزاميّة (priority 1) تتصدّر.
    assert actions[0]["type"] in {"data_gap", "recommendation"}


def test_next_actions_empty_inputs():
    """مدخلات فارغة ⇒ قائمة فارغة (لا تلفيق إجراءات)."""
    sw = _load_module()
    assert sw._next_actions({"missing": []}, None, []) == []


def test_next_actions_accepts_real_recommendation_priority_vocabulary():
    sw = _load_module()
    from api.recommendations_hub import RecommendationContext, build_recommendations

    recs = [
        r.to_dict()
        for r in build_recommendations(RecommendationContext(field_id="f1", crop="wheat"))
    ]
    assert any(r["priority"] == "high" for r in recs), "exercise the actual producer contract"
    actions = sw._next_actions({"missing": []}, {"recommendations": recs}, [])
    assert actions
    assert all(isinstance(a["priority"], int) for a in actions)
    assert [a["priority"] for a in actions] == sorted(a["priority"] for a in actions)


def test_endpoint_registered_and_requires_field_view():
    """تعاقُد البنية: النقطة مُعرَّفة على راوتر الوحدة (تُكتشَف تلقائيّاً عبر iter_modules)
    وتتطلّب صلاحيّة FIELD_VIEW (لا وصول مجهول)."""
    sw = _load_module()

    # راوتر الوحدة هو مصدر الحقيقة للمسار (register_routers يضمّ أيّ وحدة تحمل `router`)؛
    # فحصه حتميّ بصرف النظر عن ترتيب استيراد api.main في جلسة pytest.
    paths = {getattr(r, "path", None) for r in sw.router.routes}
    assert "/api/v1/fields/{field_id}/season-workspace" in paths, "النقطة غير مُعرَّفة على الراوتر"
    methods = {
        meth
        for r in sw.router.routes
        if getattr(r, "path", None) == "/api/v1/fields/{field_id}/season-workspace"
        for meth in (getattr(r, "methods", set()) or set())
    }
    assert "GET" in methods
    # المصدر يفرض صلاحيّة العرض عبر require_permission(FIELD_VIEW) — لا اعتماد على عميل.
    src = open(
        os.path.join(_CORE, "api", "routers", "season_workspace.py"), encoding="utf-8"
    ).read()
    assert "require_permission(Permission.FIELD_VIEW)" in src
    assert "tenant_connection(user)" in src  # عزل RLS


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
