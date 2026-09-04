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


_REQ = FieldIrrigationRequest(
    t_min_c=18.0, t_max_c=34.0, policy="water_saving", rain_recent_mm=0.0, forecast_rain_mm=3.0
)


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
    # WS-C.1b Zero-Legacy: لا مقارنة ظلّيّة إرثيّة بعد الآن (المحرّك مصدر ET0 الوحيد).
    assert "shadow" not in et0


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


_REQ_AUTO = FieldIrrigationRequest(policy="water_saving")  # لا حرارة ⇒ جلب تلقائيّ (والمطر معه)


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
            # المطرُ جزءٌ من اللقطة: بدونه يرفض المسارُ التوصيةَ بدل أن يحسبها على صفر.
            "rain_recent_mm": 0.0,
            "forecast_rain_mm": 3.0,
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
        # **عقدُ المُسجِّل هو المقيس** — لا شكلٌ يخصّ هذا المسار. كان يُرسَل
        # `recommendation` و`status` وهما حقلان لا يقرؤهما `record_decision`، فتُحفَظ
        # قيمةٌ فارغة ويُعلَن `pending_approval` محلّيّاً من غياب استثناء.
        assert payload["decision_type"] == "irrigation"
        assert payload["stage"] == "candidate"
        assert payload["decision_value"]["status"] == "pending_approval"
        assert payload["decision_value"]["approval_required"] is True
        assert "status" not in payload, "حقلٌ لا يقرؤه المُسجِّل يُحفَظ فارغاً"
        return {
            "decision_id": "dec_123",
            "authoritative": True,
            "persisted": True,
            "stage": "candidate",
        }

    monkeypatch.setattr(mod, "_submit_candidate_to_decision", _submit)
    req = FieldIrrigationRequest(policy="water_saving", submit_to_decision=True)

    async def _snap(_lat, _lon):
        return {
            "t_min_c": 17.0,
            "t_max_c": 33.0,
            "wind_2m_ms": 2.0,
            "solar_rad_mj_m2": 22.0,
            "rh_mean_pct": None,
            # المطرُ جزءٌ من اللقطة: بدونه يرفض المسارُ التوصيةَ بدل أن يحسبها على صفر.
            "rain_recent_mm": 0.0,
            "forecast_rain_mm": 3.0,
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
            # المطرُ جزءٌ من اللقطة: بدونه يرفض المسارُ التوصيةَ بدل أن يحسبها على صفر.
            "rain_recent_mm": 0.0,
            "forecast_rain_mm": 3.0,
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


# ─── المطر المفقود ≠ صفر ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_rain_refuses_instead_of_assuming_no_rain(monkeypatch):
    """لقطةٌ بلا مطر ⇒ ``dependency_unavailable``، لا توصيةٌ محسوبةٌ على «لا مطر».

    **العطل المقيس:** كان هذا المسار لا يمرّر المطرَ إلى ``recommend_irrigation``
    البتّة، فتأخذه النواةُ ``0.0`` بحكم توقيعها. والصفرُ يُنقِص المطروحَ من الحاجة
    فترتفع الكمّيّة — أي أنّ الانحيازَ في اتّجاه **الإذن بالريّ**، وهو الاتّجاه الذي
    يُغرِق حقلاً؛ ولا يظهر في المخرَج ما يقول إنّ المطرَ لم يُعرَف.
    """
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))

    async def _snap(_lat, _lon):
        return {
            "t_min_c": 17.0,
            "t_max_c": 33.0,
            "wind_2m_ms": 2.0,
            "solar_rad_mj_m2": 22.0,
            "rh_mean_pct": None,
            "rain_recent_mm": None,  # المحرّك لم يُعطِ مطرَ اليوم
            "forecast_rain_mm": 3.0,
            "day_of_year": 191,
            "valid_time": "2026-07-10",
            "source": "weather-engine-forecast",
        }

    monkeypatch.setattr(mod, "_field_weather_snapshot", _snap)
    out = await field_irrigation_recommendation("fld_1", _REQ_AUTO, user=object())
    assert out["status"] == "dependency_unavailable"
    assert out["recommendation"] is None
    assert any("المطر" in lim for lim in out["limitations"]), out["limitations"]


@pytest.mark.asyncio
async def test_manual_temperature_override_without_rain_also_refuses(monkeypatch):
    """التجاوزُ اليدويّ لا يفتح باباً خلفيّاً.

    لولا هذه الحالة لصار «تجاوزُ حرارة» يُسقِط المطرَ ضمناً إلى صفر، فيكون المسارُ
    الاحتياطيّ **أكثرَ إذناً بالريّ** من الأساسيّ — وهو عكسُ ما يُنتظَر من تجاوزٍ يدويّ.
    """
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))
    req = FieldIrrigationRequest(t_min_c=18.0, t_max_c=34.0, policy="water_saving")
    out = await field_irrigation_recommendation("fld_1", req, user=object())
    assert out["status"] == "dependency_unavailable"
    assert out["recommendation"] is None


