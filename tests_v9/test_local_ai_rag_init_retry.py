"""تهيئةُ local-ai-rag تُعاد بحدود وتراجعٍ، و/readyz يميّز الفشلَ النهائيّ عن التحميل (P0).

التدقيق الموحَّد 2026-09-13: كانت ``_init_models_background`` محاولةً واحدة؛ تأخّرُ
Qdrant/Ollama ثوانيَ عند الإقلاع يترك الخدمة 503 إلى الأبد بينما /readyz يقول «قيد
التحميل». الوحدةُ النقيّة ``init_retry`` تُختبَر بحقن ``sleep`` ومُهيّئ صناعيّ — بلا
شبكة ولا FastAPI؛ وربطُها بـ``main.py`` و``/readyz`` يُثبَّت على المصدر.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "local-ai-rag"
MAIN = SERVICE / "main.py"


@pytest.fixture(scope="module")
def retry():
    spec = importlib.util.spec_from_file_location(
        "_local_ai_rag_init_retry", SERVICE / "init_retry.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_backoff_is_exponential_and_capped(retry):
    assert retry.backoff_seconds(1, base=5, cap=60) == 5
    assert retry.backoff_seconds(2, base=5, cap=60) == 10
    assert retry.backoff_seconds(4, base=5, cap=60) == 40
    assert retry.backoff_seconds(9, base=5, cap=60) == 60


def test_backoff_stays_bounded_for_huge_attempt_budgets(retry):
    """Copilot على #1001 (مكتومة): `2 ** (attempt-1)` كان يُحسَب قبل `min` — سقفٌ ضخم يبني عدداً
    هائلاً (تعليق/MemoryError) عند جدولة الإعادة."""
    assert retry.backoff_seconds(10**9, base=5, cap=60) == 60
    assert retry.backoff_seconds(10**9, base=0, cap=60) == 0.0
    assert retry.backoff_seconds(3, base=5, cap=12) == 12  # يتوقّف عند السقف


def test_backoff_fails_closed_on_negative_or_non_finite_bounds(retry):
    """Copilot على #1001 (مكتومة): قاعدةٌ سالبة كانت تُعيد زمناً سالباً ⇒ حلقةُ إعادة ضيّقة."""
    for base, cap in ((-5, 60), (5, -1), (float("nan"), 60), (5, float("inf"))):
        with pytest.raises(ValueError):
            retry.backoff_seconds(1, base=base, cap=cap)


def test_non_numeric_attempt_budget_falls_back_instead_of_killing_the_import(retry):
    """Copilot على #1001: `int(os.getenv(...))` على نصّ غير رقميّ كان يُسقِط الوحدة عند الاستيراد."""
    assert retry.int_or_default("abc", 6, name="X") == 6
    assert retry.int_or_default("", 6, name="X") == 6
    assert retry.int_or_default(None, 6, name="X") == 6
    assert retry.int_or_default(" 3 ", 6, name="X") == 3
    assert retry.int_or_default("-2", 6, name="X") == -2  # التقييدُ الأدنى مسؤوليّةُ المُنادي
    src = MAIN.read_text(encoding="utf-8")
    assert 'int_or_default(\n    os.getenv("RAG_INIT_MAX_ATTEMPTS", "6")' in src
    assert 'int(os.getenv("RAG_INIT_MAX_ATTEMPTS"' not in src, (
        "نصٌّ غير رقميّ في RAG_INIT_MAX_ATTEMPTS يُسقِط الخدمة قبل /readyz — يجب أن يمرّ بحدود الإعداد"
    )


def test_lifespan_owns_and_cancels_the_init_task():
    """Copilot على #1001 (مكتومة): مهمّةُ التهيئة كانت fire-and-forget — تستمرّ بعد الإيقاف وتتسرّب."""
    src = MAIN.read_text(encoding="utf-8")
    lifespan = src.split("async def lifespan(", 1)[1].split("\n\n\n", 1)[0]
    assert "init_task = asyncio.create_task(_init_models_background())" in lifespan
    assert "finally:" in lifespan and "init_task.cancel()" in lifespan
    assert "with suppress(asyncio.CancelledError):\n                await init_task" in lifespan
    assert "asyncio.create_task(_init_models_background())\n" not in src.replace(
        "init_task = asyncio.create_task(_init_models_background())\n", ""
    ), "إنشاءُ مهمّةٍ بلا احتفاظ بمرجعها يعني تهيئةً تستمرّ بعد توقّف التطبيق"


