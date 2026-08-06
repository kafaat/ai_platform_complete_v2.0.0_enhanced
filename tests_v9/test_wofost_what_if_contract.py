#!/usr/bin/env python3
"""عقد ``/api/v1/simulate/what-if`` — سبعة أعطال مُثبَتة بالتشغيل، لا بوجود حقل.

كلّ اختبار هنا **يحقن الطقس ويؤكّد القيم النهائيّة**. اختبار استيراد أو اختبار
«الحقل موجود في الاستجابة» كان سيمرّ على كلّ واحد من الأعطال السبعة قبل الإصلاح:

* المحرّك كان يُعيد ``{"error": ...}`` والاستجابة تخرج ``available: true`` بقيم
  ``null`` — كلّ الحقول موجودة، ولا شيء منها صحيح؛
* ``reduce_irrigation`` و``no_irrigation`` كانا يُنتجان **الأرقام نفسها بالضبط**
  — الحقل ``scenario`` موجود في الاستجابة، وهو صدىً لا أثر له؛
* «محصول لا وجود له» كان يُعيد ٩.٧٨٨ ط/هـ — رقم قمحٍ صلب منسوبٌ إلى محصول آخر.

فالتمييز الوحيد الذي يفصل المُصلَح عن المعطوب هو **قيمة**، ولذلك تُحقَن هنا سلسلة
طقس ثابتة (بلا شبكة) وتُقاس المخرجات.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.unit

_PLANTING = date(2024, 1, 1)


def _weather(days: int = 200, *, rain_mm: float = 0.0) -> list[dict]:
    """سلسلة طقس ثابتة: جافّة وحارّة بما يكفي لتشغيل عتبة الإجهاد كلّ موسم."""
    return [
        {
            "date": (_PLANTING + timedelta(days=i)).isoformat(),
            "tmax": 30.0,
            "tmin": 15.0,
            "rain_mm": rain_mm,
            "rad_mj": 18.0,
            "et0_mm": 5.0,
        }
        for i in range(days)
    ]


@pytest.fixture
def engine(monkeypatch):
    """المحرّك الحقيقيّ بطقس محقون — لا شبكة، ونتيجة قابلة للتكرار."""
    from shared.wofost import engine as eng

    async def _fake_fetch(lat, lon, start, end):
        return _weather()

    monkeypatch.setattr(eng, "fetch_weather_real", _fake_fetch)
    return eng


def _run(coro):
    return asyncio.run(coro)


# ══════════════════════════════════════════════════════════════
# المحرّك — نسبة الريّ تُنفَّذ فعلاً، والاحتياط الصامت صار مُفصَحاً
# ══════════════════════════════════════════════════════════════


def _simulate(engine, **kw):
    args = {
        "field_id": "F1",
        "crop": "قمح صلب",
        "soil_type": "loam",
        "lat": 15.0,
        "lon": 44.0,
        "planting_date": _PLANTING,
    }
    args.update(kw)
    return _run(engine.simulate_wofost(**args))


def test_reduce_irrigation_is_not_the_same_run_as_no_irrigation(engine):
    """العطل الأصليّ: السيناريوان ينتجان الأرقام نفسها لأنّ الريّ منطقيّ لا نسبة.

    قبل الإصلاح كان ``irrigation`` بولياناً، فكلّ «تقليل» يتدهور إلى «إيقاف».
    هذا الاختبار يُحمِرّ فور عودة البوليان — لا يكفي وجود الحقل في المخرَج.
    """
    full = _simulate(engine, irrigation_fraction=1.0)
    half = _simulate(engine, irrigation_fraction=0.5)
    none = _simulate(engine, irrigation_fraction=0.0)

    a_full, a_half, a_none = (
        r["water_balance"]["irrigation_applied_mm"] for r in (full, half, none)
    )
    assert a_none == 0.0, "بلا ريّ يجب ألّا يُطبَّق ماء"
    # «تقليل» يعني بين الطرفين **حصراً**. الصيغة الأولى هنا قارنت الطرف الأدنى وحده،
    # فمرّت زرعةٌ تُعيد الملء الكامل عند أيّ نسبة موجبة (تقليل = ريّ كامل). المقياس
    # الصادق هو الحصر بين الحدّين، لا الاختلاف عن أحدهما.
    assert a_none < a_half < a_full, (
        f"«تقليل الريّ» ليس بين الطرفين: بلا={a_none} · تقليل={a_half} · كامل={a_full}"
    )
    assert full["simulation"]["yield_t_ha"] >= none["simulation"]["yield_t_ha"]


def test_the_fraction_is_echoed_so_the_caller_can_derive_what_ran(engine):
    r = _simulate(engine, irrigation_fraction=0.25)
    assert r["water_balance"]["irrigation_fraction"] == 0.25


def test_the_fraction_is_clamped_not_trusted(engine):
    assert _simulate(engine, irrigation_fraction=5.0)["water_balance"]["irrigation_fraction"] == 1.0
    assert (
        _simulate(engine, irrigation_fraction=-3.0)["water_balance"]["irrigation_fraction"] == 0.0
    )


def test_the_legacy_boolean_still_means_what_it_meant(engine):
    """التوافق الخلفيّ مقيس: مستهلكٌ لا يمرّر نسبةً يحصل على سلوكه السابق."""
    assert _simulate(engine, irrigation=False)["water_balance"]["irrigation_fraction"] == 0.0
    assert _simulate(engine, irrigation=True)["water_balance"]["irrigation_fraction"] == 1.0


def test_an_unknown_crop_no_longer_silently_returns_the_wheat_number(engine):
    """«محصول لا وجود له» كان يعيد ٩.٧٨٨ ط/هـ — رقم القمح الصلب، بلا أيّ إشارة."""
    wheat = _simulate(engine, crop="قمح صلب")
    unknown = _simulate(engine, crop="محصول لا وجود له")

    # الرقم ما يزال هو هو (الاحتياط لم يُزَل — منعُه يكسر نشراً شرعيّاً)…
    assert unknown["simulation"]["yield_t_ha"] == wheat["simulation"]["yield_t_ha"]
    # …لكنّ الادّعاء صار مُفصَحاً عنه، وهذا هو الفرق الذي يقرؤه المستهلك.
    assert unknown["parameter_resolution"]["crop_known"] is False
    assert unknown["parameter_resolution"]["degraded"] is True
    assert unknown["resolved_crop"] == "قمح صلب"
    assert unknown["crop"] == "محصول لا وجود له", "اسم المستخدم يبقى كما أُرسِل"
    assert wheat["parameter_resolution"]["degraded"] is False


def test_an_unknown_soil_is_disclosed_the_same_way(engine):
    unknown = _simulate(engine, soil_type="تربة مجهولة")
    assert unknown["parameter_resolution"]["soil_type_known"] is False
    assert unknown["resolved_soil_type"] == "loam"
    assert unknown["parameter_resolution"]["degraded"] is True
    assert _simulate(engine, soil_type="clay_loam")["parameter_resolution"]["degraded"] is False


def test_needed_water_is_blind_to_how_much_was_actually_applied(engine):
    """``irrigation_needed_mm`` **طلبٌ مناخيّ** لا يعلم شيئاً عن السيناريو.

    ``engine.py:425`` يحسبه ``max(0, etc − rain)`` — و``etc`` دالّة طقسٍ ومرحلةٍ
    فقط. فهو ثابت عبر كلّ نسب الريّ، بينما ``irrigation_applied_mm`` يتحرّك معها.
    هذا هو سبب إسقاط الطرح القديم: مقدارٌ ثابتٌ لا يمكن أن يقيس فرقاً بين سيناريوين.
    """
    values = {f: _simulate(engine, irrigation_fraction=f)["water_balance"] for f in (0.0, 0.5, 1.0)}
    needed = {wb["irrigation_needed_mm"] for wb in values.values()}
    assert len(needed) == 1, f"الطلب تحرّك مع النسبة ({needed}) — راجع المحرّك"
    applied = [values[f]["irrigation_applied_mm"] for f in (0.0, 0.5, 1.0)]
    assert applied[0] < applied[1] < applied[2], "المطبَّق يجب أن يتحرّك مع النسبة"


def test_the_old_water_saved_number_was_ten_percent_of_demand_and_nothing_else(engine):
    """قياسٌ يُثبِت أنّ الرقم القديم لم يكن «مقلوباً» بل **معاملاً** بلا دلالة.

    الطرح القديم كان ``needed(irrigation=True) − needed(irrigation=False)``. والفرع
    الوحيد بينهما في ``engine.py:425`` هو ``* 1.1``، و``total_etc_mm`` متطابق بين
    الحالتين. فالناتج ``0.1 × الطلب`` بالضبط — عددٌ لا يعلم بالسيناريو ولا بالماء
    المُطبَّق، ويكبر كلّما جفّ الموسم. أُبقِي المعامل نفسه (قرار مالك مفتوح:
    ``WOFOST-IRRIGATION-EFFICIENCY-COEFFICIENT-01``) وأُسقِط الطرح المبنيّ عليه.
    """
    wet = _simulate(engine, irrigation=True, irrigation_fraction=1.0)["water_balance"]
    dry = _simulate(engine, irrigation=False, irrigation_fraction=0.0)["water_balance"]

    assert wet["total_etc_mm"] == dry["total_etc_mm"], "لو اختلف الطلب لَما كان الفرق معاملاً صرفاً"
    old_water_saved = round(wet["irrigation_needed_mm"] - dry["irrigation_needed_mm"], 1)
    # المحرّك يقرّب كلّ طرف إلى منزلة واحدة قبل الطرح، فالهامش هنا هامش تقريبٍ لا تساهل.
    assert old_water_saved == pytest.approx(0.1 * dry["irrigation_needed_mm"], abs=0.2), (
        f"«الماء الموفَّر» القديم = {old_water_saved} = عُشر الطلب ({dry['irrigation_needed_mm']}), "
        "لا فرق سيناريو"
    )


# ══════════════════════════════════════════════════════════════
# الموجِّه — فشلٌ مغلق، رفضُ التاريخ الفاسد، وطرحٌ متجانس
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def route():
    import api.routers.simulate as mod

    return mod


def _request(**kw):
    from api.api_models import WhatIfRequest

    args = {"field_id": "F1", "lat": 15.0, "lon": 44.0}
    args.update(kw)
    return WhatIfRequest(**args)


def _fake_engine(monkeypatch, impl):
    """يستبدل ``shared.wofost.simulate_wofost`` — الموجِّه يستورده داخل الدالّة."""
    import shared.wofost as pkg

    monkeypatch.setattr(pkg, "simulate_wofost", impl)


def test_an_engine_error_return_is_a_failure_not_a_success(route, monkeypatch):
    """المحرّك **يُعيد** الخطأ ولا يرفعه، فـ``except`` لم يكن يعمل ولو مرّة.

    قبل الإصلاح: ``available: true`` وكلّ الأرقام ``null`` — ادّعاء نجاحٍ لم يقع،
    والمستهلك (``simulate_adapter``) يقرأ ``None`` ويحسبها «لا فرق».
    """

    async def _err(*a, **k):
        return {"error": "فشل جلب بيانات الطقس من Open-Meteo"}

    _fake_engine(monkeypatch, _err)
    out = _run(route.simulate_what_if(_request(), user=None))

    assert out["available"] is False
    assert out["error_code"] == "SIMULATION_FAILED"
    assert "Open-Meteo" not in out["error"], "تفاصيل المحرّك لا تعود إلى العميل"
    assert out["correlation_id"]


def test_an_exception_does_not_leak_its_text_to_the_client(route, monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("postgres://user:secret@db:5432 غير متاح")

    _fake_engine(monkeypatch, _boom)
    out = _run(route.simulate_what_if(_request(), user=None))

    assert out["available"] is False
    assert out["error_code"] == "SIMULATION_FAILED"
    assert "secret" not in str(out) and "postgres" not in str(out)


def test_an_invalid_planting_date_is_rejected_not_silently_today(route, monkeypatch):
    """``except ValueError: pd = today()`` كان يحاكي موسماً غير المطلوب وينسبه إليه."""
    from fastapi import HTTPException

    async def _ok(*a, **k):
        raise AssertionError("لا يجوز أن يصل الطلب إلى المحرّك بتاريخ فاسد")

    _fake_engine(monkeypatch, _ok)
    with pytest.raises(HTTPException) as exc:
        _run(route.simulate_what_if(_request(planting_date="2024-13-45"), user=None))
    assert exc.value.status_code == 422
    assert "planting_date" in str(exc.value.detail)


def test_an_unlisted_scenario_is_rejected_by_the_model(route):
    """``scenario: str`` حرّ كان يُقبل ويُعاد صدىً؛ المجموعة مغلقة الآن."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _request(scenario="اقتراح_مبتكر")
    # والقيم الثلاث المُرسَلة فعلاً في المستودع تبقى مقبولة:
    for name in ("reduce_irrigation", "no_irrigation", "recommended_action"):
        assert _request(scenario=name).scenario == name


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [("no_irrigation", 0.0), ("recommended_action", 0.0), ("reduce_irrigation", 0.5)],
)
def test_the_scenario_reaches_the_engine_as_a_fraction(route, monkeypatch, scenario, expected):
    """ليس وجود الحقل في الاستجابة هو المطلوب، بل وصوله إلى المحرّك."""
    seen: list[float] = []

    async def _capture(*a, irrigation=True, irrigation_fraction=None, **k):
        seen.append(irrigation_fraction)
        return {
            "simulation": {"yield_t_ha": 1.0},
            "water_balance": {"irrigation_applied_mm": 10.0},
            "parameter_resolution": {"degraded": False},
        }

    _fake_engine(monkeypatch, _capture)
    out = _run(route.simulate_what_if(_request(scenario=scenario), user=None))

    assert seen == [route.ACTION_IRRIGATION_FRACTION, expected]
    assert out["scenario_irrigation_fraction"] == expected


