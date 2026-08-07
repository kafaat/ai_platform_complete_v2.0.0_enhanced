#!/usr/bin/env python3
"""عقد ``BACKFILL-FAILURE-REASON-DISCARDED-01`` — «فشل» بلا سبب ليس تشخيصاً.

المقيس على ``62667ffd``: ``_process_scene_index`` كان يُرجِع ``bool``. ثلاث حالات فشل
متمايزة تنهار إلى ``False`` واحد — استثناء · وظيفة لم تكتمل · **عولجت ولم تُحفَظ** —
والسبب يُسجَّل في سجلّ العامل ثمّ **يُرمى**. ثمّ يكتب المُستدعي ``status='failed'`` ويترك
``backfill_run_items.error`` (عمودٌ قائم منذ ``v144``) ``NULL``.

**وتصحيح لصيغة أولى من هذا النصّ:** قالت إنّ ``get_backfill_run_status`` «يختار ``error``
صراحةً» فالواجهة تنتظر سبباً. ذلك صحيحٌ عن ``backfill_runs.error`` — خطأ **التشغيلة** —
لا عن عمود العنصر. وبالقياس على الشجرة وقتها: **لا استعلام واحد** يختار
``backfill_run_items.error``. فالشريحة كانت ستكتب تشخيصاً لا يقرؤه أحد — الدين الصامت
نفسه، طبقةً أعلى. أُضيف القارئ هنا (``failed_items``)، والمُشغِّل يرى «٣ فاشلة» بأسبابها
بدل أن يُحال إلى سجلّات حاوية قد تكون دُوِّرت.

**والدليل أنّ الكاتب عرف أهمّيّة الحقل:** مسار «المشهد غير موجود في الكتالوج» يكتب سبباً
صريحاً (``scene_not_found_in_catalog_for_date``). المسار العامّ وحده هو الذي لا يكتب —
وهو الذي تمرّ منه كلّ حالات الفشل الحقيقيّة.

يُثبَّت هنا **بالمصدر المُحلَّل** لا بمطابقة نصّ: كلّ ``UPDATE`` يضع
``backfill_run_items`` على ``failed`` يجب أن يضع ``error`` في العبارة نفسها.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "services/raster-service/backfill_scan_worker.py"
PERSIST = ROOT / "services/raster-service/db_persist.py"


def _sql_literals(path: Path) -> list[str]:
    """كلّ سلسلة نصّيّة في الملفّ، بعد ضمّ السلاسل المتجاورة — لأنّ عبارات SQL هنا
    مقسومة على أسطر، ومطابقةُ سطرٍ واحد كانت ستفوّت ``error=$3`` في السطر التالي."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            try:
                folded = ast.literal_eval(node)
            except (ValueError, SyntaxError, TypeError):
                continue
            if isinstance(folded, str):
                out.append(folded)
    return out


def _failed_item_updates(path: Path) -> list[str]:
    """عبارات ``UPDATE backfill_run_items`` التي تُنتِج الحالة ``failed``."""
    found = []
    for text in _sql_literals(path):
        flat = " ".join(text.split())
        if not re.search(r"UPDATE\s+backfill_run_items\s+SET", flat, re.I):
            continue
        if "failed" in flat or re.search(r"status\s*=\s*\$\d", flat):
            found.append(flat)
    return found


def test_every_failed_item_update_also_writes_a_reason():
    """الخاصّيّة العامّة: مسارُ فشلٍ جديد لا يستطيع أن يُسقِط السبب صامتاً."""
    updates = _failed_item_updates(WORKER)
    assert updates, "لا عبارة UPDATE مُكتشَفة — الحارس بلا عين"
    for flat in updates:
        assert re.search(r"\berror\s*=", flat), (
            f"يضع الحالة ولا يضع سبباً — «فشل» بلا تشخيص:\n    {flat}"
        )


def _select_statements(path: Path) -> list[str]:
    """كلّ ``SELECT`` في الملفّ، مُسطَّحاً — مشتقّاً من السلاسل المُحلَّلة لا من الأسطر."""
    out = []
    for text in _sql_literals(path):
        flat = " ".join(text.split())
        if re.match(r"^\s*SELECT\b", flat, re.I):
            out.append(flat)
    return out


