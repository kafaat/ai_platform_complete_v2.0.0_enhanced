"""عتبات الملوحة في محوّل AquaCrop == كتلة ``salinity`` في بطاقات المحاصيل (شاهد red→green).

**العطل المقيس:** ``services/agriai-engine/aquacrop_adapter.py`` حمل عتبات ثلاثة محاصيل فقط
وافتراضاً ``(2.0, 10.0)`` لأيّ محصول آخر — يخالف البطاقات (ذرة 1.7/12، طماطم 2.5/9.9)،
فتُحسَب غلّة ملحيّة لمحصولٍ بعتبةٍ لا تسندها بطاقته.

سياق Docker لـagriai-engine (``COPY shared/`` + مجلّد الخدمة) لا يحوي بطاقات المنصّة، فالجدول
مرآة؛ هذا الملفّ يفرض التطابق في الاتّجاهين بالقيم، ويفرض أنّ المحصول بلا مدخل يُرفَض.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_MOD = _ROOT / "services" / "agriai-engine" / "aquacrop_adapter.py"
_PLATFORM = _ROOT / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))


def _load():
    spec = importlib.util.spec_from_file_location("aquacrop_adapter_parity", _MOD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _card_salinity() -> dict[str, tuple[float, float]]:
    from core.crop_cards.loader import list_crop_cards, load_crop_card

    out: dict[str, tuple[float, float]] = {}
    for crop_id in list_crop_cards():
        sal = (load_crop_card(crop_id) or {}).get("salinity") or {}
        a, b = sal.get("threshold_ece_ds_m"), sal.get("slope_pct_per_ds_m")
        if a is not None and b is not None:
            out[crop_id] = (float(a), float(b))
    return out


def test_card_universe_is_measured():
    assert len(_card_salinity()) >= 30


def test_adapter_table_equals_crop_cards_both_directions():
    table = _load()._SALT_TOLERANCE
    cards = _card_salinity()
    assert set(table) == set(cards), {
        "missing_in_adapter": sorted(set(cards) - set(table)),
        "not_in_cards": sorted(set(table) - set(cards)),
    }
    drift = {c: (table[c], cards[c]) for c in cards if table[c] != cards[c]}
    assert not drift, f"عتبة/ميل الملوحة في المحوّل تخالف البطاقة (محوّل، بطاقة): {drift}"


def test_no_default_tolerance_remains():
    assert not hasattr(_load(), "_DEFAULT_TOLERANCE"), "الافتراض (2.0, 10.0) لا يعود"


@pytest.mark.parametrize(("crop", "a", "b"), [("maize", 1.7, 12.0), ("tomato", 2.5, 9.9)])
def test_gap_named_crops_use_card_values(crop, a, b):
    r = _load().simulate({"name": crop, "max_yield_kg_ha": 1000}, {}, {}, {"ec_e_initial": 5.0})
    assert r["available"] is True
    assert (r["salt_profile"]["tolerance_threshold_a"], r["salt_profile"]["tolerance_slope_b"]) == (
        a,
        b,
    )
    assert r["salt_profile"]["ks_salt"] == pytest.approx(1.0 - b / 100.0 * (5.0 - a), abs=1e-4)


@pytest.mark.parametrize("crop", ["dragonfruit", "", None])
def test_crop_without_card_threshold_is_refused(monkeypatch, crop):
    monkeypatch.delenv("AGRIAI_PRODUCTION_MODE", raising=False)
    m = _load()
    r = m.simulate({"name": crop} if crop is not None else None, {}, {}, {"ec_e_initial": 5.0})
    assert r["available"] is False
    assert r["provenance"] == m.SALT_TOLERANCE_UNAVAILABLE
    assert r["yield_kg_ha"] is None
    assert m.SALT_TOLERANCE_UNAVAILABLE in m.AQUACROP_SALT_CAPABILITY.status_enum
