"""حارس سلوك راية SIM_PCSE_ENABLED + الأمان (SIM-PCSE-01) — الأمانة القائمة تبقى، والانخراط fail-closed.

يفرض شروط المالك سلوكيّاً:
  • **مطفأة ⇒ السلوك الصادق القائم:** تطوير ⇒ deterministic_fallback · إنتاج ⇒ fail-closed.
  • **مشعلة ⇒ محرّك مُنخرِط:** محصول خارج السجلّ ⇒ fail-closed دائماً (لا معاملات مقترَضة) · pcse غائب/
    مدخلات ناقصة ⇒ fail-closed مُصنَّف (لا استبدال صامت بالبديل).
فحص صرف — ``pytest -m unit`` (pcse غير مُركَّب في CI الوحدة ⇒ مسار PCSE الثقيل يبقى pragma:no cover).
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

_SVC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "services", "agriai-engine"))
if _SVC not in sys.path:
    sys.path.insert(0, _SVC)

import wofost_adapter as wa  # noqa: E402

_FULL = {  # مدخلات كافية لـPCSE (لعزل شرط المحصول عن شرط الكفاية)
    "weather": {"daily": [{"tmax": 30, "tmin": 15}], "total_rain_mm": 40},
    "soil": {"available_water_mm": 100},
    "agromanagement": {"irrigation_mm": 20},
}


def _sim(crop, monkeypatch, *, flag, prod):
    monkeypatch.setenv("SIM_PCSE_ENABLED", "1" if flag else "0")
    monkeypatch.setenv("AGRIAI_PRODUCTION_MODE", "1" if prod else "0")
    return wa.simulate(crop=crop, **_FULL)


def test_flag_off_dev_keeps_deterministic_fallback(monkeypatch):
    out = _sim({"crop": "wheat"}, monkeypatch, flag=False, prod=False)
    assert out["provenance"] == "deterministic_fallback"  # السلوك القائم لم يتغيّر
    assert "yield_interval" in out


def test_flag_off_production_fails_closed(monkeypatch):
    with pytest.raises(RuntimeError) as e:
        _sim({"crop": "wheat"}, monkeypatch, flag=False, prod=True)
    assert "agriai_production_simulation_unavailable" in str(e.value)  # الأمانة القائمة


def test_flag_on_unsupported_crop_fails_closed_always(monkeypatch):
    """محصول خارج السجلّ (sorghum) + الراية مشعلة ⇒ fail-closed حتى في التطوير (لا معاملات مقترَضة)."""
    with pytest.raises(RuntimeError) as e:
        _sim({"crop": "sorghum"}, monkeypatch, flag=True, prod=False)
    assert "sim_pcse_unsupported_crop" in str(e.value)


def test_flag_on_supported_crop_without_pcse_fails_closed(monkeypatch):
    """الراية مشعلة + محصول مدعوم لكن pcse غير مُركَّب (CI) ⇒ fail-closed مُصنَّف (لا بديل صامت)."""
    with pytest.raises(RuntimeError) as e:
        _sim({"crop": "wheat"}, monkeypatch, flag=True, prod=False)
    msg = str(e.value)
    assert "simulation_unavailable" in msg and "pcse_unavailable" in msg


def test_flag_helper_reads_env(monkeypatch):
    monkeypatch.setenv("SIM_PCSE_ENABLED", "0")
    assert wa.sim_pcse_enabled() is False
    monkeypatch.setenv("SIM_PCSE_ENABLED", "true")
    assert wa.sim_pcse_enabled() is True
