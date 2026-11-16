"""Stage E — توحيد النواة الزراعيّة الغنيّة في الحالة القانونيّة (Salinity>Vigor).

يثبّت أنّ recompute_field_state يدمج compose_field_state (النواة الغنيّة) ويُطبّق
تحكيمها فعليّاً: ملوحة تربة حرجة تُصعّد نمط التنفيذ للمراجعة البشريّة رغم خُضرة NDVI
(الملوحة تَحكُم). وأنّ ملوحة منخفضة لا تُصعّد. conn وهميّ بلا قاعدة.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


def _ec_row(ref, value, *, sampled_on=None, method="saturated_paste"):
    """One ``soil_analyte_candidates(analyte='ec_dsm')`` row, as lab_store returns it."""
    legacy = ref.startswith("soil_lab_tests:")
    return {
        "sampled_on": sampled_on or date.today(),
        "sampled_on_source": "sampled_on",
        "result": json.dumps({"ec": value, "ph": 7.5} if legacy else {"ec_dsm": value}),
        "evidence_ref": ref,
        "method_code": None if legacy else method,
        "age_days": 0.0,
    }


@pytest.fixture(autouse=True)
def ec_candidates(monkeypatch):
    """W1-03: the ECe is read per analyte (lab_store.soil_ece_evidence over
    soil_analyte_candidates). That reader is stubbed at function level: by default the legacy
    row of _Conn (its ``ec``); a test sets ``ec_candidates["rows"]`` for v156 evidence."""
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    import api.lab_store as store

    override: dict = {}

    async def candidates(conn, *, field_id, analyte, tenant_id=None, limit=20):
        if "rows" in override:
            return override["rows"]
        ec = getattr(conn, "_ec", None)
        return [] if ec is None else [_ec_row("soil_lab_tests:soil_t1", ec)]

    monkeypatch.setattr(store, "soil_analyte_candidates", candidates)
    return override


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
        ledger_date=None,
    ):
        self._ledger_date = ledger_date
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
        if "last_ndmi_mean" in sql:  # D2b: المؤشّرات الطيفيّة (v99) + تاريخاهما (WS-D.3b)
            # نفس المشهد ⇒ نفس تاريخ الاكتساب ⇒ متوافقان زمنيّاً (سياسة الدمج).
            return {
                "last_ndmi_mean": self._ndmi,
                "last_msi_mean": self._msi,
                "last_ndmi_date": self._today,
                "last_msi_date": self._today,
            }
        if "imagery_automation_fields" in sql:
            return {"last_ndvi_mean": self._ndvi, "last_ndvi_date": self._today}
        if "FROM soil_lab_tests" in sql:  # W1-03: رأس lab_store — احتياط قديم موسوم (EC)
            return {
                "ref_id": "soil_t1",
                "sampled_on": self._today,
                "sampled_on_source": "sampled_on",
                "source_priority": 0,
                "legacy_result": json.dumps({"ec": self._ec, "ph": 7.5}),
                "legacy_status": "published",
            }
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
                # ledger_date NOT NULL في water_ledger — صفّ اليوم حاضرٌ (≤ 72 س).
                "ledger_date": self._ledger_date or self._today,
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
async def test_stale_ledger_row_is_not_current_water_stress(core_on_path, monkeypatch):
    """أحدث صفّ دفتر أقدم من 72 س ⇒ كتلة غير متاحة بقيد مُعلَن — لا صنف ولا تصعيد حتّى مع العلم."""
    from datetime import timedelta

    from api.field_state_projection import recompute_field_state

    monkeypatch.setenv("FEATURE_WATER_STRESS_ESCALATION", "1")
    conn = _Conn(
        ndvi_mean=0.7,
        ec=1.0,
        depletion_mm=81.0,
        depletion_confidence=0.9,
        ledger_date=date.today() - timedelta(days=5),
        **_SPECTRAL_STRESS,
    )
    st = (await recompute_field_state(conn, "fld_1"))["state"]
    ws = st["water_stress"]
    assert ws["available"] is False
    assert ws["water_stress_class"] is None
    assert ws["limitations"] == ["stale_water_ledger"]
    assert ws["ledger_age_hours"] > 72
    assert ws["escalation_eligible"] is False and ws["escalation_triggered"] is False
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


def _validated_raster_observations(monkeypatch, conn):
    """Replace only Raster transport; exercise the real QA resolver and projection."""
    import api.raster_service_client as transport

    async def grid(field_id, **kwargs):
        assert field_id == "fld_1" and kwargs["tenant_id"] == "t1"
        index = kwargs["index"]
        return {
            "field_id": field_id,
            "tenant_id": kwargs["tenant_id"],
            "real_data": True,
            "source": "sentinel-2",
            "quality_status": "validated",
            "date": conn._today.isoformat(),
            "stats": {
                "mean": {"ndvi": conn._ndvi, "ndre": 0.2, "ndmi": conn._ndmi, "msi": conn._msi}[
                    index
                ]
            },
            "product_id": "product:" + index,
            "scene_id": "scene-fixture",
        }

    monkeypatch.setattr(transport, "get_indicator_grid", grid)


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
    _validated_raster_observations(monkeypatch, conn)
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
    _validated_raster_observations(monkeypatch, conn)
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
    _validated_raster_observations(monkeypatch, conn)
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
    _validated_raster_observations(monkeypatch, conn)
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


def _canonical_analysis(monkeypatch, analysis):
    """W1-03: the lab_store reader stubbed at its own level (the legacy row of _Conn unused)."""
    import api.lab_store as store

    async def latest(conn, *, field_id, tenant_id=None):
        return analysis

    monkeypatch.setattr(store, "latest_approved_soil_analysis", latest)


@pytest.mark.asyncio
async def test_approved_v156_ec_alone_escalates_salinity(core_on_path, monkeypatch, ec_candidates):
    """W1-03 acceptance: an EC approved only in soil_lab_results changes the escalation."""
    from api.field_state_projection import recompute_field_state

    ec_candidates["rows"] = [_ec_row("soil_lab_results:rid-ec", 10.0)]

    _canonical_analysis(
        monkeypatch,
        {
            "source": "soil_lab_results",
            "sampled_on": date.today(),
            "values": {"ec_dsm": 10.0},
            "sampled_on_source": "sampled_on",
            "result_ids": {"ec_dsm": "rid-ec"},
            "ec_other_extract": None,
            "legacy_result": None,
        },
    )
    st = (await recompute_field_state(_Conn(ndvi_mean=0.7, ec=1.0), "fld_1"))["state"]
    assert st["agronomic"]["operational_truths"].get("salinity_class") == "critical", st
    assert st["execution_mode"] == "human_review", "approved v156 EC must escalate"
    assert st["soil_lab"] == {
        "available": True,
        "source": "soil_lab_results",
        "ec_dsm": 10.0,
        "ec_source": "soil_lab_results",
        "ec_result_id": "rid-ec",
        "ec_evidence_ref": "soil_lab_results:rid-ec",
        "ec_sampled_on": date.today().isoformat(),
        "ec_other_extract": None,
        "ec_prior_ece": None,
        "ece_unknown_prior_critical": False,
        "sampled_on_source": "sampled_on",
    }, st["soil_lab"]


@pytest.mark.asyncio
async def test_legacy_fallback_is_labelled_in_field_state(core_on_path):
    from api.field_state_projection import recompute_field_state

    st = (await recompute_field_state(_Conn(ndvi_mean=0.7, ec=10.0), "fld_1"))["state"]
    assert st["soil_lab"]["source"] == "legacy_soil_lab_tests", st["soil_lab"]
    assert st["soil_lab"]["ec_result_id"] is None, "a legacy row has no v156 result_id"


@pytest.mark.asyncio
async def test_no_lab_analysis_is_unavailable_not_zero(core_on_path, monkeypatch, ec_candidates):
    from api.field_state_projection import recompute_field_state

    ec_candidates["rows"] = []

    _canonical_analysis(monkeypatch, None)
    st = (await recompute_field_state(_Conn(ndvi_mean=0.7, ec=10.0), "fld_1"))["state"]
    assert st["soil_lab"] == {
        "available": False,
        "source": None,
        "ec_dsm": None,
        "ec_source": None,
        "ec_result_id": None,
        "ec_evidence_ref": None,
        "ec_sampled_on": None,
        "ec_other_extract": None,
        "ec_prior_ece": None,
        "ece_unknown_prior_critical": False,
        "sampled_on_source": None,
    }, st["soil_lab"]
    assert st["agronomic"]["operational_truths"].get("salinity_class") != "critical", (
        "no lab EC must not become a salinity class"
    )


@pytest.mark.asyncio
async def test_non_ece_ec_is_labelled_and_kept_out_of_salinity(
    core_on_path, monkeypatch, ec_candidates
):
    """An EC 1:5 of 2.0 (≈ ECe 12+) read as ECe would classify 'low' and skip the
    Salinity>Vigor escalation: it must not reach soil_ec, only the labelled block."""
    from api.field_state_projection import recompute_field_state

    ec_candidates["rows"] = [
        _ec_row("soil_lab_results:r15", 2.0, method="soil_water_1_5"),
        _ec_row("soil_lab_tests:soil_t1", 1.0, sampled_on=date(2026, 1, 1)),
    ]
    other = {
        "value_dsm": 2.0,
        "extraction_method": "soil_water_1_5",
        "result_id": "r15",
        "sampled_on": date.today().isoformat(),
        "ece": False,
    }
    _canonical_analysis(
        monkeypatch,
        {
            "source": "soil_lab_results",
            "sampled_on": date.today(),
            "sampled_on_source": "sampled_on",
            "values": {"ph": 8.1},
            "result_ids": {"ph": "rid-ph"},
            "ec_other_extract": other,
            "legacy_result": None,
        },
    )
    st = (await recompute_field_state(_Conn(ndvi_mean=0.7, ec=1.0), "fld_1"))["state"]
    assert st["soil_lab"]["ec_dsm"] is None, f"a non-ECe EC must not be ECe: {st['soil_lab']}"
    assert st["soil_lab"]["ec_other_extract"] == other, "the reading must stay visible, labelled"
    agronomic = st["agronomic"]
    assert agronomic["operational_truths"].get("salinity_class") is None, (
        f"no ECe must mean no salinity class: {agronomic['operational_truths']}"
    )
    assert not [p for p in agronomic["provenance"] if p.get("source") == "soil_ec"], (
        f"no soil_ec may enter the agronomic provenance: {agronomic['provenance']}"
    )


# ── W1-03 review: one ECe rule; a sample without EC never drops an older critical ECe ──


def _ph_only_newest_analysis(monkeypatch):
    """The newest approved sample is pH-only (no EC), collected today."""
    _canonical_analysis(
        monkeypatch,
        {
            "source": "soil_lab_results",
            "sampled_on": date.today(),
            "sampled_on_source": "sampled_on",
            "values": {"ph": 7.9},
            "result_ids": {"ph": "rid-ph"},
            "ec_other_extract": None,
            "legacy_result": None,
        },
    )


@pytest.mark.asyncio
async def test_newer_ph_only_sample_keeps_the_older_critical_ece(
    core_on_path, monkeypatch, ec_candidates
):
    """Older critical ECe (12 dS/m) + newer pH-only sample: the pH-only sample carries no EC,
    so the ECe is still the older one and Salinity>Vigor still escalates (auto ->
    human_review). Before the fix the EC came from the newest sample only and was dropped."""
    from api.field_state_projection import recompute_field_state

    old = date.today() - timedelta(days=20)
    ec_candidates["rows"] = [_ec_row("soil_lab_results:rid-old-ece", 12.0, sampled_on=old)]
    _ph_only_newest_analysis(monkeypatch)
    st = (await recompute_field_state(_Conn(ndvi_mean=0.7, ec=None), "fld_1"))["state"]
    assert st["soil_lab"]["ec_dsm"] == 12.0, f"older ECe dropped by a pH-only sample: {st}"
    assert st["soil_lab"]["ec_result_id"] == "rid-old-ece", st["soil_lab"]
    assert st["soil_lab"]["ec_sampled_on"] == old.isoformat(), (
        "salinity age must come from the ECe's own sample, not the newer pH-only one"
    )
    assert st["agronomic"]["operational_truths"].get("salinity_class") == "critical", st
    assert st["execution_mode"] == "human_review", "critical ECe must keep escalating"
    alerts = _derive_alerts(st)
    assert "salinity_critical" in alerts, alerts


def _derive_alerts(state):
    from api.field_state_projection import _derive_alerts_from_state

    return [a["alert_type"] for a in _derive_alerts_from_state(state)]


@pytest.mark.asyncio
async def test_newer_non_ece_ec_over_critical_prior_ece_still_escalates(
    core_on_path, monkeypatch, ec_candidates
):
    """Older critical ECe + newer EC 1:5: the ECe is unknown (the extract may contradict it),
    so it is not fed as current, but the critical prior is not dropped: human_review and the
    critical alert, with the prior labelled."""
    from api.field_state_projection import recompute_field_state

    ec_candidates["rows"] = [
        _ec_row("soil_lab_results:r15", 0.4, method="soil_water_1_5"),
        _ec_row("soil_lab_results:rid-old-ece", 12.0, sampled_on=date(2026, 1, 1)),
    ]
    _ph_only_newest_analysis(monkeypatch)
    st = (await recompute_field_state(_Conn(ndvi_mean=0.7, ec=None), "fld_1"))["state"]
    soil = st["soil_lab"]
    assert soil["ec_dsm"] is None, f"a non-ECe extract leaves the ECe unknown: {soil}"
    assert soil["ec_other_extract"]["result_id"] == "r15", soil
    assert soil["ec_prior_ece"]["evidence_ref"] == "soil_lab_results:rid-old-ece", soil
    assert soil["ec_prior_ece"]["critical"] is True, soil
    assert soil["ece_unknown_prior_critical"] is True, soil
    assert st["execution_mode"] == "human_review", "a critical prior ECe must not fail open"
    assert any("ECe" in r for r in st["reasons_ar"]), st["reasons_ar"]
    assert "salinity_critical" in _derive_alerts(st)


@pytest.mark.asyncio
async def test_newer_non_ece_ec_over_low_prior_ece_does_not_escalate(
    core_on_path, monkeypatch, ec_candidates
):
    from api.field_state_projection import recompute_field_state

    ec_candidates["rows"] = [
        _ec_row("soil_lab_results:r15", 0.4, method="soil_water_1_5"),
        _ec_row("soil_lab_results:rid-old-ece", 1.0, sampled_on=date(2026, 1, 1)),
    ]
    _ph_only_newest_analysis(monkeypatch)
    st = (await recompute_field_state(_Conn(ndvi_mean=0.7, ec=None), "fld_1"))["state"]
    assert st["soil_lab"]["ece_unknown_prior_critical"] is False, st["soil_lab"]
    assert st["execution_mode"] == "auto", st
    assert "salinity_critical" not in _derive_alerts(st)