def test_water_saved_is_derived_from_applied_water_only(route, monkeypatch):
    """الطرح على مقدار متجانس بين الفرعين — لا على ``irrigation_needed_mm``."""
    arms = iter(
        [
            {  # الإجراء (ريّ كامل)
                "simulation": {"yield_t_ha": 4.0},
                "water_balance": {
                    "irrigation_applied_mm": 300.0,
                    "irrigation_needed_mm": 999.0,  # لو قُرِئ هذا لظهر رقم آخر
                },
                "parameter_resolution": {"degraded": False},
            },
            {  # السيناريو
                "simulation": {"yield_t_ha": 3.0},
                "water_balance": {
                    "irrigation_applied_mm": 120.0,
                    "irrigation_needed_mm": 111.0,
                },
                "parameter_resolution": {"degraded": False},
            },
        ]
    )

    async def _arm(*a, **k):
        return next(arms)

    _fake_engine(monkeypatch, _arm)
    out = _run(route.simulate_what_if(_request(), user=None))

    assert out["water_saved_mm"] == 180.0  # 300 − 120، لا 999 − 111
    assert out["water_saved_basis"] == "irrigation_applied_mm"
    assert out["water_use_direction"] == "reduction"
    assert out["action_irrigation_applied_mm"] == 300.0
    assert out["scenario_irrigation_applied_mm"] == 120.0
    assert out["recommended_action_helps"] is True


