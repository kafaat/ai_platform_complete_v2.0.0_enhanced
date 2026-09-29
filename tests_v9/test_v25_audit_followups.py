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

import ast
import asyncio
import importlib.util
import types
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
#
# **تصحيحٌ بعد مراجعة #1093:** كانت الصيغةُ الأولى تختبر **نسخةً محلّيّةً** من حلقة
# الإعادة في هذا الملفّ، مع فحصٍ نصّيٍّ يُثبّت رمزَين. فتبقى خضراءَ ولو كفّت الخدمةُ
# عن الإعادة أو عن الكتابة في ``app.state`` — الصنفُ نفسُه الذي أُغلِق في #1092.
# صارت الحلقةُ ``ai_generation.preload_with_retry`` محقونةَ التبعيّات، و``lifespan``
# تُناديها، وهذه الاختبارات تُشغّلها **هي** — وأحدُها يُشغّل ``lifespan`` الحقيقيّة.

from services.ai_agronomist import ai_generation as G  # noqa: E402


class _Probe:
    """فاحصٌ مُبرمَج: يُعيد الإيصالاتِ بالترتيب ويعدّ النداءات."""

    def __init__(self, receipts: list[dict]) -> None:
        self._receipts = list(receipts)
        self.calls = 0

    async def __call__(self) -> dict:
        self.calls += 1
        return self._receipts.pop(0)


def _run_helper(receipts: list[dict], delays: tuple[float, ...]):
    probe = _Probe(receipts)
    slept: list[float] = []
    recorded: list[dict] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    final = asyncio.run(
        G.preload_with_retry(probe, delays=delays, sleep=fake_sleep, on_receipt=recorded.append)
    )
    return final, probe, slept, recorded


def test_the_production_helper_reprobes_a_boot_failure_until_it_succeeds() -> None:
    failed = {"status": "failed", "reason": "ConnectError", "model": "m"}
    done = {"status": "completed", "model": "m"}
    final, probe, slept, recorded = _run_helper([failed, done], delays=(15.0, 60.0))
    assert final == done
    assert probe.calls == 2
    assert slept == [15.0], "نامت بمُهلةٍ غيرِ المُجدولة أو لم تنم"
    assert recorded == [failed, done], "كلُّ إيصالٍ يجب أن يُكتَب فور وصوله"


def test_the_production_helper_never_reprobes_a_non_failure() -> None:
    final, probe, slept, recorded = _run_helper([{"status": "not_requested"}], delays=(15.0,))
    assert final == {"status": "not_requested"}
    assert probe.calls == 1 and slept == []
    assert recorded == [{"status": "not_requested"}]


def test_the_production_helper_is_bounded_and_reports_the_last_measured_failure() -> None:
    failed = {"status": "failed", "reason": "ConnectError", "model": "m"}
    final, probe, slept, _ = _run_helper([failed, failed, failed], delays=(1.0, 2.0))
    assert final["status"] == "failed"
    assert probe.calls == 3, "الإعادةُ يجب أن تتوقّف عند نهاية الجدول"
    assert slept == [1.0, 2.0], "المُهَلُ يجب أن تُحترَم بترتيبها"


