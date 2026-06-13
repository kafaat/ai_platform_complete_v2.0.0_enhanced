"""Stage E — توحيد النواة الزراعيّة الغنيّة في الحالة القانونيّة (Salinity>Vigor).

يثبّت أنّ recompute_field_state يدمج compose_field_state (النواة الغنيّة) ويُطبّق
تحكيمها فعليّاً: ملوحة تربة حرجة تُصعّد نمط التنفيذ للمراجعة البشريّة رغم خُضرة NDVI
(الملوحة تَحكُم). وأنّ ملوحة منخفضة لا تُصعّد. conn وهميّ بلا قاعدة.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


class _Tx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


class _Conn:
    """conn وهميّ بحقل طازج (ثقة عالية) + NDVI جيّد + EC قابل للضبط."""

    def __init__(self, *, ndvi_mean, ec):
        self._ndvi = ndvi_mean
        self._ec = ec
        self.executed = []
        self._today = date.today()

    def transaction(self):
        return _Tx()

    async def fetchrow(self, sql, *a):
        if "imagery_automation_fields" in sql:
            return {"last_ndvi_mean": self._ndvi, "last_ndvi_date": self._today}
        if "FROM field_state" in sql:
            return None
        return None

    async def fetchval(self, sql, *a):
        if "last_image_date FROM imagery_automation_fields" in sql:
            return self._today  # صورة اليوم ⇒ ثقة عالية
        if "MAX(sampled_on)" in sql:
            return self._today
        if "weather_automation_cache" in sql:
            return 1.0  # طقس حديث (ساعة)
        if "SELECT result FROM soil_lab_tests" in sql:
            return json.dumps({"ec": self._ec, "ph": 7.5})
        if "FROM fields" in sql:
            return "t1"
        return None

    async def execute(self, sql, *a):
        self.executed.append((sql, a))


@pytest.mark.asyncio
async def test_critical_salinity_escalates_despite_good_ndvi(core_on_path):
    """NDVI جيّد + EC حرج (10 dS/m) ⇒ النواة تحكم: تصعيد للمراجعة البشريّة."""
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndvi_mean=0.7, ec=10.0)
    res = await recompute_field_state(conn, "fld_1")
    st = res["state"]
    assert "agronomic" in st
    assert st["agronomic"]["operational_truths"].get("salinity_class") == "critical"
    # التحكيم يَحكُم: رغم خُضرة NDVI، الملوحة الحرجة تُصعّد نمط التنفيذ
    assert st["execution_mode"] == "human_review"
    assert st["validity"] != "valid"
    assert any("ملوحة" in r for r in st["reasons_ar"])


@pytest.mark.asyncio
async def test_low_salinity_does_not_escalate(core_on_path):
    """NDVI جيّد + EC منخفض ⇒ لا تصعيد (النواة مدموجة لكن لا تحكيم حرج)."""
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndvi_mean=0.7, ec=1.0)
    res = await recompute_field_state(conn, "fld_1")
    st = res["state"]
    assert "agronomic" in st  # النواة الغنيّة مدموجة دائماً عند توفّر إشارة
    assert st["agronomic"]["operational_truths"].get("salinity_class") != "critical"
    assert st["execution_mode"] == "auto"  # لا تصعيد


def test_extract_ec_tolerant_keys(core_on_path):
    from api.field_state_projection import _extract_ec

    assert _extract_ec('{"ec": 4.2}') == 4.2
    assert _extract_ec({"ec_ds_m": 3.1}) == 3.1
    assert _extract_ec({"ph": 7}) is None  # لا EC ⇒ None
    assert _extract_ec(None) is None
    assert _extract_ec("{bad json") is None
