"""‏`SPECTRAL-STALE-DECISION-LINKED-CLAIMS-01` — الوسم `decision_linked ✓` يجب أن يُقاس.

`spectral_stress_bridge.index_coverage_report()` يَسِم NDMI وMSI بـ`decision_linked ✓`،
و`band_math.msi` يقول في docstring إنّ MSI «يُستهلَك في تأكيد الإجهاد الطيفيّ». والاختبار
القائم (`tests/test_spectral_stress_bridge.py:84-85`) يؤكّد أنّ المفتاحين **موجودان في
القاموس الذي تكتبه الوحدة نفسها** — أي يفحص إعلاناً بإعلانه. تلك حلقة مغلقة: لو انقطعت
السلسلة غداً لبقي الوسم أخضر والاختبار أخضر.

هذا الملفّ يربط الوسم بالمسار الفعليّ الذي يجعله صادقاً:

    raster-service يعيد قيمة وجودة ومصدر كل مؤشر
      ⇒ canonical_spectral_state يتحقق من الجودة وهوية النطاق
        ⇒ field_state_projection يمرر المنتج إلى canonical_water_stress
          ⇒ fuse_water_stress يدمج المؤشرين بعد سياسة العمر
          ⇒ spectral_confirmation_available/spectral_stress_detected في الحالة القانونيّة

وحدّ الصدق مكتوب في الاختبارات نفسها: هذه تُثبِت أنّ **الوصل قائم ومشروط**، لا أنّ
الأعمدة تُملأ في بيئة حيّة. البرهان التشغيليّ يبقى مفتوحاً.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "services" / "sahool-platform"
PROJECTION = CORE / "api" / "field_state_projection.py"
STRESS = CORE / "api" / "canonical_water_stress.py"


@pytest.fixture(scope="module")
def core_on_path():
    if str(CORE) not in sys.path:
        sys.path.insert(0, str(CORE))
    pytest.importorskip("fastapi")


def _row(**over):
    base = {
        "depletion_mm": 95.0,
        "taw_mm": 100.0,
        "raw_fraction": 0.5,
        "depletion_confidence": 0.9,
        "ndmi": 0.05,
        "msi": 1.9,
        "ndmi_date": "2026-06-10",
        "msi_date": "2026-06-10",
        "quality_status": "validated",
    }
    base.update(over)
    return base


def test_both_indices_together_produce_a_confirmation(core_on_path):
    """زوج موثوق ضمن سياسة عمر صريحة ⇒ تأكيد فعليّ، لا مجرد وجود قيمتين."""
    from api.canonical_water_stress import canonical_water_stress

    out = canonical_water_stress(_row(), as_of="2026-06-10", max_spectral_age_days=12)
    assert out["spectral_confirmation_available"] is True
    assert out["spectral_stress_detected"] is not None
    assert out["spectral_confidence"] is not None


@pytest.mark.parametrize("missing", ["ndmi", "msi"])
def test_either_index_missing_kills_the_confirmation(core_on_path, missing):
    """كلاهما مطلوب: غياب أيّهما ⇒ لا تأكيد ولا كشف — «فيزياء + رصد» بلا تصعيد بلا رصد."""
    from api.canonical_water_stress import canonical_water_stress

    out = canonical_water_stress(
        _row(**{missing: None}), as_of="2026-06-10", max_spectral_age_days=12
    )
    assert out["spectral_confirmation_available"] is False
    assert out["spectral_stress_detected"] is None


def test_incompatible_acquisition_dates_kill_the_confirmation(core_on_path):
    """قراءتان من مشهدين متباعدين ليستا تأكيداً — الدمج الزمنيّ غير المتحقَّق fail-closed."""
    from api.canonical_water_stress import (
        SPECTRAL_MAX_DATE_GAP_DAYS,
        canonical_water_stress,
    )

    out = canonical_water_stress(
        _row(msi_date="2026-05-01"), as_of="2026-06-10", max_spectral_age_days=12
    )
    assert out["spectral_date_gap_days"] > SPECTRAL_MAX_DATE_GAP_DAYS
    assert out["spectral_confirmation_available"] is False
    assert out["spectral_temporal_compatible"] is False


def test_the_fusion_is_the_bridge_not_a_local_reimplementation(core_on_path):
    """التأكيد يمرّ بـ``fuse_water_stress`` نفسه — وإلّا صار الوسم يصف جسراً غير مُستعمَل."""
    tree = ast.parse(STRESS.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "core.engines.spectral_stress_bridge"
        for alias in node.names
    }
    assert "fuse_water_stress" in imported
    called = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "fuse_water_stress"
    ]
    assert called, "الجسر مُستورَد ولا يُستدعى — استيراد بلا استهلاك"


class _NoopTx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


class _Conn:
    """Legacy cached columns remain present but cannot substitute Raster QA."""

    def __init__(self, *, ndmi, msi, same_date=True):
        from datetime import date, timedelta

        self._ndmi, self._msi = ndmi, msi
        self._d1 = date.today()
        self._d2 = self._d1 if same_date else self._d1 - timedelta(days=40)
        self.spectral_query_seen = False

    def transaction(self):
        return _NoopTx()

    async def fetchrow(self, sql, *a):
        if "last_ndmi_mean" in sql and "last_msi_mean" in sql:
            self.spectral_query_seen = True
            return {
                "last_ndmi_mean": self._ndmi,
                "last_msi_mean": self._msi,
                "last_ndmi_date": self._d1,
                "last_msi_date": self._d2,
            }
        if "FROM water_ledger" in sql:
            # الأعمدة الثلاثة التي يقرأها الإسقاط فعلاً (لا شكل مُتخيَّل):
            # depletion_mm · soil_moisture_pct · confidence
            return {"depletion_mm": 95.0, "soil_moisture_pct": 11.0, "confidence": 0.9}
        return None

    async def fetchval(self, sql, *a):
        return "t1" if "FROM fields" in sql else None

    async def fetch(self, sql, *a):
        return []

    async def execute(self, sql, *a):
        return None


def _raster_transport(monkeypatch, conn, *, quality="validated", age_days=0):
    from datetime import timedelta

    import api.raster_service_client as transport

    calls = []

    async def grid(field_id, **kwargs):
        assert field_id == "fld_1" and kwargs["tenant_id"] == "t1"
        index = kwargs["index"]
        calls.append(index)
        day = conn._d2 if index == "msi" else conn._d1
        return {
            "field_id": field_id,
            "tenant_id": kwargs["tenant_id"],
            "real_data": True,
            "source": "sentinel-2",
            "quality_status": quality,
            "date": (day - timedelta(days=age_days)).isoformat(),
            "stats": {
                "mean": {"ndvi": 0.5, "ndre": 0.2, "ndmi": conn._ndmi, "msi": conn._msi}[index]
            },
            "product_id": "product:" + index,
            "scene_id": "scene-fixture",
        }

    monkeypatch.setattr(transport, "get_indicator_grid", grid)
    return calls


@pytest.mark.asyncio
async def test_the_projection_feeds_validated_products_into_the_fusion(core_on_path, monkeypatch):
    """Real resolver and projection; only provider transport and DB are doubled."""
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndmi=0.05, msi=1.9)
    calls = _raster_transport(monkeypatch, conn)
    result = await recompute_field_state(conn, "fld_1")
    water = result["state"].get("water_stress") or {}
    assert set(calls) == {"ndvi", "ndre", "ndmi", "msi"}
    assert len(calls) == 4
    assert water.get("spectral_confirmation_available") is True
    assert water["spectral_quality_status"] == "validated"
    assert {"product:ndmi", "product:msi"} <= set(water["spectral_evidence_ids"])
    assert water["spectral_freshness"]["verified"] is True


@pytest.mark.asyncio
async def test_the_projection_chain_dies_when_one_column_is_empty(core_on_path, monkeypatch):
    """Same path with a missing Raster index must not confirm."""
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndmi=0.05, msi=None)
    _raster_transport(monkeypatch, conn)
    result = await recompute_field_state(conn, "fld_1")
    water = result["state"].get("water_stress") or {}
    assert water.get("spectral_confirmation_available") is False


@pytest.mark.asyncio
async def test_legacy_columns_without_raster_evidence_cannot_confirm(core_on_path, monkeypatch):
    import api.raster_service_client as transport
    from api.field_state_projection import recompute_field_state

    async def absent(*args, **kwargs):
        return None

    monkeypatch.setattr(transport, "get_indicator_grid", absent)
    conn = _Conn(ndmi=0.05, msi=1.9)
    result = await recompute_field_state(conn, "fld_1")
    assert conn.spectral_query_seen
    water = result["state"]["water_stress"]
    assert water["spectral_confirmation_available"] is False
    assert water["escalation_eligible"] is False


@pytest.mark.parametrize("quality,age_days", [("unknown", 0), ("validated", 13)])
@pytest.mark.asyncio
async def test_projection_rejects_unqualified_or_stale_products(
    core_on_path, monkeypatch, quality, age_days
):
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndmi=0.05, msi=1.9)
    _raster_transport(monkeypatch, conn, quality=quality, age_days=age_days)
    water = (await recompute_field_state(conn, "fld_1"))["state"]["water_stress"]
    assert water["spectral_confirmation_available"] is False
    assert water["escalation_eligible"] is False


def test_the_bridge_label_and_the_chain_agree(core_on_path):
    """الوسم والسلسلة يُفحَصان **معاً**: العضويّة وحدها حلقة مغلقة تفحص إعلاناً بإعلانه."""
    from core.engines.spectral_stress_bridge import index_coverage_report

    linked = index_coverage_report()["decision_linked"]
    assert "ndmi" in linked and "msi" in linked
    source = PROJECTION.read_text(encoding="utf-8")
    assert "resolve_canonical_spectral_state" in source and "water_stress_spectral_inputs" in source


def test_the_writer_still_waits_before_it_reads(core_on_path):
    """الطرف الأوّل من السلسلة: الكاتب الذي يملأ العمودين.

    قبل #749 كان ``_trigger_indicators`` يقرأ نتيجة الدفعة **قبل اكتمالها**، فلا يُكتَب
    شيء ويبقى الوسم أخضر. الفحص على AST لا على النصّ: وجود الاسم في الملفّ لا يعني أنّ
    النداء ما يزال في مكانه — لو بقي التعريف وحُذِف الاستدعاء لمرّ الفحص النصّيّ.
    القيد هنا على وجود **الاستدعاء داخل الدالّة** وعلى أنّه **يحكم** ما بعده، لا على
    تشغيله حيّاً.
    """
    tree = ast.parse((CORE / "api" / "imagery_automation.py").read_text(encoding="utf-8"))
    trigger = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_trigger_indicators"
    )
    awaited = [
        n
        for n in ast.walk(trigger)
        if isinstance(n, ast.Attribute) and n.attr == "_await_batch_terminal"
    ]
    assert awaited, "زال انتظار اكتمال الدفعة من _trigger_indicators — تعود القراءة قبل الأوان"

    guarded = [
        n
        for n in ast.walk(trigger)
        if isinstance(n, ast.If)
        and any(
            isinstance(sub, ast.Attribute) and sub.attr == "_await_batch_terminal"
            for sub in ast.walk(n.test)
        )
    ]
    assert guarded, "الانتظار يُستدعى ولا تُحكَم به القراءة — نتيجة مُهمَلة تعادل غيابه"
    assert any(isinstance(stmt, ast.Return) for stmt in guarded[0].body), (
        "الانتظار الفاشل لا يمنع القراءة — النداء الذي يُعرَف سلفاً أنّه سيصطدم بـ404 ضجيج"
    )


def test_the_honesty_limit_is_not_overstated():
    """حدّ صريح: هذا الملفّ يُثبِت الوصل، لا الملء الحيّ.

    يُثبَّت نصّاً كي لا يُقرأ نجاحه لاحقاً على أنّه شهادة تشغيليّة — وهو الفرق الذي
    ضاع أوّل مرّة حين سُجِّل «المسار موجود» بدل «المسار يعمل».
    """
    assert "البرهان التشغيليّ يبقى مفتوحاً" in Path(__file__).read_text(encoding="utf-8")


def test_module_paths_are_real(core_on_path):
    for path in (PROJECTION, STRESS):
        assert path.is_file(), f"{os.path.relpath(path, ROOT)} — مسار بائت في الاختبار نفسه"
