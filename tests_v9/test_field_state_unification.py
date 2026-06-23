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

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

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

    def __init__(self, *, ndvi_mean, ec, boundary_confidence=None):
        self._ndvi = ndvi_mean
        self._ec = ec
        self._boundary_confidence = boundary_confidence
        self.executed = []
        self._today = date.today()

    def transaction(self):
        return _Tx()

    async def fetchrow(self, sql, *a):
        if "imagery_automation_fields" in sql:
            return {"last_ndvi_mean": self._ndvi, "last_ndvi_date": self._today}
        if "FROM soil_lab_tests" in sql:  # صفّ واحد: sampled_on + result (EC)
            return {"sampled_on": self._today, "result": json.dumps({"ec": self._ec, "ph": 7.5})}
        if "FROM field_boundaries" in sql:  # Bundle B: جودة الحدّ (None ⇒ لا كتلة)
            if self._boundary_confidence is None:
                return None
            return {
                "confidence_score": self._boundary_confidence,
                "source_type": "auto_delineation",
                "model_version": "sam2_hiera_large",
                "review_status": "unreviewed",
            }
        if "FROM field_state" in sql:
            return None
        return None

    async def fetchval(self, sql, *a):
        if "last_image_date FROM imagery_automation_fields" in sql:
            return self._today  # صورة اليوم ⇒ ثقة عالية
        if "weather_automation_cache" in sql:
            return 1.0  # طقس حديث (ساعة)
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


@pytest.mark.asyncio
async def test_low_boundary_confidence_escalates(core_on_path):
    """Bundle B: حدّ منخفض الثقة (< 0.6) ⇒ تصعيد للمراجعة البشريّة رغم سلامة باقي الإشارات."""
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndvi_mean=0.7, ec=1.0, boundary_confidence=0.4)  # لولا الحدّ ⇒ auto
    res = await recompute_field_state(conn, "fld_1")
    st = res["state"]
    # كتلة الحدّ الكنسيّة حاضرة بمصدر مُعلَن + توصية مراجعة
    assert st["boundary"]["boundary_confidence"] == 0.4
    assert st["boundary"]["review_recommended"] is True
    assert st["boundary"]["source"] == "field_state.canonical"
    # التصعيد: ثقة الحدّ المنخفضة تَحكُم (نظير الملوحة) — مراجعة بشريّة
    assert st["execution_mode"] == "human_review"
    assert st["validity"] != "valid"
    assert any("حدّ" in r for r in st["reasons_ar"])


@pytest.mark.asyncio
async def test_high_boundary_confidence_does_not_escalate(core_on_path):
    """Bundle B: حدّ عالي الثقة (≥ 0.6) ⇒ كتلة حاضرة بلا تصعيد (سلوك محفوظ)."""
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndvi_mean=0.7, ec=1.0, boundary_confidence=0.95)
    res = await recompute_field_state(conn, "fld_1")
    st = res["state"]
    assert st["boundary"]["boundary_confidence"] == 0.95
    assert st["boundary"]["review_recommended"] is False
    assert st["execution_mode"] == "auto"  # لا تصعيد


@pytest.mark.asyncio
async def test_no_boundary_row_no_block_no_escalation(core_on_path):
    """Bundle B: لا صفّ حدّ مُهدَّف ⇒ لا كتلة boundary ولا تصعيد (صدق: لا تصعيد على غياب)."""
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndvi_mean=0.7, ec=1.0, boundary_confidence=None)
    res = await recompute_field_state(conn, "fld_1")
    st = res["state"]
    assert "boundary" not in st  # لا ثقة مخزَّنة ⇒ لا كتلة مُلفّقة
    assert st["execution_mode"] == "auto"


def test_v55_migration_in_manifest_before_append_only():
    manifest = os.path.join(ROOT, "migrations", "MANIFEST.txt")
    with open(manifest, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    assert "v55_field_state_agronomic.sql" in lines
    assert lines.index("v55_field_state_agronomic.sql") < lines.index(
        "v9_append_only_enforcement.sql"
    )
    assert os.path.exists(os.path.join(ROOT, "migrations", "v55_field_state_agronomic.sql"))


def test_extract_ec_tolerant_keys(core_on_path):
    from api.field_state_projection import _extract_ec

    assert _extract_ec('{"ec": 4.2}') == 4.2
    assert _extract_ec({"ec_ds_m": 3.1}) == 3.1
    assert _extract_ec({"ph": 7}) is None  # لا EC ⇒ None
    assert _extract_ec(None) is None
    assert _extract_ec("{bad json") is None
