"""WOFOST يقرأ Kc/حرارة الأساس من بطاقة المحصول وθFC/θWP من FAO-56 عبر الموجِّه.

**العطل المقيس:** ``shared/wofost/engine.py`` يحمل ``CROP_PARAMS``/``SOIL_PARAMS`` بقيمه
الخاصّة — قمح kc_ini 0.40 (البطاقة 0.30) وtbase 5 (البطاقة gdd_base 0)، ذرة kc_ini 0.40
(0.30)، loam θ 0.30/0.12 (FAO-56: 0.25/0.10) — فيحسب ``/api/v1/simulate/what-if`` الماء
بجدولٍ موازٍ يخالف كلّ مستهلك آخر للحقل نفسه.

**الإصلاح:** المحرّك يقبل البارامترات محقونةً بالاسم (اتّجاه shared→platform محفوظ)،
والموجِّه يحقنها من البطاقة وFAO-56، والمخرَج يُعلن ``parameter_source``. المستدعون
الآخرون (بلا حقن) يبقون على القيم المدمجة موسومةً ``wofost_builtin``.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLANTING = date(2024, 1, 1)
_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
_CARD_IDS = sorted(
    p.stem for p in (_PLATFORM / "core" / "crop_cards").glob("*.yaml") if not p.stem.startswith("_")
)
_INJECTED_KEYS = {"kc_ini", "kc_mid", "kc_end", "tbase", "theta_fc", "theta_wp"}


def _weather(days: int = 200) -> list[dict]:
    return [
        {
            "date": (_PLANTING + timedelta(days=i)).isoformat(),
            "tmax": 30.0,
            "tmin": 15.0,
            "rain_mm": 0.0,
            "rad_mj": 18.0,
            "et0_mm": 5.0,
        }
        for i in range(days)
    ]


@pytest.fixture
def engine(monkeypatch):
    from shared.wofost import engine as eng

    async def _fake_fetch(lat, lon, start, end):
        return _weather()

    monkeypatch.setattr(eng, "fetch_weather_real", _fake_fetch)
    return eng


def _run(coro):
    return asyncio.run(coro)


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


def _card(crop_id: str) -> dict:
    from core.crop_cards.loader import load_crop_card

    card = load_crop_card(crop_id)
    assert card is not None, crop_id
    return card


# ── المحرّك: المحقون يحلّ محلّ المدمج ويُعلَن مصدره ──────────────────────────────


def test_uninjected_caller_keeps_builtin_values_and_says_so(engine):
    out = _simulate(engine)
    assert out["parameter_source"] == {
        "kc": "wofost_builtin",
        "tbase": "wofost_builtin",
        "soil_water": "wofost_builtin",
    }
    used = out["parameters_used"]
    # القيم المدمجة كما هي — مستدعٍ لا يحقن لا يتغيّر رقمه.
    assert (used["kc_ini"], used["tbase"], used["theta_fc"], used["theta_wp"]) == (
        0.40,
        5.0,
        0.30,
        0.12,
    )
    assert out["daily_series"][0]["kc"] == 0.40


def test_injected_values_drive_the_simulation(engine):
    out = _simulate(
        engine,
        kc_ini=0.30,
        kc_mid=1.15,
        kc_end=0.40,
        tbase=0.0,
        theta_fc=0.25,
        theta_wp=0.10,
    )
    assert out["parameter_source"] == {
        "kc": "crop_card",
        "tbase": "crop_card",
        "soil_water": "fao56",
    }
    series = out["daily_series"]
    assert series[0]["kc"] == 0.30, "Kc الابتدائيّ من البطاقة لا 0.40 المدمجة"
    assert max(d["kc"] for d in series) == 1.15
    # tbase=0 ⇒ GDD اليوميّ = min(topt=18, tmean=22.5) − 0 = 18 (كان 13 بـtbase 5).
    assert series[0]["gdd"] == 18.0
    assert out["parameters_used"]["theta_fc"] == 0.25
    assert out["parameters_used"]["theta_wp"] == 0.10


def test_injected_soil_water_changes_the_water_balance(engine):
    builtin = _simulate(engine)["water_balance"]["irrigation_applied_mm"]
    fao = _simulate(engine, theta_fc=0.25, theta_wp=0.10)["water_balance"]["irrigation_applied_mm"]
    assert builtin != fao, "θ المحقونة لم تصل إلى توازن الماء"


def test_injected_theta_makes_a_fao56_texture_known(engine):
    # "sand" ليس في SOIL_PARAMS المدمج؛ θ محقونة من FAO-56 تجعل الماء الأرضيّ يخصّ المُدخَل.
    out = _simulate(engine, soil_type="sand", theta_fc=0.10, theta_wp=0.04)
    assert out["parameter_resolution"]["soil_type_known"] is True
    assert out["resolved_soil_type"] == "sand"
    assert out["parameter_resolution"]["degraded"] is False
    # وبلا حقن يبقى الاحتياط مُفصَحاً كما كان.
    assert _simulate(engine, soil_type="sand")["parameter_resolution"]["degraded"] is True


@pytest.mark.parametrize(
    "kw",
    [
        {"kc_ini": 0.3},  # مجموعة Kc ناقصة
        {"theta_fc": 0.25},  # زوج θ ناقص
        {"kc_ini": 0.3, "kc_mid": 0.0, "kc_end": 0.4},  # Kc غير فيزيائيّ
        {"theta_fc": 0.10, "theta_wp": 0.25},  # θWP ≥ θFC
        {"tbase": 30.0},  # فوق topt ⇒ لا GDD أبداً
    ],
)
def test_invalid_injection_is_rejected_not_silently_used(engine, kw):
    with pytest.raises(ValueError):
        _simulate(engine, **kw)


# ── الموجِّه: يحقن من البطاقة وFAO-56 ─────────────────────────────────────────────


@pytest.fixture
def route():
    import api.routers.simulate as mod

    return mod


def _request(**kw):
    from api.api_models import WhatIfRequest

    args = {"field_id": "F1", "lat": 15.0, "lon": 44.0, "planting_date": _PLANTING.isoformat()}
    args.update(kw)
    return WhatIfRequest(**args)


def _capture(monkeypatch) -> list[dict]:
    import shared.wofost as pkg

    seen: list[dict] = []

    async def _fake(*a, **k):
        seen.append(k)
        return {
            "simulation": {"yield_t_ha": 1.0},
            "water_balance": {"irrigation_applied_mm": 10.0},
            "parameter_resolution": {"degraded": False},
        }

    monkeypatch.setattr(pkg, "simulate_wofost", _fake)
    return seen


@pytest.mark.parametrize(
    ("crop", "crop_id"),
    [("قمح صلب", "wheat"), ("ذرة صفراء", "maize"), ("شعير", "barley"), ("بطاطس", "potato")],
)
def test_router_passes_card_kc_and_tbase_to_both_arms(route, monkeypatch, crop, crop_id):
    seen = _capture(monkeypatch)
    _run(route.simulate_what_if(_request(crop=crop), user=None))
    card = _card(crop_id)
    assert len(seen) == 2
    for kw in seen:
        assert (kw["kc_ini"], kw["kc_mid"], kw["kc_end"]) == (
            card["kc"]["initial"],
            card["kc"]["mid"],
            card["kc"]["end"],
        )
        assert kw["tbase"] == card["thermal"]["gdd_base_c"]


def test_router_gap_named_values(route, monkeypatch):
    """القيم المسمّاة في المراجعة: قمح 0.30/0 (لا 0.40/5) · loam 0.25/0.10 (لا 0.30/0.12)."""
    seen = _capture(monkeypatch)
    _run(route.simulate_what_if(_request(crop="قمح صلب", soil_type="loam"), user=None))
    kw = seen[0]
    assert (kw["kc_ini"], kw["tbase"]) == (0.30, 0.0)
    assert (kw["theta_fc"], kw["theta_wp"]) == (0.25, 0.10)


@pytest.mark.parametrize("soil", ["loam", "clay_loam", "sandy_loam", "silt_loam", "sand"])
def test_router_passes_fao56_theta(route, monkeypatch, soil):
    from core.engines.fao56 import theta_fc_wp_for_texture

    seen = _capture(monkeypatch)
    _run(route.simulate_what_if(_request(soil_type=soil), user=None))
    assert (seen[0]["theta_fc"], seen[0]["theta_wp"]) == theta_fc_wp_for_texture(soil)


def test_router_injects_nothing_it_does_not_know(route, monkeypatch):
    # «خضروات» بلا بطاقة، وقوام مجهول لـFAO-56 ⇒ لا قيمة مُلفَّقة؛ المحرّك يُعلن wofost_builtin.
    seen = _capture(monkeypatch)
    _run(route.simulate_what_if(_request(crop="خضروات", soil_type="تربة مجهولة"), user=None))
    assert not (_INJECTED_KEYS & set(seen[0])), seen[0]


def test_router_end_to_end_reports_card_and_fao56_source(route, engine, monkeypatch):
    import shared.wofost as pkg

    monkeypatch.setattr(pkg, "simulate_wofost", engine.simulate_wofost)
    out = _run(route.simulate_what_if(_request(crop="ذرة صفراء", soil_type="loam"), user=None))
    assert out["available"] is True
    assert out["parameter_source"] == {
        "kc": "crop_card",
        "tbase": "crop_card",
        "soil_water": "fao56",
    }


@pytest.mark.parametrize("crop_id", _CARD_IDS)
def test_canonical_parameters_equal_the_card_for_every_card(route, crop_id):
    from core.season_phenology import crop_kc_profile

    params = route.canonical_engine_parameters(crop_id, "loam")
    prof = crop_kc_profile(crop_id)
    assert (params["kc_ini"], params["kc_mid"], params["kc_end"]) == (
        prof.kc_initial,
        prof.kc_mid,
        prof.kc_end,
    )
    assert params["tbase"] == _card(crop_id)["thermal"]["gdd_base_c"]
