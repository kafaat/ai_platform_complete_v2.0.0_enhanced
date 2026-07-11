"""راوتر /api/v1/gdd/track يستهلك نواة GDD من محرّك الطقس (WS-C.1c Zero-Legacy) —

يُثبِت: المسار يفوّض النواة للمحرّك فعلاً · سياسة المراحل تُطبَّق على تراكميّ المحرّك ·
تعذّر المحرّك ⇒ 503 بلا GDD محلّيّ. (أُزيلت المقارنة الظلّيّة ونواة daily_gdd المحلّيّة.)
"""

from __future__ import annotations

import api.routers.gdd as mod
import pytest
from api.api_models import DailyTempInput, GDDRequest
from api.gdd_tracker import GDD_CROP_PARAMS
from fastapi import HTTPException


def _simple_gdd(t_min: float, t_max: float, t_base: float, t_upper: float | None) -> float:
    """نسخة اختبار محلّيّة لصيغة GDD method="simple" (لتوليد ردّ محرّك وهميّ فقط —
    ليست نواة إنتاجيّة؛ الاختبارات مُستثناة من حارس الصيغ)."""
    tmax = min(t_max, t_upper) if t_upper is not None else t_max
    return max(0.0, (tmax + t_min) / 2.0 - t_base)


def _req(crop="wheat", n=5):
    temps = [DailyTempInput(t_min_c=12.0 + i, t_max_c=28.0 + i) for i in range(n)]
    return GDDRequest(crop=crop, temps=temps)


def _engine_cumulative(crop, req):
    p = GDD_CROP_PARAMS[crop]
    return sum(_simple_gdd(t.t_min_c, t.t_max_c, p["t_base"], p["t_upper"]) for t in req.temps)


def _patch_engine(monkeypatch, *, raises=None):
    async def _fake(*, daily_t_min, daily_t_max, base_c, upper_cutoff_c, method):
        if raises is not None:
            raise raises
        # المحرّك الكنسيّ بنفس الطريقة ⇒ يعيد قيمة الإرث نفسها (round 3).
        daily = [
            round(_simple_gdd(mn, mx, base_c, upper_cutoff_c), 3)
            for mn, mx in zip(daily_t_min, daily_t_max, strict=False)
        ]
        return {
            "product": "gdd",
            "calculation_version": "gdd/daily/1.0.0",
            "unit": "degC-day",
            "daily_gdd": daily,
            "accumulated_gdd": round(sum(daily), 3),
            "thresholds_used": {
                "base_c": base_c,
                "upper_cutoff_c": upper_cutoff_c,
                "method": method,
            },
            "valid_period": {"start_date": None, "end_date": None, "days": len(daily)},
            "quality_status": "validated",
            "limitations": [],
        }

    monkeypatch.setattr(mod, "_engine_gdd", _fake)


@pytest.mark.asyncio
async def test_route_consumes_engine_and_carries_provenance(monkeypatch):
    _patch_engine(monkeypatch)
    req = _req()
    out = await mod.gdd_track(req, user=object())
    assert out["crop"] == "wheat"
    prov = out["gdd_provenance"]
    assert prov["source"] == "weather-engine"
    assert prov["calculation_version"] == "gdd/daily/1.0.0"
    # التراكميّ من المحرّك يطابق حساب الإرث (نفس الطريقة).
    assert abs(out["cumulative_gdd"] - round(_engine_cumulative("wheat", req), 1)) < 1e-6


@pytest.mark.asyncio
async def test_provenance_has_no_shadow_block(monkeypatch):
    # WS-C.1c Zero-Legacy: أُزيلت المقارنة الظلّيّة — النَّسَب من المحرّك مباشرة بلا "shadow".
    _patch_engine(monkeypatch)
    out = await mod.gdd_track(_req(), user=object())
    assert "shadow" not in out["gdd_provenance"]
    assert out["gdd_provenance"]["thresholds_used"] is not None


@pytest.mark.asyncio
async def test_engine_down_fails_closed_503(monkeypatch):
    _patch_engine(monkeypatch, raises=HTTPException(status_code=502, detail="down"))
    with pytest.raises(HTTPException) as ei:
        await mod.gdd_track(_req(), user=object())
    assert ei.value.status_code == 503
    assert "fail-closed" in str(ei.value.detail)


@pytest.mark.asyncio
async def test_unknown_crop_422_before_engine(monkeypatch):
    # محصول مجهول ⇒ 422 دون استدعاء المحرّك.
    called = {"n": 0}

    async def _fake(**_kw):
        called["n"] += 1
        return {}

    monkeypatch.setattr(mod, "_engine_gdd", _fake)
    with pytest.raises(HTTPException) as ei:
        await mod.gdd_track(_req(crop="banana_unknown"), user=object())
    assert ei.value.status_code == 422
    assert called["n"] == 0
