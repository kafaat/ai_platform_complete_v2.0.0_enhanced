"""ONE-BAD-ROW-ABORTS-THE-WHOLE-SIGNAL-CYCLE-01 — الحراسةُ لكلّ صفٍّ لا للدورة.

**العطلُ الذي وُجِد هذا لأجله:** `run_cycle` كان يمرّ على التراكبات بلا حراسةٍ لكلّ
صفّ. فحقلٌ واحدٌ ببياناتٍ فاسدة يرفع استثناءً يخرج من الحلقة كلِّها، وتبقى **بقيّةُ
الحقول بلا إشارات** حتّى الدورة التالية — عقوبةُ صفٍّ واحدٍ تقع على كلّ مستأجرٍ في
الدفعة. وحلقةُ `run` تلتقط الاستثناءَ وتُسجّل «تعذّرت دورة توليد الإشارات» **بلا اسم
الحقل الجاني**، فيتكرّر العطلُ كلَّ دورةٍ بلا مَقودٍ يقود إليه.

والاختبارُ يُثبِت ثلاثةً معاً: الدورةُ تكمل · والناجونَ يُحسَبون · والجاني يُسمّى.
والثالثُ ليس تجميلاً — بلا اسمٍ لا يُغلَق العطلُ أبداً.

ويُستورَد المُشغِّلُ بمسارٍ مع تعويض `asyncpg` و`core.*`: هذا عاملٌ لا خدمةَ ويب،
ولا نُشغّل قاعدةً لاختبارِ منطقِ حلقة.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "services" / "weather-signal-engine" / "src" / "main.py"


def _load_engine():
    """يُحمِّل العامل مع تعويضِ تبعيّتين لا يمسّهما المنطقُ محلَّ الاختبار."""
    stubs = {
        "asyncpg": types.ModuleType("asyncpg"),
        "core": types.ModuleType("core"),
        "core.weather_overlay_pipeline": types.ModuleType("core.weather_overlay_pipeline"),
    }
    stubs["core.weather_overlay_pipeline"].build_signal_records = lambda *a, **k: []
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("wx_signal_engine", SRC)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev


engine = _load_engine()

_GOOD_A = {"tenant_id": "t1", "field_id": "f-good-a"}
_BAD = {"tenant_id": "t1", "field_id": "f-poison"}
_GOOD_B = {"tenant_id": "t2", "field_id": "f-good-b"}


class _Conn:
    async def fetch(self, _sql):
        return [_GOOD_A, _BAD, _GOOD_B]


class _Pool:
    def acquire(self):
        conn = _Conn()

        class _Ctx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()


def _run_with(monkeypatch, processed: list) -> int:
    async def fake_process(_conn, overlay):
        processed.append(overlay["field_id"])
        if overlay["field_id"] == _BAD["field_id"]:
            raise ValueError("عمودٌ فاسدٌ في التراكب")
        return 2

    monkeypatch.setattr(engine, "process_overlay", fake_process)
    return asyncio.run(engine.run_cycle(_Pool()))


def test_a_poison_row_does_not_strip_the_rest_of_the_batch(monkeypatch):
    """الحقلُ الجاني يسقط وحدَه، والباقيان يُعالَجان."""
    processed: list[str] = []
    total = _run_with(monkeypatch, processed)
    assert processed == [_GOOD_A["field_id"], _BAD["field_id"], _GOOD_B["field_id"]], (
        "الدورةُ خرجت عند الصفّ الفاسد بدل أن تتابع"
    )
    assert total == 4, "إشاراتُ الناجين لم تُحسَب (٢ لكلّ حقلٍ ناجح)"


def test_the_offending_field_is_named_in_the_log(monkeypatch, caplog):
    """بلا اسمِ الحقل لا يُغلَق العطل — تكرارُ دورةٍ صامتةٍ ليس تشخيصاً."""
    with caplog.at_level(logging.WARNING, logger="weather-signal-engine"):
        _run_with(monkeypatch, [])
    text = caplog.text
    assert _BAD["field_id"] in text, "الحقلُ الجاني غيرُ مُسمّى في السجلّ"
    assert _BAD["tenant_id"] in text, "المستأجرُ غيرُ مُسمّى في السجلّ"
    assert "1 حقلاً أخفق من 3" in text, "عددُ الإخفاقات لا يُرفَع في نهاية الدورة"


def test_a_clean_batch_logs_no_failure_line(monkeypatch):
    """لا ابتلاعَ ولا ضجيج: صمتُ السجلّ يعني نجاحاً."""

    async def all_good(_conn, _overlay):
        return 1

    monkeypatch.setattr(engine, "process_overlay", all_good)
    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda r: records.append(r.getMessage())  # type: ignore[method-assign]
    engine.log.addHandler(handler)
    try:
        assert asyncio.run(engine.run_cycle(_Pool())) == 3
    finally:
        engine.log.removeHandler(handler)
    assert not [m for m in records if "أخفق" in m]
