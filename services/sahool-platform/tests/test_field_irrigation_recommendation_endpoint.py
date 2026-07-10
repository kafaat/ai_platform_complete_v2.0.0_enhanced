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


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeConn:
    def __init__(
        self, *, depletion_mm, age_hours=5.0, confidence=0.9, soil_texture=None, spectral=None
    ):
        self._depletion = depletion_mm
        self._age = age_hours
        self._conf = confidence
        self._soil_texture = soil_texture
        self._spectral = spectral  # dict: ndmi/msi/ndmi_date/msi_date

    def transaction(self):
        return _Tx()

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
        if "FROM soil_lab_tests" in sql:
            if self._soil_texture is None:
                return None
            return {
                "sampled_on": date(2026, 5, 1),
                "result": {"texture": self._soil_texture},
                "age_days": 40.0,
            }
        if "FROM imagery_automation_fields" in sql:
            if self._spectral is None:
                return None
            return {
                "last_ndmi_mean": self._spectral.get("ndmi"),
                "last_msi_mean": self._spectral.get("msi"),
                "last_ndmi_date": self._spectral.get("ndmi_date"),
                "last_msi_date": self._spectral.get("msi_date"),
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
async def test_msi_reaches_irrigation_candidate(monkeypatch):
    # WS-D.3: NDMI+MSI بتاريخين متوافقين ⇒ التأكيد الطيفيّ يصل المرشَّح (لم يعد ميتاً).
    _patch(
        monkeypatch,
        _FakeConn(
            depletion_mm=60.0,
            spectral={
                "ndmi": 0.05,
                "msi": 1.6,
                "ndmi_date": date(2026, 7, 8),
                "msi_date": date(2026, 7, 8),
            },
        ),
    )
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    assert out["spectral_confirmation"]["available"] is True
    assert any(e.startswith("spectral-confirmation:ndmi+msi") for e in out["evidence_ids"])


@pytest.mark.asyncio
async def test_no_spectral_escalation_when_msi_missing(monkeypatch):
    # قرار المستخدم: غياب أحد الدليلين ⇒ لا تأكيد ولا تصعيد (صدق: NDMI وحده لا يكفي).
    _patch(
        monkeypatch,
        _FakeConn(
            depletion_mm=60.0,
            spectral={"ndmi": 0.05, "msi": None, "ndmi_date": date(2026, 7, 8), "msi_date": None},
        ),
    )
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    assert out["spectral_confirmation"]["available"] is False
    assert out["spectral_confirmation"]["escalation_eligible"] is False


@pytest.mark.asyncio
async def test_lab_texture_is_measured_provenance(monkeypatch):
    # فحص تربة معتمَد بنسيج ⇒ TAW من نسيج مقيس، لا fallback.
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0, soil_texture="sandy_loam"))
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    prov = out["inputs"]["soil_provenance"]
    assert prov["texture"]["source"] == "lab_measured"
    assert prov["texture"]["value"] == "sandy_loam"
    assert prov["taw"]["source"] == "modelled_from_lab_texture"
    assert any(e.startswith("soil-lab-texture:") for e in out["evidence_ids"])


@pytest.mark.asyncio
async def test_missing_lab_texture_fallback_lowers_confidence(monkeypatch):
    # لا فحص تربة ⇒ نسيج fallback عامّ ⇒ قيد مُعلَن + ثقة أخفض (لا اختلاق دقّة).
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0, soil_texture=None))
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    prov = out["inputs"]["soil_provenance"]
    assert prov["texture"]["source"] == "unavailable_fallback"
    assert prov["confidence_penalty"] >= 0.15
    assert any("not lab-measured" in lim for lim in out["limitations"])


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


_REQ_AUTO = FieldIrrigationRequest(policy="water_saving")  # لا حرارة ⇒ جلب تلقائيّ