def test_the_real_lifespan_writes_the_retried_receipt_into_app_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """الشاهدُ الذي كان ناقصاً: ``lifespan`` الحقيقيّة، لا نسخةٌ منها.

    لو كفّت ``preload`` عن مناداة المساعِد، أو عن الإعادة، أو عن الكتابة في
    ``app.state``، لبقي الإيصالُ ``failed`` أو ``pending`` وحمرَّ هذا الاختبار.
    """
    pytest.importorskip("fastapi")
    from services.ai_agronomist import main as M

    probe = _Probe(
        [
            {"status": "failed", "reason": "ConnectError", "model": "m"},
            {"status": "completed", "model": "m"},
        ]
    )
    monkeypatch.setattr(M.ai_generation, "preload_local_generation", probe)
    monkeypatch.setattr(M, "_GENERATION_RETRY_DELAYS", (0.0,))

    async def scenario() -> dict:
        app = types.SimpleNamespace(state=types.SimpleNamespace())
        async with M.lifespan(app):
            for _ in range(400):
                if getattr(app.state, "generation_startup", {}).get("status") == "completed":
                    break
                await asyncio.sleep(0.005)
            return dict(app.state.generation_startup)

    receipt = asyncio.run(scenario())
    assert receipt == {"status": "completed", "model": "m"}
    assert probe.calls == 2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, G.DEFAULT_PRELOAD_RETRY_DELAYS, id="غائب ⇒ الافتراض"),
        pytest.param("  ", G.DEFAULT_PRELOAD_RETRY_DELAYS, id="فارغ ⇒ الافتراض"),
        pytest.param("1, 2.5,0", (1.0, 2.5, 0.0), id="صالح ⇒ كما هو"),
        pytest.param("15,inf", G.DEFAULT_PRELOAD_RETRY_DELAYS, id="inf ⇒ كان سيُعيد الإيصالَ العالق"),
        pytest.param("nan", G.DEFAULT_PRELOAD_RETRY_DELAYS, id="nan"),
        pytest.param("15,-1", G.DEFAULT_PRELOAD_RETRY_DELAYS, id="سالب"),
        pytest.param("15,abc", G.DEFAULT_PRELOAD_RETRY_DELAYS, id="غيرُ رقميّ ⇒ لا يُسقِط الاستيراد"),
    ],
)
def test_the_retry_schedule_parser_rejects_what_would_recreate_the_fault(raw, expected) -> None:
    assert G.parse_preload_retry_delays(raw) == expected


# ── ٣) الجلبُ المتزامن لا يحجز حلقةَ أحداثِ المسار غيرِ المتزامن ─────────────────────
#
# رفعُ المهلة إلى 60 جعل نداءً متزامناً داخل مسارٍ ``async`` يحجز حلقةَ الأحداث دقيقةً
# كاملة — فبعاملَي Uvicorn يكفي طلبان بطيئان لتجويع /healthz (رصده مراجعُ #1093).
#
# **حدُّ هذا الشاهد، صراحةً:** يفحص **بنيةَ الشيفرة الحقيقيّة** (AST) لا سلوكَها وقتَ
# التشغيل. فتحميلُ الموجِّه يستورد ``main`` الخاصّ بـsoil-service، وهو يتصادم مع
# وحدات ``main`` لخدماتٍ أخرى في جلسة pytest واحدة. والفحصُ البنيويُّ على الملفّ
# الحقيقيّ ليس نسخةً منه، لكنّه لا يُثبِت أنّ الخيطَ يعمل — يُثبِت أنّ النداءَ المباشرَ
# لم يَعُد.

_SOIL_ROUTER = ROOT / "services/soil-service/routers/soil_profile.py"
_BLOCKING_FETCH = "fetch_soil_properties"


def _direct_blocking_calls_inside_async_defs(source: str) -> list[str]:
    """كلُّ نداءٍ **مباشر** للجلب المتزامن داخل ``async def`` — والتمريرُ لـ``to_thread`` ليس نداءً."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == _BLOCKING_FETCH:
                found.append(f"{node.name}:{inner.lineno}")
    return found


def test_no_async_route_calls_the_blocking_soil_fetch_directly() -> None:
    offenders = _direct_blocking_calls_inside_async_defs(_SOIL_ROUTER.read_text(encoding="utf-8"))
    assert offenders == [], f"جلبٌ متزامنٌ يُنادى مباشرةً داخل مسارٍ غيرِ متزامن: {offenders}"


def test_the_detector_flags_a_direct_call_and_accepts_the_thread_offload() -> None:
    """تكذيبٌ للكاشف نفسِه — كي لا تكون خضرةُ الشجرة شهادةً على كاشفٍ لا يرى."""
    direct = "async def r():\n    data = soilgrids_client.fetch_soil_properties(1, 2)\n"
    offloaded = (
        "import asyncio\n"
        "async def r():\n"
        "    data = await asyncio.to_thread(soilgrids_client.fetch_soil_properties, 1, 2)\n"
    )
    assert _direct_blocking_calls_inside_async_defs(direct) == ["r:2"]
    assert _direct_blocking_calls_inside_async_defs(offloaded) == []
