"""حارس: عامل فحص backfill يُظهر انحراف المخطّط بوضوح بدل ابتلاعه صامتاً.

الجذر (بلاغ حيّ): تشغيلات backfill تبقى عالقة في ``planned`` والخطّ الزمنيّ يُظهر
الشهر الحاليّ فقط. أحد الأسباب: استعلام المطالبة يشير إلى عمود (مثل ``source``، v147)
غير موجود في قاعدة متأخّرة عن الترحيل ⇒ يفشل كلّ دورة. الحلقة كانت تبتلع كلّ استثناء
عند ``warning`` فيبقى العلوق بلا إشارة تشخيصيّة واضحة.

هذا الحارس يثبت أنّ أخطاء المخطّط الدائمة (``UndefinedColumnError``/``UndefinedTableError``)
تُسجَّل عند ``ERROR`` بتلميح للترحيل، بينما أخطاء الاتّصال العابرة تبقى عند ``warning``.
نقيّ بلا شبكة: نُرقِّع ``run_once`` ليرمي، ونوقف الحلقة بعد دورة واحدة.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

asyncpg = pytest.importorskip(
    "asyncpg", reason="asyncpg is required for schema-drift integration guard"
)
import backfill_scan_worker as bsw  # noqa: E402  — must follow importorskip (needs asyncpg)

pytestmark = pytest.mark.unit


class _StopLoop(Exception):
    pass


def _run_one_cycle(monkeypatch, raise_exc: Exception):
    """يُشغّل دورة واحدة من loop_worker مع run_once يرمي ``raise_exc`` ثمّ يوقف الحلقة."""
    monkeypatch.setattr(bsw, "_enabled", lambda: True)

    async def _fake_connect():
        return object()  # pool وهميّ — لا يُستعمَل قبل الرمي

    monkeypatch.setattr(bsw, "_connect", _fake_connect)

    calls = {"n": 0}

    async def _fake_run_once(_pool):
        calls["n"] += 1
        raise raise_exc

    monkeypatch.setattr(bsw, "run_once", _fake_run_once)

    # أوقف الحلقة بعد أوّل sleep (بعد معالجة الاستثناء ومحاولة إغلاق pool وهميّ).
    async def _fake_sleep(_secs):
        raise _StopLoop

    monkeypatch.setattr(bsw.asyncio, "sleep", _fake_sleep)

    async def _drive():
        with pytest.raises(_StopLoop):
            await bsw.loop_worker()

    asyncio.run(_drive())
    return calls["n"]


def _mk_undefined_column() -> asyncpg.UndefinedColumnError:
    # نُنشئ الاستثناء دون اتّصال فعليّ.
    return asyncpg.UndefinedColumnError('column "source" does not exist')


def test_schema_drift_logged_at_error_with_migration_hint(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="raster-service.backfill_scan_worker")
    n = _run_one_cycle(monkeypatch, _mk_undefined_column())
    assert n == 1
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, "انحراف المخطّط يجب أن يُسجَّل عند ERROR لا warning"
    joined = " ".join(r.getMessage() for r in errors)
    assert "planned" in joined and "migration" in joined.lower()


def test_transient_error_stays_at_warning(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="raster-service.backfill_scan_worker")
    _run_one_cycle(monkeypatch, ConnectionError("DB warming up"))
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not errors, "خطأ اتّصال عابر يجب ألّا يُصعَّد إلى ERROR"
    assert warnings, "خطأ عابر يجب أن يُسجَّل عند warning"
