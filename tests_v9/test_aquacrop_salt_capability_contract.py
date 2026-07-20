"""حارس WATER-SALT-02 — محوّل AquaCrop للمسار الملحيّ (Maas-Hoffman الداخليّ) + براهين سلبيّة.

يفرض براهين المواصفة §4 + قرارات §5 المعتمدة + ملاحظة الصدق:
  • **عقد قدرة ببرهان سلبيّ:** supported:true بلا limits/status_enum/references يفشل (لا fail-open مقنّع).
  • **برهان توجيه (§5-1، مصدر حقيقة واحد):** بلا ملوحة / ECe تحت العتبة ⇒ المحرّك الملحيّ **لم يُستدعَ** (PCSE المرجع).
  • **رتابة:** ECe أعلى ⇒ غلّة ≤ (حتّى القاع) — Maas-Hoffman خطّيّ نازل.
  • **إنتاج fail-closed:** AGRIAI_PRODUCTION_MODE + الراية مطفأة / الحزمة مؤجَّلة ⇒ فشل مُصنَّف.
  • **صدق (ملاحظة الجلسة):** «لا نقل ملح زمنيّ» يبقى في limits لا covers — Maas-Hoffman ثابت لا ديناميكيّ
    (المواصفة §Q2 افترضت AquaCrop الديناميكيّ؛ البناء المعتمد ثابت، فلا يُدّعى النقل الزمنيّ).

وحدة صرفة — ``pytest -m unit`` (لا شبكة/قاعدة). الاستيراد عبر مسار الخدمة.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_MOD = _ROOT / "services" / "agriai-engine" / "aquacrop_adapter.py"


def _load():
    spec = importlib.util.spec_from_file_location("aquacrop_adapter", _MOD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # لازم قبل exec: @dataclass يحلّ الوحدة عبر sys.modules
    spec.loader.exec_module(mod)
    return mod


def test_capability_contract_has_limits_and_refs():
    """عقد قدرة يُعلِن حدوده وإلّا fail-open مقنّع (برهان سلبيّ للمعيار A5)."""
    m = _load()
    cap = m.AQUACROP_SALT_CAPABILITY
    assert cap.supported is True
    assert cap.limits and cap.status_enum and cap.references, "supported:true بلا حدود = fail-open"
    for c in cap.covers:
        assert c.ref and ".py:" in c.ref, "كلّ ادّعاء covers مقرون بمرجع file:line"
    assert cap.calibration_status.startswith("uncalibrated")
    assert cap.flag == "AQUACROP_ENABLED"


def test_honesty_no_time_dynamic_transport_stays_in_limits():
    """صدق: Maas-Hoffman ثابت ⇒ «لا نقل ملح زمنيّ» في limits لا covers (لا ادّعاء ديناميكيّ)."""
    m = _load()
    cap = m.AQUACROP_SALT_CAPABILITY
    joined_limits = " | ".join(cap.limits)
    joined_covers = " | ".join(c.claim for c in cap.covers)
    assert "نقل ملح زمنيّ" in joined_limits, "حدّ النقل الزمنيّ يجب أن يبقى في limits"
    assert "زمنيّ" not in joined_covers, "لا ادّعاء نقل زمنيّ في covers (Maas-Hoffman ثابت)"


def test_routing_single_source_of_truth():
    """§5-1: المحرّك الملحيّ يُستدعى فقط فوق عتبة ECe — لا مجرّد وجود مدخل."""
    m = _load()
    assert m.salt_engine_applies(None) is False
    assert m.salt_engine_applies({}) is False
    assert m.salt_engine_applies({"ec_e_initial": 0.5}) is False  # تحت العتبة (2.0) ⇒ PCSE
    assert m.salt_engine_applies({"ec_e_initial": 6.0}) is True  # فوق العتبة ⇒ المحرّك الملحيّ
    # عتبة صريحة قابلة للتمرير
    assert m.salt_engine_applies({"ec_e_initial": 3.0}, ece_threshold=4.0) is False


def test_maas_hoffman_monotonic_yield_decreasing_in_ece():
    """رتابة: ECe أعلى ⇒ Ks أقلّ ⇒ غلّة ≤ (حتّى القاع 0)."""
    m = _load()
    crop = {"name": "wheat", "max_yield_kg_ha": 5000}
    prev = None
    for ece in [0.0, 6.0, 8.0, 12.0, 20.0, 40.0]:
        r = m.simulate(crop, {}, {}, {"ec_e_initial": ece})
        y = r["yield_kg_ha"]
        if prev is not None:
            assert y <= prev + 1e-6, f"غير رتيب عند ECe={ece}: {y} > {prev}"
        prev = y
        assert y >= 0.0
    # تحت العتبة (a=6 للقمح) لا خفض
    assert m.simulate(crop, {}, {}, {"ec_e_initial": 3.0})["yield_kg_ha"] == pytest.approx(5000.0)


def test_provenance_always_uncalibrated_and_engine_internal():
    m = _load()
    r = m.simulate({"name": "barley"}, {}, {}, {"ec_e_initial": 10.0})
    assert r["provenance"] == "aquacrop_uncalibrated"
    assert r["engine"] == "maas_hoffman_internal"  # ليست الحزمة الرسميّة (مؤجَّلة)
    assert "salt_profile" in r and "ks_salt" in r["salt_profile"]


def test_production_fail_closed(monkeypatch):
    """إنتاج + الراية مطفأة ⇒ فشل مُغلَق مُصنَّف (لا بديل داخليّ صامت في الإنتاج)."""
    m = _load()
    monkeypatch.setenv("AGRIAI_PRODUCTION_MODE", "1")
    monkeypatch.delenv("AQUACROP_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="aquacrop_production_unavailable"):
        m.simulate({"name": "wheat"}, {}, {}, {"ec_e_initial": 10.0})


def test_dev_fallback_runs_when_flag_off_non_production(monkeypatch):
    """تطوير (بلا إنتاج، الراية مطفأة): يُكمِل بالبديل الداخليّ الموسوم — لا فشل."""
    m = _load()
    monkeypatch.delenv("AGRIAI_PRODUCTION_MODE", raising=False)
    monkeypatch.delenv("AQUACROP_ENABLED", raising=False)
    r = m.simulate({"name": "potato"}, {}, {}, {"ec_e_initial": 5.0})
    assert r["provenance"] == "aquacrop_uncalibrated" and r["yield_kg_ha"] >= 0.0
