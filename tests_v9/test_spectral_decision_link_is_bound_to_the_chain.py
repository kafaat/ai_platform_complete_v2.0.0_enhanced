"""‏`SPECTRAL-STALE-DECISION-LINKED-CLAIMS-01` — الوسم `decision_linked ✓` يجب أن يُقاس.

`spectral_stress_bridge.index_coverage_report()` يَسِم NDMI وMSI بـ`decision_linked ✓`،
و`band_math.msi` يقول في docstring إنّ MSI «يُستهلَك في تأكيد الإجهاد الطيفيّ». والاختبار
القائم (`tests/test_spectral_stress_bridge.py:84-85`) يؤكّد أنّ المفتاحين **موجودان في
القاموس الذي تكتبه الوحدة نفسها** — أي يفحص إعلاناً بإعلانه. تلك حلقة مغلقة: لو انقطعت
السلسلة غداً لبقي الوسم أخضر والاختبار أخضر.

هذا الملفّ يربط الوسم بالمسار الفعليّ الذي يجعله صادقاً:

    imagery_automation يكتب last_ndmi_mean/last_msi_mean   (الكاتب — أُصلِح في #749)
      ⇒ field_state_projection يقرأ العمودين
        ⇒ canonical_water_stress يدمجهما عبر fuse_water_stress
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
    }
    base.update(over)
    return base


def test_both_indices_together_produce_a_confirmation(core_on_path):
    """المؤشّران معاً ⇒ تأكيد فعليّ — لا وسم في قاموس بل قيمة في المخرَج."""
    from api.canonical_water_stress import canonical_water_stress

    out = canonical_water_stress(_row())
    assert out["spectral_confirmation_available"] is True
    assert out["spectral_stress_detected"] is not None
    assert out["spectral_confidence"] is not None


@pytest.mark.parametrize("missing", ["ndmi", "msi"])
def test_either_index_missing_kills_the_confirmation(core_on_path, missing):
    """كلاهما مطلوب: غياب أيّهما ⇒ لا تأكيد ولا كشف — «فيزياء + رصد» بلا تصعيد بلا رصد."""
    from api.canonical_water_stress import canonical_water_stress

    out = canonical_water_stress(_row(**{missing: None}))
    assert out["spectral_confirmation_available"] is False
    assert out["spectral_stress_detected"] is None


def test_incompatible_acquisition_dates_kill_the_confirmation(core_on_path):
    """قراءتان من مشهدين متباعدين ليستا تأكيداً — الدمج الزمنيّ غير المتحقَّق fail-closed."""
    from api.canonical_water_stress import (
        SPECTRAL_MAX_DATE_GAP_DAYS,
        canonical_water_stress,
    )

    out = canonical_water_stress(_row(msi_date="2026-05-01"))
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
    """conn وهميّ يُجيب **فقط** الاستعلام الذي يطلب العمودين الطيفيّين.

    هذا هو جوهر الربط: لو توقّف الإسقاط عن اختيار ``last_ndmi_mean``/``last_msi_mean``
    فلن يُطابق هذا الشرط، فيعود ``None`` وتسقط سلسلة التأكيد — يفشل الاختبار **سلوكيّاً**
    لا نصّيّاً. (الصيغة النصّيّة وحدها تمرّ ما دام الاسم مذكوراً في أيّ مكان من الملفّ،
    وقد اكتشفتُ ذلك بتكذيب هذا الاختبار نفسه قبل شحنه.)
    """

    def __init__(self, *, ndmi, msi, same_date=True):
        from datetime import date, timedelta

        self._ndmi, self._msi = ndmi, msi
        self._d1 = date(2026, 6, 10)
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


@pytest.mark.asyncio
async def test_the_projection_actually_feeds_the_columns_into_the_fusion(core_on_path):
    """الحلقة التي كانت مقطوعة، مفحوصة **سلوكيّاً**: من العمودين إلى التأكيد.

    القيمتان لا تصلان الدمج إلّا إذا اختار الإسقاط العمودين فعلاً. ولذلك يُجيب الـconn
    الوهميّ ذلك الاستعلام وحده: انقطاع الاختيار ⇒ لا صفّ ⇒ لا تأكيد ⇒ فشل مسموع.
    """
    from api.field_state_projection import recompute_field_state

    conn = _Conn(ndmi=0.05, msi=1.9)
    result = await recompute_field_state(conn, "fld_1")
    assert conn.spectral_query_seen, "الإسقاط لم يعد يستعلم عن العمودين الطيفيّين"
    water = result["state"].get("water_stress") or {}
    assert water.get("spectral_confirmation_available") is True, (
        "العمودان يصلان الاستعلام ولا يصلان الدمج — الوسم decision_linked صار ادّعاءً"
    )


@pytest.mark.asyncio
async def test_the_projection_chain_dies_when_one_column_is_empty(core_on_path):
    """نفس المسار بقيمة ناقصة ⇒ لا تأكيد. يُثبِت أنّ النجاح أعلاه ليس ثابتاً محفوراً."""
    from api.field_state_projection import recompute_field_state

    result = await recompute_field_state(_Conn(ndmi=0.05, msi=None), "fld_1")
    water = result["state"].get("water_stress") or {}
    assert water.get("spectral_confirmation_available") is False


def test_the_bridge_label_and_the_chain_agree(core_on_path):
    """الوسم والسلسلة يُفحَصان **معاً**: العضويّة وحدها حلقة مغلقة تفحص إعلاناً بإعلانه."""
    from core.engines.spectral_stress_bridge import index_coverage_report

    linked = index_coverage_report()["decision_linked"]
    assert "ndmi" in linked and "msi" in linked
    source = PROJECTION.read_text(encoding="utf-8")
    assert "last_ndmi_mean" in source and "last_msi_mean" in source, (
        "الوسم يدّعي ربطاً بقرار بينما الإسقاط لا يقرأ المؤشّرين — ادّعاء بلا مسار"
    )


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
