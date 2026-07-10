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


def _patch(monkeypatch, conn):
    @contextlib.asynccontextmanager
    async def _tc(_user):
        yield conn

    async def _ctx(_conn, _field_id):
        return (16.0, 44.9, "wheat", "mid", 40)

    monkeypatch.setattr(mod, "tenant_connection", _tc)
    monkeypatch.setattr(mod, "_field_weather_context", _ctx)


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