@pytest.mark.asyncio
async def test_recent_rain_reaches_the_policy_and_lowers_the_amount(monkeypatch):
    """شاهدٌ موجب: المطرُ الأخير **يصل** النواةَ ويُغيّر الرقم.

    رفضُ الغياب وحدَه لا يُثبِت أنّ الحاضرَ يُستعمَل — مسارٌ يرفض ``None`` ثمّ يهمل
    القيمةَ يمرّ بحالتَي الرفض أعلاه وهو معطوب. فالمقيسُ هنا **الفرق**.

    **وقيدان مُعلَنان، مقيسان أثناء كتابة هذه الحالة — لا يُصلَحان هنا:**

    (١) ``irrigation_advice`` يقول صراحةً إنّ **المطر المتوقّع لا يدخل في الكمّيّة**؛
    يخفض الإلحاح ويؤخّر التوقيت. فصياغةٌ تنتظر نقصانَ الكمّيّة منه كانت ستُثبِّت
    سلوكاً لا وجودَ له — واحمرّت هذه الحالةُ عليه أوّلَ مرّة فكُشِف.

    (٢) وعلى **هذا المسار** المتوقّعُ خامدٌ تماماً: ٢٥ مم خلال ٤٨ ساعة لا تُغيّر شيئاً
    في الاستجابة — ``urgency`` يقودها الاستنزاف/الإجهاد لا المطر، و``timing_ar``
    و``rationale_ar`` (وفيهما «انتظِر قبل الريّ») **لا يُصدَّران أصلاً**. أي أنّ
    المزارع يُوصى بملء ≈٤٨ مم عشيّةَ مطرٍ متوقَّعٍ لا يُذكَر له. مسجَّلٌ فجوةً؛
    وتعديلُ قرار الإطلاق قرارٌ زراعيّ لا يُتَّخذ داخل شريحةِ إصلاحِ مُدخَل.
    """
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))

    async def _run(recent: float) -> dict:
        async def _snap(_lat, _lon):
            return {
                "t_min_c": 17.0,
                "t_max_c": 33.0,
                "wind_2m_ms": 2.0,
                "solar_rad_mj_m2": 22.0,
                "rh_mean_pct": None,
                "rain_recent_mm": recent,
                "forecast_rain_mm": 0.0,
                "day_of_year": 191,
                "valid_time": "2026-07-10",
                "source": "weather-engine-forecast",
            }

        monkeypatch.setattr(mod, "_field_weather_snapshot", _snap)
        out = await field_irrigation_recommendation("fld_1", _REQ_AUTO, user=object())
        assert out["status"] == "recommendation_ready"
        return out["recommendation"]

    dry = await _run(0.0)
    rained = await _run(20.0)
    assert dry["net_irrigation_mm"] > 0.0, "الحالةُ الجافّة لا تُنتِج كمّيّةً — لا فرقَ يُقاس"
    assert rained["net_irrigation_mm"] < dry["net_irrigation_mm"], (
        "مطرٌ أخيرٌ أكبر لم يُنقِص الكمّيّة — القيمةُ لا تصل النواة"
    )


# ─── حجزُ المطر المتوقَّع، وشاهدُ الحفظ ──────────────────────────────────


def _snap_forecast(rain_forecast: float):
    async def _snap(_lat, _lon):
        return {
            "t_min_c": 17.0,
            "t_max_c": 33.0,
            "wind_2m_ms": 2.0,
            "solar_rad_mj_m2": 22.0,
            "rh_mean_pct": None,
            "rain_recent_mm": 0.0,
            "forecast_rain_mm": rain_forecast,
            "day_of_year": 191,
            "valid_time": "2026-07-10",
            "source": "weather-engine-forecast",
        }

    return _snap


