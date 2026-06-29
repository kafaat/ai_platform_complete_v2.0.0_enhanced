"""اختبار وحدة لقارئ المياه الكنسيّة (Bundle D / D3) — قراءة صرفة من مصدر واحد، بلا حساب.

يقفل: كتلة `water` تُستخرَج عند توفّر ET0+ETc (مع source مُعلَن)؛ وتغيب (None) عند نقصهما/مدخل غير صالح
— فلا يقرأ المستهلكون قيمة مُلفَّقة، بل من مكان واحد أو يعرفون أنّها غير متاحة بصدق.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

try:
    from api.canonical_water import canonical_water
except Exception:  # noqa: BLE001 — تبعيّات المنصّة غير متوفّرة (بيئة Unit Tests الأدنى)
    pytest.skip("platform/api deps unavailable", allow_module_level=True)


def test_water_block_when_et0_and_etc_present():
    """ET0+ETc موجودان ⇒ كتلة مكتملة بمصدر مُعلَن واحد."""
    truths = {"et0_mm": 7.5, "etc_mm": 6.4, "etc_demand_class": "medium", "kc": 0.85, "x": 1}
    w = canonical_water(truths)
    assert w is not None
    assert w["et0_mm"] == 7.5
    assert w["etc_mm"] == 6.4
    assert w["etc_demand_class"] == "medium"
    assert w["source"] == "field_state.canonical"
    assert "x" not in w  # لا يلتقط إلّا مفاتيح المياه


def test_none_when_core_values_missing():
    """غياب et0 أو etc ⇒ None (لا كتلة جزئيّة مُضلِّلة)."""
    assert canonical_water({"et0_mm": 7.5}) is None  # لا etc
    assert canonical_water({"etc_mm": 6.4}) is None  # لا et0
    assert canonical_water({"et0_mm": None, "etc_mm": None}) is None
    assert canonical_water({}) is None


def test_none_on_invalid_input():
    """مدخل غير قاموس ⇒ None (صدق + fail-safe)."""
    assert canonical_water(None) is None
    assert canonical_water("nope") is None
