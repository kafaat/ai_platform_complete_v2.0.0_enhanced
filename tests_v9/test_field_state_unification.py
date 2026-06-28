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

    def __init__(
        self,
        *,
        ndvi_mean,
        ec,
        boundary_confidence=None,
        depletion_mm=None,
        depletion_confidence=0.9,
        ndmi=None,
        msi=None,
    ):
        self._ndvi = ndvi_mean
        self._ec = ec
        self._boundary_confidence = boundary_confidence
        self._depletion_mm = depletion_mm
        self._depletion_confidence = depletion_confidence
        self._ndmi = ndmi
        self._msi = msi
        self.executed = []
        self._today = date.today()

    def transaction(self):
        return _Tx()

    async def fetchrow(self, sql, *a):
        if "last_ndmi_mean" in sql:  # D2b: المؤشّرات الطيفيّة (v99)
            return {"last_ndmi_mean": self._ndmi, "last_msi_mean": self._msi}
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
        if "FROM water_ledger" in sql:  # Bundle D/D2: استنزاف (None ⇒ لا كتلة)
            if self._depletion_mm is None:
                return None
            return {
                "depletion_mm": self._depletion_mm,
                "soil_moisture_pct": None,
                "confidence": self._depletion_confidence,
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


@pytest.mark.asyncio
async def test_water_stress_block_present_no_escalation(core_on_path):
    """Bundle D/D2a: استنزاف مخزَّن ⇒ كتلة water_stress معلوماتيّة **بلا تصعيد** (محفوظ السلوك)."""
    from api.field_state_projection import recompute_field_state

    # TAW الاحتياطيّ = 150×0.6 = 90 مم؛ Dr=81 ⇒ AWF=0.1 ≤ 0.2 ⇒ critical — ومع ذلك لا تصعيد (D2a).
    conn = _Conn(ndvi_mean=0.7, ec=1.0, depletion_mm=81.0)
    res = await recompute_field_state(conn, "fld_1")
    st = res["state"]
    assert "water_stress" in st
    assert st["water_stress"]["water_stress_class"] == "critical"
    assert st["water_stress"]["calibrated"] is False
    assert st["water_stress"]["source"] == "field_state.canonical"
    # بلا تأكيد طيفيّ (ndmi/msi غائبان) ⇒ غير مؤهَّل ⇒ لا تصعيد (نمط D2b: فيزياء+رصد).
    assert st["water_stress"]["escalation_eligible"] is False
    assert st["execution_mode"] == "auto"


@pytest.mark.asyncio
async def test_no_water_ledger_no_water_stress_block(core_on_path):
    """Bundle D/D2a: لا استنزاف مخزَّن ⇒ لا كتلة water_stress (صدق: لا قرار على غياب)."""
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndvi_mean=0.7, ec=1.0, depletion_mm=None)
    res = await recompute_field_state(conn, "fld_1")
    assert "water_stress" not in res["state"]


@pytest.mark.asyncio
async def test_readiness_block_present_and_informational(core_on_path):
    """مؤشّر الجاهزيّة يُسقَط على الحالة (درجة+مستوى+مصدر) ولا يغيّر القرار (معلوماتيّ)."""
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndvi_mean=0.7, ec=1.0)
    st = (await recompute_field_state(conn, "fld_1"))["state"]
    assert "readiness" in st
    rd = st["readiness"]
    assert isinstance(rd["overall_score"], (int, float))
    assert rd["level"] in ("excellent", "good", "fair", "poor", "insufficient")
    assert rd["source"] == "field_state.canonical"
    assert "dimensions" in rd and "actionable_ar" in rd
    # معلوماتيّ صرف: لا يلمس القرار القانونيّ
    assert st["execution_mode"] == "auto"


# ── D2b: تصعيد الإجهاد المائيّ خلف feature flag (NDMI+MSI) ──
# إجهاد طيفيّ شديد: NDMI=-0.1 (<0.0 severe) + MSI=2.5 (≥2.0 severe) ⇒ fused severe ⇒ detected.
_SPECTRAL_STRESS = {"ndmi": -0.1, "msi": 2.5}


