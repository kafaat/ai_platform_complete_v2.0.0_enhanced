"""S4 — نَسَب الموسم المكانيّ: هويّة الأصل في صفوف NDVI وبصمتها، وتحذير تغيّر حدّ الحقل.

S4-a: محوِّل نقطة ``/timeseries`` كان يُسقط ``scene_id`` (ولا يحمل مراجعة الهندسة ولا
الأصل المقروء)، فنقطتان بالأرقام نفسها من مشهدين/أصلين مختلفين تُعطيان صفّاً واحداً
و``input_digest`` واحداً — البصمة لا تُميّز ما قيس عليه.

S4-b: المواسم مربوطة بـ``field_id`` والتواريخ فقط (لا مراجعة هندسة ولا مساحة تاريخيّة —
قرار مخطّط معلّق). بلا ترحيل: المحاكاة تُعلِن صراحةً حين عُدِّل حدّ الحقل بعد بداية
الموسم، لأنّها تقرأ إحداثيّات الحقل وسلسلته على الحدّ **الحاليّ**.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api import raster_service_client as rsc
from core.canonical_schemas import UserRole, UserSchema
from core.historical_season_context import compose_historical_season_context

pytestmark = pytest.mark.unit

_TENANT = "00000000-0000-0000-0000-0000000000a4"
_USER = UserSchema(user_id="u-s4", tenant_id=_TENANT, role=UserRole.OWNER, name_ar="مزارع")


def _point(**over):
    point = {
        "datetime": "2025-01-10",
        "mean": 0.5,
        "cloud_pct": 10.0,
        "valid_pixel_ratio": 0.9,
        "coverage_ratio": 0.9,
        "scene_id": "S2A_T38PNA_20250110",
        "geometry_revision": 1,
        "source_uri": "s3://rasters/field-a/ndvi/r1.tif",
    }
    point.update(over)
    return point


# ── S4-a: المحوِّل والبصمة ──────────────────────────────────────────────────────────


def test_vegetation_row_carries_scene_and_asset_identity():
    row = rsc.timeseries_point_to_vegetation_row(_point(), field_id="field-a")
    assert row["scene_id"] == "S2A_T38PNA_20250110"
    assert row["geometry_revision"] == 1
    assert row["source_uri"] == "s3://rasters/field-a/ndvi/r1.tif"


def test_absent_identity_stays_none_not_fabricated():
    row = rsc.timeseries_point_to_vegetation_row(
        {"datetime": "2025-01-10", "mean": 0.5}, field_id="field-a"
    )
    assert row["scene_id"] is None
    assert row["geometry_revision"] is None
    assert row["source_uri"] is None


@pytest.mark.parametrize(
    "changed",
    [
        {"scene_id": "S2B_T38PNA_20250110"},
        {"geometry_revision": 2},
        {"source_uri": "s3://rasters/field-a/ndvi/r2.tif"},
    ],
)
def test_input_digest_distinguishes_source_identity_with_identical_numbers(changed):
    def digest(point):
        row = rsc.timeseries_point_to_vegetation_row(point, field_id="field-a")
        return compose_historical_season_context(
            tenant_id=_TENANT,
            field_id="field-a",
            season_id="season-a",
            season={"season_id": "season-a", "sowing_date": date(2025, 1, 1)},
            vegetation=[row],
        )

    a, b = digest(_point()), digest(_point(**changed))
    # الرقم نفسه يُشتقّ منه fAPAR نفسه — والبصمة وحدها تُميّز الأصل.
    assert a["simulation_inputs"] == b["simulation_inputs"]
    assert a["input_digest"] != b["input_digest"]


# ── المسار: /api/v1/seasons/{id}/simulate بحدود الشبكة/القاعدة وحدها ─────────────────


@dataclass
class _Day:
    date: str = ""
    temp_min_c: float = 15.0
    temp_max_c: float = 30.0
    et0_mm: float = 5.0
    precipitation_mm: float = 0.0


class _Conn:
    def __init__(self, season_row, geometry_rows, *, geometry_error=False, candidates=()):
        self.season_row = season_row
        self.geometry_rows = geometry_rows
        self.geometry_error = geometry_error
        self.candidates = list(candidates)
        self.runs: list[tuple] = []
        self.executed: list[str] = []

    @contextlib.asynccontextmanager
    async def transaction(self):
        yield self

    async def fetchrow(self, sql, *args):
        if "FROM seasons s JOIN fields f" in sql:
            return self.season_row
        return None  # لا سجلّ يدويّ مرتبط

    async def fetch(self, sql, *args):
        if "field_geometry_history" in sql:
            if self.geometry_error:
                raise RuntimeError("relation field_geometry_history does not exist")
            return self.geometry_rows
        if "FROM season_records sr" in sql:
            return self.candidates
        return []

    async def fetchval(self, sql, *args):
        assert "INSERT INTO season_simulation_runs" in sql
        self.runs.append(args)
        return uuid.uuid4()

    async def execute(self, sql, *args):
        self.executed.append(sql)
        return "OK"


def _install(monkeypatch, conn, points):
    import api.connectors.openmeteo as openmeteo
    import api.routers.seasons as route
    import api.weather_service_client as wsc

    monkeypatch.delenv("HISTORICAL_SEASON_DECISION_CONTEXT_ENABLED", raising=False)

    @contextlib.asynccontextmanager
    async def _tenant_connection(_user):
        yield conn

    async def _historical(lat, lon, start, end, timeout_s=30.0):
        n = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        return [_Day(date=(date.fromisoformat(start) + timedelta(days=i)).isoformat()) for i in range(n)]

    async def _et0(*, daily_t_min, **_kw):
        return {"daily_et0_mm": [5.0] * len(daily_t_min), "formula_version": "t"}

    async def _gdd(*, daily_t_min, **_kw):
        return {"daily_gdd": [12.0] * len(daily_t_min), "calculation_version": "t"}

    async def _timeseries(field_id, *, tenant_id=None, index="ndvi", **_kw):
        return points

    monkeypatch.setattr(route, "tenant_connection", _tenant_connection)
    # The route reads "today" from its own clock; the fixtures below are built from _TODAY,
    # fixed once at import. A run that crosses midnight UTC between collection and the call
    # saw one more day (window_days_requested 302 != 301, PR #1318, run 43123678786).
    monkeypatch.setattr(route, "datetime", _ClockOnFixtureDay)
    monkeypatch.setattr(openmeteo, "fetch_historical", _historical)
    monkeypatch.setattr(wsc, "get_et0_series", _et0)
    monkeypatch.setattr(wsc, "get_gdd_product", _gdd)
    monkeypatch.setattr(rsc, "get_field_timeseries", _timeseries)
    return route


def _season(sow: date, end: date) -> dict:
    return {
        "season_id": "season-a",
        "field_id": "field-a",
        "crops": ["wheat"],
        "sowing_date": sow,
        "season_end": end,
        "lat": 15.3,
        "lon": 44.2,
    }


def _rev(revision: int, at: date) -> dict:
    return {"revision": revision, "changed_at": datetime.combine(at, datetime.min.time(), UTC)}


_TODAY = datetime.now(UTC).date()


class _ClockOnFixtureDay(datetime):
    """The real clock, kept on the fixtures' calendar day (_TODAY)."""

    @classmethod
    def now(cls, tz=None):
        real = datetime.now(tz)
        return real.replace(year=_TODAY.year, month=_TODAY.month, day=_TODAY.day)