def test_a_scenario_that_uses_more_water_is_reported_as_an_increase(route, monkeypatch):
    """الاتّجاه يُقاس ولا يُفترَض؛ نسبة أقلّ قد تُشغّل عتبة الإجهاد أكثر.

    تصحيح صريح من المالك: «``baseline − scenario`` ليست مقلوبة دائماً — عرّف دلالة
    كلّ سيناريو واختبر التخفيض والزيادة». وقصُّ السالب عند الصفر كان سيُخفي الزيادة.
    """
    arms = iter(
        [
            {
                "simulation": {"yield_t_ha": 4.0},
                "water_balance": {"irrigation_applied_mm": 100.0},
                "parameter_resolution": {"degraded": False},
            },
            {
                "simulation": {"yield_t_ha": 4.0},
                "water_balance": {"irrigation_applied_mm": 175.0},
                "parameter_resolution": {"degraded": False},
            },
        ]
    )

    async def _arm(*a, **k):
        return next(arms)

    _fake_engine(monkeypatch, _arm)
    out = _run(route.simulate_what_if(_request(scenario="reduce_irrigation"), user=None))

    assert out["water_saved_mm"] == -75.0, "الزيادة تُعلَن سالبةً، لا تُقَصّ إلى صفر"
    assert out["water_use_direction"] == "increase"
    assert out["recommended_action_helps"] is False  # 4.0 > 4.0 × 1.02 كاذبة