def test_the_read_side_selects_the_item_column_this_write_side_fills():
    """**الصيغة الأولى طابقت الجدول الخطأ — وهي عطل هذه الشريحة بعينه، ارتكبتُه أنا.**

    كان الفحص ``…\\berror\\b…FROM\\s+backfill_runs`` ويمرّ. لكنّ ``backfill_runs.error``
    خطأ **التشغيلة**، مقروءٌ منذ ``v144``؛ والعمود الذي تملؤه هذه الشريحة هو
    ``backfill_run_items.error`` — **جدولٌ آخر يحمل الاسم نفسه**. فبرهانُ «جانب القراءة
    مبنيٌّ على وجوده» كان يخصّ عموداً غير الذي يُكتَب.

    وقياسٌ على الشجرة وقتها: **لا استعلام واحد** في ``services/`` يختار
    ``backfill_run_items.error``؛ التجميع الوحيد على الجدول كان
    ``SELECT status, count(*) … GROUP BY status`` — يعدّ الحالات ولا يقرأ سبباً. أي أنّ
    الشريحة كانت ستكتب تشخيصاً **لا يصل إلى أحد**: الدين الصامت الذي تدّعي إغلاقه.

    فالفحص الآن يُلزِم ``SELECT`` **من ``backfill_run_items`` نفسه** يحمل ``error``.
    """
    statements = _select_statements(PERSIST)
    assert statements, "لا عبارة SELECT مُكتشَفة — الحارس بلا عين"
    item_reads = [
        s
        for s in statements
        if re.search(r"\bFROM\s+backfill_run_items\b", s, re.I)
        and re.search(r"(^|,|\s)error(\s|,|$)", s, re.I)
    ]
    assert item_reads, (
        "لا استعلام يقرأ backfill_run_items.error — العمود يُكتَب ولا يُقرأ:\n  "
        + "\n  ".join(statements[:8])
    )


def test_the_run_level_error_is_a_different_column_and_still_read():
    """الجدولان يحملان عموداً بالاسم نفسه؛ وخلطُهما هو ما أوقع الفحص السابق.

    فيُثبَّت الاثنان منفصلين: خطأ التشغيلة من ``backfill_runs``، وسبب العنصر من
    ``backfill_run_items``. سقوطُ أحدهما لا يُخفيه الآخر.
    """
    statements = _select_statements(PERSIST)
    run_reads = [
        s
        for s in statements
        if re.search(r"\bFROM\s+backfill_runs\b", s, re.I)
        and re.search(r"(^|,|\s)error(\s|,|$)", s, re.I)
    ]
    assert run_reads, "خطأ التشغيلة لم يعد يُقرأ — انحدار في جانب القراءة"


def _load_worker():
    sys.path.insert(0, str(ROOT / "services/raster-service"))
    spec = importlib.util.spec_from_file_location("_backfill_scan_worker", WORKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_PROJECT_MODULES = {
    "raster_api_models",
    "raster_backfill_scene_processing",
    "raster_date_geo",
    "raster_processing_runtime",
    "raster_runtime_state",
    "db_persist",
}


@pytest.fixture(scope="module")
def worker():
    """يتخطّى عند **غياب تبعيّة طرف ثالث** فقط — ولا يتخطّى عند عطبٍ في مصدر المشروع.

    الصيغة الأولى كانت ``except Exception: skip`` مطلقاً، فزرعةٌ تكسر تعريف
    ``SceneOutcome`` جعلت الاختبارات **تتخطّى** بدل أن تحمرّ: fail-open كامل، وهو صنف
    «الطفرة تُسمّي اختباراً قابلاً للتخطّي» الذي قِيس في هذا المستودع قبلاً. الآن كلّ
    ``SyntaxError``/``TypeError``/عطبٍ في وحدة مشروع يفشل، ولا يُتخطّى إلّا ما لا
    نملكه.
    """
    try:
        return _load_worker()
    except ModuleNotFoundError as exc:
        missing = (exc.name or "").split(".")[0]
        if missing in _PROJECT_MODULES or missing.startswith("raster"):
            raise
        pytest.skip(f"تبعيّة طرف ثالث غائبة: {missing}")


def test_the_outcome_carries_a_reason_not_just_a_boolean(worker):
    """``bool`` لا يتّسع لثلاث حالات؛ والنوع نفسه هو ما يمنع عودتها إلى واحدة."""
    assert worker.SceneOutcome(True).reason is None
    assert worker.SceneOutcome(False, "processed_not_persisted").ok is False
    assert set(worker.SceneOutcome._fields) == {"ok", "reason"}


def test_the_three_failure_modes_are_distinguishable(worker):
    """الحالات الثلاث كانت تنهار إلى ``False`` واحد؛ هنا تُقرأ متمايزةً.

    وأخطرها ``processed_not_persisted``: الصورة عولِجت ولم تدخل ``raster_assets`` —
    عملٌ تمّ وأثرٌ ضاع، وكان لا يُميَّز عن انقطاع شبكة.
    """
    source = WORKER.read_text(encoding="utf-8")
    for reason in ("job_not_completed:", "processed_not_persisted", "exception:"):
        assert f'"{reason}' in source or f"'{reason}" in source, f"حالة {reason} غير مُميَّزة"


def test_the_reason_does_not_carry_the_exception_text(worker):
    """العمود يُقرأ ضمن مستأجِر، ونصّ الاستثناء قد يحمل سلسلة اتّصال.

    نفس قرار ``#796``: رمزٌ ثابت + نوع الاستثناء + مُعرّف ربط في العمود، والتفاصيل
    الكاملة في السجلّ بالمُعرّف نفسه — فيبقى التشخيص ممكناً بلا تسريب.
    """
    source = WORKER.read_text(encoding="utf-8")
    assert 'f"exception:{type(e).__name__}:{correlation_id}"' in source
    assert 'f"exception:{e}"' not in source
    assert "correlation_id" in source