_SOW = _TODAY - timedelta(days=90)
_END = _TODAY - timedelta(days=20)


async def _simulate(monkeypatch, geometry_rows, points=(), **conn_kw):
    conn = _Conn(_season(_SOW, _END), geometry_rows, **conn_kw)
    route = _install(monkeypatch, conn, list(points))
    out = await route.simulate_season_endpoint("season-a", user=_USER)
    (run,) = conn.runs
    return out, run


def _geometry_warnings(warnings):
    return [w for w in warnings if "حدّ الحقل" in w]


async def test_simulation_warns_when_field_boundary_changed_after_season_start(monkeypatch):
    out, run = await _simulate(
        monkeypatch,
        [_rev(1, _SOW - timedelta(days=30)), _rev(2, _SOW + timedelta(days=5))],
    )
    (warning,) = _geometry_warnings(out.warnings_ar)
    assert "2" in warning
    # التحذير جزءٌ من سجلّ التشغيل المُلحَق لا الاستجابة وحدها.
    assert warning in json.loads(run[-1])


async def test_no_warning_when_boundary_only_recorded_at_creation_or_before_start(monkeypatch):
    # المراجعة الأولى = رسم الحقل (لا «تعديل»)، ولو سُجِّلت بعد بدء موسمٍ مُدخَل لاحقاً؛
    # وتعديلٌ قبل البداية لا يمسّ حدّ الموسم.
    out, run = await _simulate(
        monkeypatch,
        [_rev(1, _SOW - timedelta(days=30)), _rev(2, _SOW - timedelta(days=3))],
    )
    assert _geometry_warnings(out.warnings_ar) == []
    out, run = await _simulate(monkeypatch, [_rev(1, _SOW + timedelta(days=10))])
    assert _geometry_warnings(out.warnings_ar) == []


async def test_geometry_lookup_failure_does_not_break_the_simulation(monkeypatch):
    out, run = await _simulate(monkeypatch, [], geometry_error=True)
    assert out.simulation_run_id
    assert _geometry_warnings(out.warnings_ar) == []


