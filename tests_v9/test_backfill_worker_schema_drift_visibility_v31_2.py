"""حارس ساكن: عامل فحص backfill يُظهر انحراف المخطّط بوضوح (بلاغ «عالق في planned»).

الجذر (بلاغ حيّ): تشغيلات backfill تبقى عالقة في ``planned`` والخطّ الزمنيّ يُظهر الشهر
الحاليّ فقط. أحد الأسباب الصامتة: استعلام المطالبة يشير إلى عمود مضاف لاحقاً (``source``،
v147) غير موجود في قاعدة متأخّرة عن الترحيل ⇒ يفشل كلّ دورة. الحلقة كانت تبتلع كلّ استثناء
عند ``warning`` فيبقى العلوق بلا إشارة تشخيصيّة.

هذا الحارس (ساكن — نمط tests_v9) يمنع الانحدار: أخطاء المخطّط الدائمة تُصعَّد إلى ERROR
بتلميح للترحيل، وتبقى الأخطاء العابرة عند warning، وسكربت التشخيص المصاحب موجود.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
WORKER = REPO / "services" / "raster-service" / "backfill_scan_worker.py"
DIAG = REPO / "scripts" / "diagnose_backfill_stuck.py"


def test_worker_escalates_schema_drift_to_error_with_hint() -> None:
    src = WORKER.read_text(encoding="utf-8")
    # يلتقط أخطاء المخطّط الدائمة تحديداً (لا Exception عامّ فقط).
    assert "asyncpg.UndefinedColumnError" in src
    assert "asyncpg.UndefinedTableError" in src
    # يُسجّلها عند ERROR بتلميح صريح للترحيل + سبب العلوق.
    assert "logger.error(" in src
    assert "planned" in src
    assert "migration" in src.lower()


def test_worker_keeps_transient_errors_at_warning() -> None:
    src = WORKER.read_text(encoding="utf-8")
    # الفرع العابر (قاعدة تُقلِع) يبقى عند warning كي لا يضجّ ERROR عند الإقلاع الطبيعيّ.
    assert "cycle skipped (transient" in src
    assert "logger.warning(" in src


def test_diagnostic_script_present_and_readonly() -> None:
    assert DIAG.exists(), "سكربت تشخيص العلوق مفقود"
    src = DIAG.read_text(encoding="utf-8")
    # للقراءة فقط: لا UPDATE/DELETE/INSERT على backfill_runs، ومحاكاة المطالبة بـROLLBACK.
    assert "UPDATE backfill_runs" not in src
    assert "DELETE FROM backfill_runs" not in src
    assert "tr.rollback()" in src  # يُحاكي دون مطالبة فعليّة
    # يفحص الأسباب الثلاثة.
    assert "RASTER_ASYNC_BACKFILL_ENABLED" in src
    assert "column_name='source'" in src
