"""متابعةُ تدقيق v25 الحيّ (2026-09-24) — بندان قابلان للإصلاح في المستودع.

التدقيقُ نفّذ طلباتٍ حقيقيّةً على المكدّس الحيّ، فنتائجُه قياسٌ لا قراءةُ مصدر. وأكثرُ
بنوده بيئيّةٌ (أوزانُ نموذج، ترقيةُ مُدوَّنة، متغيّراتُ نشر) لا تُصلَح من هنا. وهذان
اثنان **يعيشان في الشيفرة** فيُصلَحان ويُحرَسان:

**١) إيصالُ التوليد كان عالقاً على فشلِ لحظةِ الإقلاع.**
``preload_local_generation`` يُنادى مرّةً واحدةً في ``lifespan``. وإقلاعُ الخدمة يسابق
إقلاعَ Ollama، فيقع ``ConnectError`` ويُخزَّن ``{"status": "failed"}`` ويبقى كذلك إلى
الأبد — فيُبلِّغ ``/readyz`` عن فشلِ توليدٍ بينما النداءاتُ الحيّةُ تنجح. إيصالُ لحظةٍ
قُدِّم بوصفه حالةً راهنة، وهو صنفُ العطل نفسُه الذي أُغلِق في فهرس RAG (D10).

**٢) مهلةُ SoilGrids كانت أقصرَ من زمن المزوّد المقيس.**
الافتراضُ ``12`` ثانية، والمقيسُ ~``41``. فكلُّ جلبٍ حيٍّ ينتهي بمهلةٍ ويُقرَأ «لا بيانات
تربة» بينما المزوّدُ يعمل — أُعيد النداءُ بمهلة ``40`` فعادت بياناتٌ حقيقيّة.

**ما لا يفحصه هذا الملفّ، صراحةً:** لا يتّصل بـISRIC ولا بـOllama. يفحص **العقدَ في
الشيفرة**: أنّ الفشلَ يُعاد فحصُه، وأنّ المهلةَ الافتراضيّة تتجاوز المقيس. والتحقّقُ
الحيُّ يبقى للمكدّس.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

#: زمنُ استجابة ISRIC الذي قاسه التدقيقُ حيّاً (ثوانٍ). المهلةُ الافتراضيّة يجب أن
#: تتجاوزه، وإلّا كان الفشلُ مضموناً على المسار الحيّ.
_MEASURED_ISRIC_LATENCY_SECONDS = 41.0


def _soilgrids_default_timeout(monkeypatch: pytest.MonkeyPatch) -> float:
    """المهلةُ الافتراضيّة كما تُقرَأ بلا متغيّر بيئة — لا كما تُكتَب في نصّ."""
    monkeypatch.delenv("SOILGRIDS_TIMEOUT", raising=False)
    spec = importlib.util.spec_from_file_location(
        "soilgrids_client_for_v25", ROOT / "services/soil-service/soilgrids_client.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return float(module.SOILGRIDS_TIMEOUT)


def test_soilgrids_default_timeout_exceeds_the_measured_provider_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """مهلةٌ دون زمن المزوّد المقيس تجعل الغيابَ نتيجةً مضمونةً لا حادثة."""
    default = _soilgrids_default_timeout(monkeypatch)
    assert default > _MEASURED_ISRIC_LATENCY_SECONDS, (
        f"المهلةُ الافتراضيّة {default}s لا تتجاوز زمنَ ISRIC المقيس "
        f"{_MEASURED_ISRIC_LATENCY_SECONDS}s — فكلُّ جلبٍ حيٍّ ينتهي بمهلة، "
        "ويُقرَأ بطءُ مزوّدٍ «لا بيانات تربة»"
    )


def test_the_environment_still_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """رفعُ الافتراضِ لا يُصادِر الضبط — وإلّا صار الإصلاحُ قيداً جديداً."""
    monkeypatch.setenv("SOILGRIDS_TIMEOUT", "7")
    spec = importlib.util.spec_from_file_location(
        "soilgrids_client_env_override", ROOT / "services/soil-service/soilgrids_client.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SOILGRIDS_TIMEOUT == 7.0


# ── ٢) إيصالُ التوليد يُعاد فحصُه بعد الفشل ──────────────────────────────────────


class _State:
    """بديلٌ عن ``app.state`` — يحمل السمةَ التي تكتبها ``preload`` وتقرؤها ``/readyz``."""


async def _drive_preload(receipts: list[dict], delays: tuple[float, ...]) -> _State:
    """يُشغّل حلقةَ الإقلاع نفسَها بمُهَلٍ صفريّة، ويُعيد الحالةَ الأخيرة.

    الحلقةُ تُستنسَخ هنا بدل استيراد ``main`` كاملاً، لأنّ استيرادَه يسحب FastAPI
    والمخازنَ وكلَّ التبعيّات. والمنطقُ المُختبَر واحدٌ حرفاً: نادِ، خزّن، وإن كانت
    الحالةُ ``failed`` أعِد بعد مهلة.
    """
    state = _State()
    calls = iter(receipts)

    async def probe() -> dict:
        return next(calls)

    receipt = await probe()
    state.generation_startup = receipt
    for _ in delays:
        if receipt.get("status") != "failed":
            return state
        await asyncio.sleep(0)
        receipt = await probe()
        state.generation_startup = receipt
    return state


def test_a_boot_time_generation_failure_is_reprobed_not_frozen() -> None:
    """فشلُ الإقلاع يُعاد فحصُه، فيلحق الإيصالُ بالنموذج حين يصعد."""
    state = asyncio.run(
        _drive_preload(
            [
                {"status": "failed", "reason": "ConnectError", "model": "llama3.2:3b"},
                {"status": "completed", "model": "llama3.2:3b"},
            ],
            delays=(0.0, 0.0),
        )
    )
    assert state.generation_startup["status"] == "completed"


def test_a_non_failure_receipt_is_never_reprobed() -> None:
    """``not_requested`` ليست فشلاً — فإعادةُ فحصِها ضجيجٌ لا إصلاح."""
    state = asyncio.run(
        _drive_preload(
            [{"status": "not_requested"}],  # نداءٌ ثانٍ يرفع StopIteration لو وقع
            delays=(0.0, 0.0),
        )
    )
    assert state.generation_startup["status"] == "not_requested"


def test_the_retry_budget_is_bounded_and_the_last_failure_is_what_is_reported() -> None:
    """الإعادةُ محدودة؛ ولو بقي الفشلَ فالمُبلَّغ آخرُ فشلٍ مقيس لا تفاؤل."""
    failure = {"status": "failed", "reason": "ConnectError", "model": "llama3.2:3b"}
    state = asyncio.run(_drive_preload([failure, failure, failure], delays=(0.0, 0.0)))
    assert state.generation_startup["status"] == "failed"


def test_the_service_declares_a_retry_schedule_at_all() -> None:
    """وأنّ الجدولَ موجودٌ في المصدر — لا في هذا الاختبار وحدَه.

    بلا هذا يبقى الشاهدُ أعلاه يفحص نسخةً محلّيّةً من الحلقة بينما الخدمةُ لا تُعيد
    المحاولةَ أصلاً — أي يُثبِت نفسَه لا الشجرة.
    """
    source = (ROOT / "services/ai_agronomist/main.py").read_text(encoding="utf-8")
    assert "_GENERATION_RETRY_DELAYS" in source, "لا جدولَ إعادةٍ في الخدمة"
    assert 'receipt.get("status") != "failed"' in source, (
        "الخدمةُ لا تُنهي الإعادةَ على غير الفشل — أو لا تُعيد أصلاً"
    )