async def test_persisted_context_carries_scene_identity_and_digest_tracks_it(monkeypatch):
    day = (_SOW + timedelta(days=10)).isoformat()
    a, run_a = await _simulate(monkeypatch, [], points=[_point(datetime=day)])
    b, _ = await _simulate(
        monkeypatch, [], points=[_point(datetime=day, scene_id="S2B_T38PNA_other")]
    )
    snapshot = json.loads(run_a[6])
    (obs,) = snapshot["vegetation"]["observations"]
    assert obs["scene_id"] == "S2A_T38PNA_20250110"
    assert obs["source_uri"] == "s3://rasters/field-a/ndvi/r1.tif"
    assert a.yield_kg_ha == b.yield_kg_ha
    assert a.input_digest != b.input_digest


# ── النافذة والمحصول والهندسة في استجابة المسار ─────────────────────────────────────


async def _simulate_season(monkeypatch, season, **conn_kw):
    conn = _Conn(season, [], **conn_kw)
    route = _install(monkeypatch, conn, [])
    out = await route.simulate_season_endpoint("season-a", user=_USER)
    return out, conn


async def test_long_season_window_is_truncated_explicitly_not_silently(monkeypatch):
    sow = _TODAY - timedelta(days=300)
    out, conn = await _simulate_season(monkeypatch, {**_season(sow, None), "season_end": None})
    assert out.truncated is True
    assert out.window_days_requested == 301
    assert out.window_days_simulated == 161
    assert out.days_simulated == 161
    assert "SIM_WINDOW_TRUNCATED" in out.limitations
    (warning,) = [w for w in out.warnings_ar if "سقف المحاكاة" in w]
    assert warning in json.loads(conn.runs[0][-1])


async def test_response_declares_simulated_crop_and_current_geometry_basis(monkeypatch):
    out, _ = await _simulate_season(monkeypatch, {**_season(_SOW, _END), "crops": ["قمح", "شعير"]})
    assert out.simulated_crop == "قمح"
    assert out.geometry_basis == "current_boundary"
    assert out.truncated is False
    assert out.window_days_requested == out.window_days_simulated == 71
    assert any("حوكِيَ المحصول" in w for w in out.warnings_ar)  # التحذير المختلط باقٍ


async def test_season_without_sowing_date_is_refused_with_arabic_422(monkeypatch):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await _simulate_season(monkeypatch, {**_season(_SOW, _END), "sowing_date": None})
    assert exc.value.status_code == 422
    assert "تاريخ بذار" in exc.value.detail


def _record(crop_ref):
    return {
        "id": uuid.UUID(int=7),
        "tenant_id": _TENANT,
        "field_id": "field-a",
        "trust_status": "accepted",
        "link_crop_registry_ref": crop_ref,
        "link_variety_name": None,
    }


async def test_historical_record_of_another_crop_is_not_auto_linked(monkeypatch):
    out, conn = await _simulate_season(
        monkeypatch, _season(_SOW, _END), candidates=[_record("barley")]
    )
    assert not any("season_record_links" in sql for sql in conn.executed)
    assert out.historical_context_used is False


async def test_historical_record_of_the_same_crop_is_auto_linked(monkeypatch):
    out, conn = await _simulate_season(
        monkeypatch, _season(_SOW, _END), candidates=[_record("wheat")]
    )
    assert any("INSERT INTO season_record_links" in sql for sql in conn.executed)
    assert out.historical_context_used is True


async def test_multicrop_season_rejected_before_any_simulation_write(monkeypatch):
    from fastapi import HTTPException

    season = {**_season(_SOW, _END), "crops": ["wheat", "peanut"]}
    conn = _Conn(season, [])
    route = _install(monkeypatch, conn, [])
    with pytest.raises(HTTPException) as exc:
        await route.simulate_season_endpoint("season-a", user=_USER)
    assert exc.value.status_code == 422
    assert "متعدد المحاصيل" in str(exc.value.detail)
    assert not conn.runs


async def test_missing_archive_day_rejected_before_any_simulation_write(monkeypatch):
    from fastapi import HTTPException

    import api.connectors.openmeteo as openmeteo

    conn = _Conn(_season(_SOW, _END), [])
    route = _install(monkeypatch, conn, [])

    async def incomplete(lat, lon, start, end, timeout_s=30.0):
        n = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        return [
            _Day(date=(date.fromisoformat(start) + timedelta(days=i)).isoformat())
            for i in range(n - 1)
        ]

    monkeypatch.setattr(openmeteo, "fetch_historical", incomplete)
    with pytest.raises(HTTPException) as exc:
        await route.simulate_season_endpoint("season-a", user=_USER)
    assert exc.value.status_code == 503
    assert "سلسلة الطقس" in str(exc.value.detail)
    assert not conn.runs
