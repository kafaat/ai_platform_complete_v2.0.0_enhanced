"""اختبارات وحدة لتحليل الغلّة — التجميع النقيّ + المعالِج (اتّصال مُحاكى).

قسمان: (أ) ``api.yield_analysis`` منطق صرف (لا قاعدة) — صدق الفراغ/الجزئيّة،
تحويل kg/ha→t/ha، مقارنة الزراعة↔الحصاد، أداء الهجن (استبعاد بلا حصاد/بلا هجين)؛
(ب) المعالِج ``yield_analysis_endpoint`` مباشرةً باتّصال مُحاكى (best-effort) —
تشكيل صحيح + فشل اتّصال ⇒ 503. لا قاعدة حقيقيّة (المسار التكامليّ منفصل).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import api.main  # noqa: F401 — تهيئة api.main كاملةً قبل استيراد الموجِّه
import pytest
from api.routers.yield_analysis import yield_analysis_endpoint
from api.yield_analysis import (
    assemble_yield_analysis,
    build_hybrid_performance,
    build_planting_vs_harvest,
)
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-yield",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مُحلِّل الغلّة",
)


def _season(**kw):
    base = {
        "season_id": "ssn_1",
        "field_id": "fld_1",
        "field_name": "حقل القمح",
        "crops": ["wheat"],
        "cultivar": None,
        "seed_variety_source": None,
        "maturity": None,
        "sowing_date": date(2026, 1, 1),
        "season_end": None,
        "status": "closed",
        "target_yield_kg_ha": None,
        "actual_yield_kg_ha": None,
    }
    base.update(kw)
    return base


# ── (أ) التجميع النقيّ ──────────────────────────────────────────


class TestPlantingVsHarvest:
    def test_kg_ha_converted_to_t_ha(self):
        rows = [_season(actual_yield_kg_ha=4200, target_yield_kg_ha=5000)]
        out = build_planting_vs_harvest(rows)
        assert out[0]["actual_yield_t_ha"] == 4.2
        assert out[0]["target_yield_t_ha"] == 5.0
        assert out[0]["yield_gap_t_ha"] == -0.8  # فعليّ أقلّ من المستهدف
        assert out[0]["has_harvest"] is True
        assert out[0]["crop"] == "wheat"

    def test_missing_harvest_is_honest_none(self):
        out = build_planting_vs_harvest([_season()])  # بلا غلّة فعليّة
        assert out[0]["actual_yield_t_ha"] is None
        assert out[0]["yield_gap_t_ha"] is None  # لا فجوة بلا طرفين
        assert out[0]["has_harvest"] is False
        assert out[0]["sowing_date"] == "2026-01-01"  # date → ISO

    def test_hybrid_label_prefers_cultivar(self):
        out = build_planting_vs_harvest(
            [_season(cultivar="Pioneer-X", seed_variety_source="dealer-A")]
        )
        assert out[0]["hybrid"] == "Pioneer-X"


class TestHybridPerformance:
    def test_avg_per_hybrid_sorted_desc(self):
        rows = [
            _season(season_id="s1", field_id="f1", cultivar="A", actual_yield_kg_ha=6000),
            _season(season_id="s2", field_id="f2", cultivar="A", actual_yield_kg_ha=4000),
            _season(season_id="s3", field_id="f3", cultivar="B", actual_yield_kg_ha=7000),
        ]
        out = build_hybrid_performance(rows)
        assert [h["hybrid"] for h in out] == ["B", "A"]  # B (7) > A (avg 5)
        a = next(h for h in out if h["hybrid"] == "A")
        assert a["avg_yield_t_ha"] == 5.0
        assert a["min_yield_t_ha"] == 4.0
        assert a["max_yield_t_ha"] == 6.0
        assert a["season_count"] == 2
        assert a["field_count"] == 2

    def test_rows_without_harvest_or_hybrid_excluded(self):
        rows = [
            _season(cultivar="A"),  # بلا حصاد ⇒ مُستبعَد
            _season(cultivar=None, actual_yield_kg_ha=5000),  # بلا هجين ⇒ مُستبعَد
            _season(cultivar="B", actual_yield_kg_ha=5000),  # مكتمل ⇒ يدخل
        ]
        out = build_hybrid_performance(rows)
        assert [h["hybrid"] for h in out] == ["B"]


class TestAssembleHonesty:
    def test_empty_scope_has_note(self):
        out = assemble_yield_analysis([], field_id="fld_x", season=None)
        assert out["summary"]["seasons_total"] == 0
        assert out["planting_vs_harvest"] == []
        assert out["hybrid_performance"] == []
        assert out["provenance"]["note_ar"]  # رسالة فراغ صريحة
        assert out["provenance"]["honesty"] == "stored_only"
        assert out["scope"]["field_id"] == "fld_x"

    def test_seasons_but_no_harvest_has_note(self):
        out = assemble_yield_analysis([_season(cultivar="A")])
        assert out["summary"]["seasons_total"] == 1
        assert out["summary"]["seasons_with_harvest"] == 0
        assert out["hybrid_performance"] == []  # لا حصاد ⇒ لا أداء
        assert "actual_yield" in out["provenance"]["note_ar"]

    def test_full_data_no_note(self):
        out = assemble_yield_analysis([_season(cultivar="A", actual_yield_kg_ha=5000)])
        assert out["summary"]["seasons_with_harvest"] == 1
        assert out["summary"]["hybrids_compared"] == 1
        assert out["provenance"]["note_ar"] is None


# ── (ب) المعالِج (اتّصال مُحاكى) ────────────────────────────────


class _FakeConn:
    def __init__(self, rows=None, fail=False):
        self._rows = rows or []
        self._fail = fail

    async def fetch(self, sql, *args):
        if self._fail:
            raise RuntimeError("relation seasons does not exist")
        return self._rows


def _patch_conn(monkeypatch, conn=None, raise_open=False):
    @asynccontextmanager
    async def _fake_tenant_connection(user):
        if raise_open:
            raise RuntimeError("pool unavailable")
        yield conn

    monkeypatch.setattr("api.routers.yield_analysis.tenant_connection", _fake_tenant_connection)


async def test_endpoint_shapes_result(monkeypatch):
    rows = [
        _season(season_id="s1", field_id="f1", cultivar="A", actual_yield_kg_ha=6000),
        _season(season_id="s2", field_id="f2", cultivar="A", actual_yield_kg_ha=4000),
    ]
    _patch_conn(monkeypatch, conn=_FakeConn(rows=rows))
    out = await yield_analysis_endpoint(field_id=None, season=None, user=_USER)
    assert out["summary"]["seasons_total"] == 2
    assert out["summary"]["seasons_with_harvest"] == 2
    assert out["hybrid_performance"][0]["hybrid"] == "A"
    assert out["hybrid_performance"][0]["avg_yield_t_ha"] == 5.0
    assert out["tenant_id"] == "00000000-0000-0000-0000-000000000002"
    assert out["units"]["yield"] == "t/ha"


async def test_endpoint_empty_is_honest(monkeypatch):
    _patch_conn(monkeypatch, conn=_FakeConn(rows=[]))
    out = await yield_analysis_endpoint(field_id="fld_9", season=None, user=_USER)
    assert out["summary"]["seasons_total"] == 0
    assert out["provenance"]["note_ar"]
    assert out["scope"]["field_id"] == "fld_9"


async def test_endpoint_db_open_failure_returns_503(monkeypatch):
    _patch_conn(monkeypatch, raise_open=True)
    with pytest.raises(HTTPException) as e:
        await yield_analysis_endpoint(field_id=None, season=None, user=_USER)
    assert e.value.status_code == 503


async def test_endpoint_fetch_failure_returns_503(monkeypatch):
    _patch_conn(monkeypatch, conn=_FakeConn(fail=True))
    with pytest.raises(HTTPException) as e:
        await yield_analysis_endpoint(field_id=None, season=None, user=_USER)
    assert e.value.status_code == 503


def test_endpoint_registered_in_app():
    from api.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/v1/analysis/yield" in paths
