"""اختبار نقطة توصية الريّ المُثراة من حالة الحقل (WS-D.2) — الوصل + fail-closed.

يتحقّق أنّ النقطة تقرأ الاستنزاف/TAW آليّاً وتمرّرهما لبوّابة الاتّساق ثمّ للمنتِج:
  • حالة متّسقة طازجة ⇒ recommendation_ready + should_irrigate + ownership candidate.
  • Dr مفقود ⇒ insufficient_data، recommendation=None (مفقود ≠ صفر).
  • Dr > TAW ⇒ inconsistent_state، recommendation=None (لا قصّ صامت).
لا قاعدة بيانات: نُحقن اتّصالاً وهميّاً + سياق حقل عبر monkeypatch.
"""

from __future__ import annotations

import contextlib
from datetime import date

import api.routers.irrigation_recommendation as mod
import pytest
from api.routers.irrigation_recommendation import (
    FieldIrrigationRequest,
    field_irrigation_recommendation,
)


class _FakeConn:
    def __init__(self, *, depletion_mm, age_hours=5.0, confidence=0.9):
        self._depletion = depletion_mm
        self._age = age_hours
        self._conf = confidence

    async def fetchrow(self, sql, *a):
        if "FROM seasons" in sql:
            return {"season_id": "season_2026"}
        if "FROM water_ledger" in sql:
            if self._depletion is None:
                return None
            return {
                "depletion_mm": self._depletion,
                "confidence": self._conf,
                "soil_moisture_pct": None,
                "ledger_date": date(2026, 7, 9),
                "age_hours": self._age,
            }
        return None


def _fake_et0_product(**over):
    base = {
        "product": "et0",
        "et0_mm": 5.1,
        "method": "hargreaves_fallback",
        "quality_status": "degraded",
        "formula_version": "et0/fao56-pm/1.0.0",
        "unit": "mm/day",
        "valid_time": None,
        "weather_snapshot_id": "wsnap/sha1/1:deadbeefcafef00d",
    }
    base.update(over)
    return base


def _patch(monkeypatch, conn, *, engine=None, engine_raises=None):
    @contextlib.asynccontextmanager
    async def _tc(_user):
        yield conn

    async def _ctx(_conn, _field_id):
        return (16.0, 44.9, "wheat", "mid", 40)

    async def _engine(**_kw):
        if engine_raises is not None:
            raise engine_raises
        return engine if engine is not None else _fake_et0_product()

    monkeypatch.setattr(mod, "tenant_connection", _tc)
    monkeypatch.setattr(mod, "_field_weather_context", _ctx)
    # كلّ ET0 من المحرّك — نُثبِّت نقطة الوصل (لا شبكة) لنُثبِت أنّ المسار يستهلكها.
    monkeypatch.setattr(mod, "_engine_et0", _engine)


_REQ = FieldIrrigationRequest(t_min_c=18.0, t_max_c=34.0, policy="water_saving")


@pytest.mark.asyncio
async def test_ready_produces_candidate(monkeypatch):
    # Dr=60, TAW من الافتراضيّ (~؟) — نتحقّق من البنية لا القيمة الدقيقة.
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    assert out["status"] == "recommendation_ready"
    assert out["field_id"] == "fld_1"
    assert out["season_id"] == "season_2026"
    assert out["ownership"] == "recommendation_candidate → decision-service"
    assert "should_irrigate" in out["recommendation"]
    assert out["calibrated"] is False
    assert any(e.startswith("water-ledger:") for e in out["evidence_ids"])


@pytest.mark.asyncio
async def test_et0_provenance_from_weather_engine(monkeypatch):
    # نَسَب ET0 يأتي من المحرّك: method/quality/formula_version/snapshot + مصدر صريح.
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    et0 = out["et0"]
    assert et0["source"] == "weather-engine"
    assert et0["method"] == "hargreaves_fallback"
    assert et0["formula_version"] == "et0/fao56-pm/1.0.0"
    assert et0["weather_snapshot_id"] == "wsnap/sha1/1:deadbeefcafef00d"
    # نَسَب المحرّك في أدلّة القرار.
    assert any(e.startswith("weather-engine-et0:") for e in out["evidence_ids"])
    # مقارنة ظلّيّة مؤقّتة موجودة (الإرث لا يدخل القرار).
    assert "shadow" in et0
    assert et0["shadow"]["diff_mm"] is not None


@pytest.mark.asyncio
async def test_engine_down_fails_closed_no_local_et0(monkeypatch):
    # تعذّر المحرّك ⇒ dependency_unavailable، لا توصية، لا حساب ET0 محلّيّ بديل.
    from fastapi import HTTPException

    _patch(
        monkeypatch,
        _FakeConn(depletion_mm=60.0),
        engine_raises=HTTPException(status_code=502, detail="weather-service down"),
    )
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    assert out["status"] == "dependency_unavailable"
    assert out["recommendation"] is None
    assert any("fail-closed" in lim for lim in out["limitations"])


@pytest.mark.asyncio
async def test_shadow_diff_is_near_zero_faithful_reproduction(monkeypatch):
    # المحرّك (المُثبَّت) يُعيد قيمة الإرث نفسها ⇒ diff = 0 (إثبات أمانة إعادة الإنتاج).
    # نحسب الإرث فعليّاً لنُطابق قيمة المحرّك المُثبَّتة معه.
    from api.water_balance import WeatherInput, compute_et0

    legacy_mm, _ = compute_et0(
        WeatherInput(
            t_min_c=18.0, t_max_c=34.0, latitude_deg=16.0, elevation_m=2000.0, day_of_year=100
        )
    )
    _patch(
        monkeypatch,
        _FakeConn(depletion_mm=60.0),
        engine=_fake_et0_product(et0_mm=round(legacy_mm, 3), method="fao56_penman_monteith"),
    )
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    assert out["et0"]["shadow"]["diff_mm"] == 0.0


@pytest.mark.asyncio
async def test_missing_depletion_is_insufficient(monkeypatch):
    _patch(monkeypatch, _FakeConn(depletion_mm=None))
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    assert out["status"] == "insufficient_data"
    assert out["recommendation"] is None
    assert "missing_depletion_mm" in out["limitations"]


@pytest.mark.asyncio
async def test_depletion_exceeds_taw_is_inconsistent(monkeypatch):
    # Dr ضخم يتجاوز أيّ TAW معقول ⇒ inconsistent_state، لا توصية، لا قصّ.
    _patch(monkeypatch, _FakeConn(depletion_mm=9999.0))
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    assert out["status"] == "inconsistent_state"
    assert out["recommendation"] is None
    assert "depletion_exceeds_taw" in out["limitations"]