def test_a_degraded_parameter_resolution_reaches_the_response(route, monkeypatch):
    async def _degraded(*a, **k):
        return {
            "simulation": {"yield_t_ha": 9.788},
            "water_balance": {"irrigation_applied_mm": 10.0},
            "parameter_resolution": {
                "crop_known": False,
                "soil_type_known": True,
                "degraded": True,
            },
            "resolved_crop": "قمح صلب",
            "resolved_soil_type": "loam",
        }

    _fake_engine(monkeypatch, _degraded)
    out = _run(route.simulate_what_if(_request(crop="محصول لا وجود له"), user=None))

    assert out["degraded"] is True
    assert out["parameter_resolution"]["crop_known"] is False
    assert "قمح صلب" in out["note_ar"]


def test_end_to_end_with_injected_weather_produces_a_real_difference(route, engine, monkeypatch):
    """الموجِّه فوق المحرّك الحقيقيّ: قيمٌ نهائيّة، لا مضاعِفات ولا حقول.

    هذا هو الاختبار الذي كان سيُحمِرّ على العطل الأصليّ برمّته: قبل الإصلاح كان
    ``water_saved_mm`` طرحاً بين مقدارَين غير متجانسَين، و``reduce_irrigation``
    يُنتج ما يُنتجه ``no_irrigation``.
    """
    import shared.wofost as pkg

    monkeypatch.setattr(pkg, "simulate_wofost", engine.simulate_wofost)

    reduce_ = _run(
        route.simulate_what_if(
            _request(scenario="reduce_irrigation", planting_date=_PLANTING.isoformat()), user=None
        )
    )
    none = _run(
        route.simulate_what_if(
            _request(scenario="no_irrigation", planting_date=_PLANTING.isoformat()), user=None
        )
    )

    assert reduce_["available"] is True and none["available"] is True
    assert none["scenario_irrigation_applied_mm"] == 0.0
    assert reduce_["scenario_irrigation_applied_mm"] > 0.0
    assert reduce_["water_saved_mm"] < none["water_saved_mm"], (
        "تقليل الريّ يوفّر أقلّ من إيقافه — وقبل الإصلاح كان الرقمان متطابقين"
    )
    assert none["water_saved_mm"] == none["action_irrigation_applied_mm"]
    assert reduce_["degraded"] is False