def test_config_boundary_normalises_backoff_values(retry):
    """القيمُ غير الصالحة تُستبدَل بالافتراضيّ عند الحدود (لا في منتصف حلقة الإعادة)."""
    ok = retry.non_negative_float("2.5", 5.0, name="X")
    assert ok == 2.5
    assert retry.non_negative_float(None, 5.0, name="X") == 5.0
    assert retry.non_negative_float("  ", 5.0, name="X") == 5.0
    for bad in ("-5", "nan", "inf", "-inf", "abc"):
        assert retry.non_negative_float(bad, 60.0, name="X") == 60.0, bad
    assert retry.non_negative_float("0", 60.0, name="X") == 0.0  # الصفر مسموح (بلا تراجع)
    # main.py يمرّ بهذه الحدود لكلا المتغيّرين — لا `float(os.getenv(...))` عارٍ.
    src = MAIN.read_text(encoding="utf-8")
    for var, default in (("RAG_INIT_BACKOFF_BASE_S", "5"), ("RAG_INIT_BACKOFF_CAP_S", "60")):
        assert f'non_negative_float(\n    os.getenv("{var}", "{default}")' in src, var
        assert f'float(os.getenv("{var}"' not in src, (
            f"{var} يُقرأ بلا تطبيع — السالبُ يصير تراجعاً صفريّاً وحلقةَ إعادة ضيّقة"
        )


@pytest.mark.asyncio
async def test_transient_failure_is_retried_until_ready(retry):
    attempts = {"n": 0}
    sleeps: list[float] = []

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("qdrant not up yet")

    async def fake_sleep(s):
        sleeps.append(s)

    state = retry.new_state()
    out = await retry.run_init_with_retry(
        flaky, state, max_attempts=5, base=5, cap=60, sleep=fake_sleep
    )
    assert out["status"] == "ready" and out["attempts"] == 3
    assert out["last_error"] is None
    assert state == out  # الحالة المشتركة (التي يقرؤها /readyz) حُدِّثت في مكانها
    assert sleeps == [5, 10]


@pytest.mark.asyncio
async def test_exhausted_attempts_are_reported_as_failed_not_pending(retry):
    def always_down():
        raise RuntimeError("collection missing")

    async def no_sleep(_s):
        return None

    state = retry.new_state()
    out = await retry.run_init_with_retry(
        always_down, state, max_attempts=3, base=1, cap=1, sleep=no_sleep
    )
    assert out["status"] == "failed" and out["attempts"] == 3
    assert "collection missing" in out["last_error"]


@pytest.mark.asyncio
async def test_intermediate_state_is_retrying_not_pending(retry):
    seen: list[str] = []
    state = retry.new_state()

    async def observe(_s):
        seen.append(state["status"])

    calls = {"n": 0}

    def once_then_ok():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("ollama")

    await retry.run_init_with_retry(
        once_then_ok, state, max_attempts=2, base=1, cap=1, sleep=observe
    )
    assert seen == ["retrying"] and state["status"] == "ready"


def test_main_wires_background_init_and_readyz_through_the_shared_state():
    src = MAIN.read_text(encoding="utf-8")
    assert "import init_retry" in src
    assert "_init_state: dict = init_retry.new_state()" in src
    assert "await init_retry.run_init_with_retry(" in src
    assert "max_attempts=INIT_MAX_ATTEMPTS" in src
    # /readyz يميّز الفشل النهائيّ ويذكر المحاولات وآخر خطأ.
    readyz = src[src.index('@app.get("/readyz")') :]
    assert '"init_failed" if failed else "initialising"' in readyz
    assert '"init_attempts": _init_state.get("attempts", 0)' in readyz
    assert '"last_error": _init_state.get("last_error")' in readyz


@pytest.mark.asyncio
async def test_initializer_returning_a_task_or_future_is_awaited_not_assumed_ready(retry):
    """Copilot على #1001: Task/Future awaitable لا coroutine — يجب انتظاره لا اعتباره نجاحاً."""
    import asyncio

    calls = {"n": 0}

    def init_returning_future():
        calls["n"] += 1
        fut = asyncio.get_running_loop().create_future()
        if calls["n"] == 1:
            fut.set_exception(RuntimeError("qdrant down"))
        else:
            fut.set_result(None)
        return fut

    async def no_sleep(_s):
        return None

    state = retry.new_state()
    out = await retry.run_init_with_retry(
        init_returning_future, state, max_attempts=3, base=1, cap=1, sleep=no_sleep
    )
    assert out["status"] == "ready" and out["attempts"] == 2

    async def slow_ok():
        await asyncio.sleep(0)

    def init_returning_task():
        return asyncio.create_task(slow_ok())

    state2 = retry.new_state()
    out2 = await retry.run_init_with_retry(
        init_returning_task, state2, max_attempts=1, base=1, cap=1, sleep=no_sleep
    )
    assert out2["status"] == "ready"


def test_readyz_reports_the_clamped_attempt_budget_not_the_raw_env():
    """Copilot على #1001: صفرٌ أو سالب في RAG_INIT_MAX_ATTEMPTS يُقيَّد إلى 1 عند التعريف
    — فما يُنفَّذ وما يُبلَّغ في /readyz قيمةٌ واحدة، ويُسجَّل تحذير."""
    src = MAIN.read_text(encoding="utf-8")
    assert "INIT_MAX_ATTEMPTS = max(1, _INIT_MAX_ATTEMPTS_RAW)" in src
    assert "if _INIT_MAX_ATTEMPTS_RAW < 1:" in src
    readyz = src[src.index('@app.get("/readyz")') :]
    assert '"init_max_attempts": INIT_MAX_ATTEMPTS' in readyz
    assert "_INIT_MAX_ATTEMPTS_RAW" not in readyz