@pytest.mark.asyncio
async def test_d2b_flag_off_eligible_but_not_triggered(core_on_path, monkeypatch):
    """D2b: العلم OFF (افتراضيّ) ⇒ أهليّة معلنة لكن لا تصعيد + سبب التعطيل (محفوظ السلوك)."""
    from api.field_state_projection import recompute_field_state

    monkeypatch.delenv("FEATURE_WATER_STRESS_ESCALATION", raising=False)
    # Dr=81/TAW=90 ⇒ AWF=0.1 critical · conf=0.9≥0.8 · طيف شديد ⇒ eligible.
    conn = _Conn(
        ndvi_mean=0.7, ec=1.0, depletion_mm=81.0, depletion_confidence=0.9, **_SPECTRAL_STRESS
    )
    st = (await recompute_field_state(conn, "fld_1"))["state"]
    ws = st["water_stress"]
    assert ws["escalation_eligible"] is True
    assert ws["spectral_stress_detected"] is True
    assert ws["escalation_triggered"] is False
    assert ws["disabled_reason"] == "feature_flag_off"
    assert st["execution_mode"] == "auto"  # العلم مطفأ ⇒ لا تصعيد إنتاجيّ


@pytest.mark.asyncio
async def test_d2b_flag_on_escalates(core_on_path, monkeypatch):
    """D2b: العلم ON + الشروط مكتملة ⇒ human_review (المسند المُقَرّ يقع)."""
    from api.field_state_projection import recompute_field_state

    monkeypatch.setenv("FEATURE_WATER_STRESS_ESCALATION", "1")
    conn = _Conn(
        ndvi_mean=0.7, ec=1.0, depletion_mm=81.0, depletion_confidence=0.9, **_SPECTRAL_STRESS
    )
    st = (await recompute_field_state(conn, "fld_1"))["state"]
    ws = st["water_stress"]
    assert ws["escalation_triggered"] is True
    assert ws["disabled_reason"] is None
    assert st["execution_mode"] == "human_review"
    assert st["validity"] != "valid"
    assert any("إجهاد مائيّ" in r for r in st["reasons_ar"])


@pytest.mark.asyncio
async def test_d2b_flag_on_no_spectral_no_escalation(core_on_path, monkeypatch):
    """D2b: العلم ON لكن غياب مؤشّر طيفيّ (msi) ⇒ لا تأكيد ⇒ لا تصعيد (صدق: فيزياء+رصد)."""
    from api.field_state_projection import recompute_field_state

    monkeypatch.setenv("FEATURE_WATER_STRESS_ESCALATION", "1")
    conn = _Conn(
        ndvi_mean=0.7, ec=1.0, depletion_mm=81.0, depletion_confidence=0.9, ndmi=-0.1, msi=None
    )
    st = (await recompute_field_state(conn, "fld_1"))["state"]
    ws = st["water_stress"]
    assert ws["spectral_confirmation_available"] is False
    assert ws["spectral_stress_detected"] is None
    assert ws["escalation_eligible"] is False
    assert st["execution_mode"] == "auto"


@pytest.mark.asyncio
async def test_d2b_flag_on_low_confidence_no_escalation(core_on_path, monkeypatch):
    """D2b: العلم ON + طيف شديد لكن ثقة استنزاف < 0.8 ⇒ لا تصعيد (فيزياء غير موثوقة)."""
    from api.field_state_projection import recompute_field_state

    monkeypatch.setenv("FEATURE_WATER_STRESS_ESCALATION", "1")
    conn = _Conn(
        ndvi_mean=0.7, ec=1.0, depletion_mm=81.0, depletion_confidence=0.7, **_SPECTRAL_STRESS
    )
    st = (await recompute_field_state(conn, "fld_1"))["state"]
    assert st["water_stress"]["escalation_eligible"] is False
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