@pytest.mark.asyncio
async def test_forecast_rain_hold_withholds_the_release_decision(monkeypatch):
    """حكمان متعارضان ⇒ **امتناع**، لا أمرُ ريّ.

    **المقيسُ قبل هذه الشريحة:** باستنزافٍ فوق العتبة، `forecast_rain_mm=25` لا تُغيّر
    حرفاً — `should_irrigate=True` و`target_refill_mm=48.0` و`urgency=moderate`. أي
    يُوصى بملءٍ عشيّةَ مطرٍ **لا يُذكَر للمزارع**، لأنّ `timing_ar`/`rationale_ar` — وهما
    الموضعان الوحيدان اللذان يذكرانه — لم يكونا يُصدَّران، و`urgency` يبتلعه الاستنزاف.

    **ولا حكمَ زراعيّاً جديداً هنا:** العتبةُ (٥مم/٤٨ساعة) هي عتبةُ `irrigation_advice`
    منذ كُتِبت، والمستخرَجُ نتيجتُها لا قاعدةٌ ثانية. واجتماعُها مع قرار الاستنزاف يُنتِج
    `None` — وهو **نفسُ ما تعنيه `None`** في هذا الحقل أصلاً: لا قرارَ مُختلَق.
    """
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))
    monkeypatch.setattr(mod, "_field_weather_snapshot", _snap_forecast(25.0))
    out = await field_irrigation_recommendation("fld_1", _REQ_AUTO, user=object())

    rec = out["recommendation"]
    assert out["status"] == "recommendation_ready"
    assert rec["should_irrigate"] is None, "أمرُ ريٍّ صدر رغم مطرٍ متوقَّعٍ يؤجّله"
    assert rec["target_refill_mm"] is None
    assert rec["trigger_reason"] == "forecast_rain_hold_requires_reassessment"
    assert rec["forecast_hold"] is True
    # الاحتياجُ يبقى **معلومةً حسابيّة**: امتناعٌ عن الأمر لا حجبٌ للقياس.
    assert rec["net_irrigation_mm"] > 0
    # والسببُ يبلغ المزارع — حجزٌ صامتٌ أسوأ من أمرٍ خاطئ لأنّه لا يُراجَع.
    assert "مطر متوقّع" in rec["rationale_ar"]
    assert rec["timing_ar"]


@pytest.mark.asyncio
async def test_without_the_hold_the_release_decision_still_fires(monkeypatch):
    """الشاهدُ الموجب: الحجزُ مشروطٌ لا دائم — بلا مطرٍ متوقَّعٍ يبقى القرار كما كان."""
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))
    monkeypatch.setattr(mod, "_field_weather_snapshot", _snap_forecast(0.0))
    out = await field_irrigation_recommendation("fld_1", _REQ_AUTO, user=object())

    rec = out["recommendation"]
    assert rec["should_irrigate"] is True
    assert rec["trigger_reason"] == "depletion_at_or_above_trigger"
    assert rec["forecast_hold"] is False
    assert rec["target_refill_mm"] is not None


@pytest.mark.asyncio
async def test_the_hold_blocks_submission_to_decision_service(monkeypatch):
    """لا يُقدَّم مرشَّحٌ لا قرارَ فيه — وإلّا كان سجلَّ موافقةٍ على امتناع."""
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))
    monkeypatch.setattr(mod, "_field_weather_snapshot", _snap_forecast(25.0))

    called = False

    async def _submit(_payload, _tenant):
        nonlocal called
        called = True
        return {"decision_id": "dec_should_not_happen"}

    monkeypatch.setattr(mod, "_submit_candidate_to_decision", _submit)
    req = FieldIrrigationRequest(policy="water_saving", submit_to_decision=True)
    out = await field_irrigation_recommendation("fld_1", req, user=object())

    assert called is False, "قُدِّم مرشَّحٌ أثناء حجز المطر"
    assert out["approval_state"] == "blocked_forecast_rain_hold"
    assert out["decision_id"] is None


@pytest.mark.asyncio
async def test_submission_without_proof_of_persistence_is_not_pending_approval(monkeypatch):
    """ردٌّ بلا شاهدِ حفظٍ ⇒ **لا** ``pending_approval``.

    نقطةُ التسجيل لا تُعيد `status`، فاستنتاجُه محلّيّاً من غياب استثناء كان يُعلِن
    نجاحاً لم يُثبَت — ويصير للمزارع «قُدِّم للموافقة» وقد لا يكون شيءٌ قد حُفِظ.
    """
    _patch(monkeypatch, _FakeConn(depletion_mm=60.0))
    monkeypatch.setattr(mod, "_field_weather_snapshot", _snap_forecast(0.0))

    async def _submit(_payload, _tenant):
        return {"decision_id": "dec_123"}  # بلا authoritative/persisted/stage

    monkeypatch.setattr(mod, "_submit_candidate_to_decision", _submit)
    req = FieldIrrigationRequest(policy="water_saving", submit_to_decision=True)
    out = await field_irrigation_recommendation("fld_1", req, user=object())

    assert out["approval_state"] == "submit_unproven"
    assert out["decision_id"] is None
    assert any("fail-closed" in lim for lim in out["limitations"])