@pytest.mark.asyncio
async def test_auto_fetch_weather_is_primary_path(monkeypatch):
    # بلا حرارة في الطلب ⇒ الطقس يُجلَب آليّاً من المحرّك (المسار الأساسيّ D.2c).
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))

    async def _snap(_lat, _lon):
        return {
            "t_min_c": 17.0,
            "t_max_c": 33.0,
            "wind_2m_ms": 2.0,
            "solar_rad_mj_m2": 22.0,
            "rh_mean_pct": None,
            "day_of_year": 191,
            "valid_time": "2026-07-10",
            "source": "weather-engine-forecast",
        }

    monkeypatch.setattr(mod, "_field_weather_snapshot", _snap)
    out = await field_irrigation_recommendation("fld_1", _REQ_AUTO, user=object())
    assert out["status"] == "recommendation_ready"
    assert out["weather"]["source"] == "weather-engine-forecast"
    assert out["weather"]["valid_time"] == "2026-07-10"
    assert out["weather"]["day_of_year"] == 191


@pytest.mark.asyncio
async def test_manual_weather_is_flagged_override(monkeypatch):
    # تمرير حرارة يدويّاً ⇒ يُعلَن كتجاوز (ليس المسار الأساسيّ).
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    assert out["weather"]["source"] == "manual_override"
    assert any("manual weather override" in lim for lim in out["limitations"])


@pytest.mark.asyncio
async def test_weather_engine_down_fails_closed(monkeypatch):
    from fastapi import HTTPException

    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))

    async def _down(_lat, _lon):
        raise HTTPException(status_code=503, detail="forecast down")

    monkeypatch.setattr(mod, "_field_weather_snapshot", _down)
    out = await field_irrigation_recommendation("fld_1", _REQ_AUTO, user=object())
    assert out["status"] == "dependency_unavailable"
    assert out["recommendation"] is None
    assert any("fail-closed" in lim for lim in out["limitations"])


@pytest.mark.asyncio
async def test_default_is_not_submitted(monkeypatch):
    # لا submit ⇒ المرشَّح غير مُقدَّم (approval_state=not_submitted) — «اروِ» ليس نهائيّاً.
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))
    out = await field_irrigation_recommendation("fld_1", _REQ, user=object())
    assert out["approval_state"] == "not_submitted"
    assert out["decision_id"] is None


@pytest.mark.asyncio
async def test_submit_to_decision_is_pending_approval(monkeypatch):
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))

    async def _submit(payload, _tenant):
        assert payload["decision_type"] == "irrigation"
        assert payload["status"] == "pending_approval"
        return {"decision_id": "dec_123"}

    monkeypatch.setattr(mod, "_submit_candidate_to_decision", _submit)
    req = FieldIrrigationRequest(policy="water_saving", submit_to_decision=True)

    async def _snap(_lat, _lon):
        return {
            "t_min_c": 17.0,
            "t_max_c": 33.0,
            "wind_2m_ms": 2.0,
            "solar_rad_mj_m2": 22.0,
            "rh_mean_pct": None,
            "day_of_year": 191,
            "valid_time": "2026-07-10",
            "source": "weather-engine-forecast",
        }

    monkeypatch.setattr(mod, "_field_weather_snapshot", _snap)
    out = await field_irrigation_recommendation("fld_1", req, user=object())
    assert out["approval_state"] == "pending_approval"
    assert out["decision_id"] == "dec_123"


@pytest.mark.asyncio
async def test_submit_decision_service_down_is_flagged(monkeypatch):
    from fastapi import HTTPException

    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))

    async def _down(_payload, _tenant):
        raise HTTPException(status_code=502, detail="decision-service down")

    async def _snap(_lat, _lon):
        return {
            "t_min_c": 17.0,
            "t_max_c": 33.0,
            "wind_2m_ms": 2.0,
            "solar_rad_mj_m2": 22.0,
            "rh_mean_pct": None,
            "day_of_year": 191,
            "valid_time": "2026-07-10",
            "source": "weather-engine-forecast",
        }

    monkeypatch.setattr(mod, "_submit_candidate_to_decision", _down)
    monkeypatch.setattr(mod, "_field_weather_snapshot", _snap)
    req = FieldIrrigationRequest(policy="water_saving", submit_to_decision=True)
    out = await field_irrigation_recommendation("fld_1", req, user=object())
    # فشل التقديم لا يُلفَّق نجاحاً — يُعلَن submit_unavailable، والمرشَّح ما زال يُعرَض.
    assert out["approval_state"] == "submit_unavailable"
    assert out["decision_id"] is None
    assert any("not submitted" in lim for lim in out["limitations"])


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
