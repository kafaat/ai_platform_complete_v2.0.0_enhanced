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

#: أطولُ زمنٍ مقيسٍ لـISRIC (ثوانٍ). كان ~41 في التدقيق؛ وقياسُ Railway staging
#: (2026-09-29) على نقطةٍ زراعيّة (وادي زبيد) انقطع عند 90.57 **بلا جواب** — فهو حدٌّ
#: أدنى لا زمنٌ مكتمل. المهلةُ الافتراضيّة (حدُّ الخيط الخلفيّ) يجب أن تتجاوزه.
_MEASURED_ISRIC_LATENCY_SECONDS = 90.57


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
#: كلا المُجلِبَين متزامن. بعد نقل الجلب إلى الذاكرة المؤقّتة صار الموجِّه يُسمّي
#: ``query_soil_properties`` — والفحصُ على ``fetch_soil_properties`` وحده كان سيمرّ فارغاً.
_BLOCKING_FETCHES = frozenset({"fetch_soil_properties", "query_soil_properties"})


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
            if name in _BLOCKING_FETCHES:
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


# ── ٤) «لا تغطية» ليست «متعذّراً» — مقيسٌ حيّاً على Railway staging ─────────────────
#
# **العطلُ الذي وُجِد هذا لأجله** (2026-09-29): ISRIC أجاب صنعاء (44.2,15.35) بـ**200**
# وكلُّ ``mean`` فيه ``null`` — أرضٌ حضريّةٌ مُقنَّعة. والخدمةُ أعادت 503
# «تعذّر الوصول/تغطية»، فغيابُ تغطيةٍ **دائم** يُقرَأ عطلاً **عابراً** يُعاد إلى الأبد.
# والحمولةُ أدناه بنيةُ الردّ الحيّ نفسُها (المفاتيح والطبقات كما عادت)، لا تخمين.


def _load_soil_module(unique: str, filename: str):
    spec = importlib.util.spec_from_file_location(unique, ROOT / "services/soil-service" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SG = _load_soil_module("soilgrids_client_v25_live", "soilgrids_client.py")
SC = _load_soil_module("soilgrids_cache_v25_live", "soilgrids_cache.py")


def _live_shaped(mean_by_layer: dict[str, float | None]) -> dict:
    """بنيةُ ردّ ISRIC كما عادت حيّاً: type/geometry/properties.layers/query_time_s."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [44.2, 15.35]},
        "properties": {
            "layers": [
                {"name": name, "depths": [{"label": "0-5cm", "values": {"mean": mean}}]}
                for name, mean in mean_by_layer.items()
            ]
        },
        "query_time_s": 4.1,
    }


_ALL_NULL = dict.fromkeys(("cec", "clay", "phh2o", "sand", "silt", "soc"))


class _Resp:
    def __init__(self, status: int, payload=None, bad_json: bool = False) -> None:
        self.status_code = status
        self._payload = payload
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._payload


class _Client:
    def __init__(self, resp=None, exc: Exception | None = None) -> None:
        self._resp, self._exc = resp, exc

    def get(self, url, params=None):
        if self._exc:
            raise self._exc
        return self._resp


def test_the_live_urban_payload_is_no_coverage_not_unavailable() -> None:
    out = SG.query_soil_properties(44.2, 15.35, client=_Client(_Resp(200, _live_shaped(_ALL_NULL))))
    assert out == {"outcome": "no_coverage"}, (
        "ISRIC أجاب 200 بلا قيم (أرضٌ مُقنَّعة) — هذا غيابُ تغطيةٍ دائم، لا تعذّرٌ عابر"
    )
    # والتوافقُ القديم باقٍ: من يريد البيانات أو None يحصل على None.
    assert (
        SG.fetch_soil_properties(44.2, 15.35, client=_Client(_Resp(200, _live_shaped(_ALL_NULL))))
        is None
    )


def test_a_partially_masked_point_keeps_the_values_it_has() -> None:
    partial = dict(_ALL_NULL, clay=250, phh2o=78)
    out = SG.query_soil_properties(43.3, 14.2, client=_Client(_Resp(200, _live_shaped(partial))))
    assert out["outcome"] == "ok"
    assert out["data"]["properties"] == {"clay_pct": 25.0, "ph": 7.8}


@pytest.mark.parametrize(
    ("client", "reason"),
    [
        pytest.param(_Client(exc=__import__("httpx").ReadTimeout("t")), "timeout", id="مهلة"),
        pytest.param(_Client(exc=RuntimeError("dns")), "unreachable", id="تعذّر وصول"),
        pytest.param(_Client(_Resp(429, {})), "http_429", id="حدّ الاستخدام"),
        pytest.param(_Client(_Resp(200, bad_json=True)), "malformed", id="JSON شاذّ"),
        pytest.param(
            _Client(_Resp(200, {"properties": {}})), "malformed", id="بلا طبقات ≠ لا تغطية"
        ),
        pytest.param(
            _Client(_Resp(200, _live_shaped({"cec": None}))),
            "malformed",
            id="طبقةٌ واحدةٌ فارغةٌ والبقيّةُ غائبة ≠ لا تغطية (مراجعة #1094)",
        ),
    ],
)
def test_transient_failures_are_classified_and_never_called_no_coverage(client, reason) -> None:
    pytest.importorskip("httpx")
    assert SG.query_soil_properties(1.0, 2.0, client=client) == {
        "outcome": "unavailable",
        "reason": reason,
    }


def test_the_cache_module_speaks_the_same_outcome_names_as_the_client() -> None:
    assert (SC.OK, SC.NO_COVERAGE, SC.UNAVAILABLE) == (SG.OK, SG.NO_COVERAGE, SG.UNAVAILABLE)


# ── ٥) الجلبُ خلفيّ: المستدعي لا ينتظر المزوّد ─────────────────────────────────────
#
# **العطلُ الذي وُجِد هذا لأجله:** نقطةٌ زراعيّةٌ لم تُجَب في 90ث، والمنصّةُ تنتظر
# 20ث فقط (``ADAPTER_TIMEOUT``). فمهما رُفِعت مهلةُ الخدمة، كلُّ نقطةٍ حقيقيّةٍ تصل
# البطاقةَ «مفقودة». الذاكرةُ المؤقّتة بجلبٍ خلفيّ هي ما يجعل النداءَ الثاني فوريّاً.


class _GatedFetch:
    """مُجلِبٌ متزامنٌ يُحبَس حتّى يُفتَح — ويُسجّل الخيطَ الذي جرى فيه."""

    def __init__(self, result: dict) -> None:
        import threading

        self.result = result
        self.gate = threading.Event()
        self.calls = 0
        self.threads: list[int] = []

    def __call__(self, lon: float, lat: float) -> dict:
        import threading

        self.calls += 1
        self.threads.append(threading.get_ident())
        assert self.gate.wait(5), "لم يُفتَح المُجلِب"
        return self.result


_OK = {"outcome": "ok", "data": {"source": "soilgrids", "properties": {"clay_pct": 25.0}}}


def test_a_slow_provider_answers_pending_then_the_next_call_is_served_from_cache() -> None:
    import threading

    fetch = _GatedFetch(_OK)
    cache = SC.SoilGridsCache(fetch, ttl_s=3600)

    async def scenario():
        loop_thread = threading.get_ident()
        first, second = await asyncio.gather(
            cache.lookup(43.33, 14.2, wait_s=0.05), cache.lookup(43.33, 14.2, wait_s=0.05)
        )
        fetch.gate.set()
        for _ in range(200):
            if cache.cached(43.33, 14.2) is not None:
                break
            await asyncio.sleep(0.01)
        third = await cache.lookup(43.33, 14.2, wait_s=0.05)
        return loop_thread, first, second, third

    loop_thread, first, second, third = asyncio.run(scenario())
    assert first == second == {"outcome": "pending"}, "المستدعي كان سينتظر المزوّدَ كلَّه"
    assert fetch.calls == 1, "نداءان متزامنان أطلقا جلبَين — لا single-flight"
    assert third == _OK, "الجلبُ الخلفيّ لم يملأ الذاكرة بعد انقضاء انتظار المستدعي"
    # الشاهدُ السلوكيّ الذي كان #1093 يُعلِن غيابَه: الجلبُ جرى في خيطٍ غيرِ خيط الحلقة.
    assert fetch.threads and fetch.threads[0] != loop_thread


@pytest.mark.parametrize(
    ("result", "cached"),
    [
        pytest.param(_OK, True, id="ok يُخزَّن"),
        pytest.param({"outcome": "no_coverage"}, True, id="لا تغطية دائمة ⇒ تُخزَّن"),
        pytest.param({"outcome": "unavailable", "reason": "timeout"}, False, id="العابر لا يُخزَّن"),
    ],
)
def test_only_durable_outcomes_are_cached(result, cached) -> None:
    fetch = _GatedFetch(result)
    fetch.gate.set()
    cache = SC.SoilGridsCache(fetch, ttl_s=3600)

    async def twice():
        a = await cache.lookup(1.0, 2.0, wait_s=2)
        b = await cache.lookup(1.0, 2.0, wait_s=2)
        return a, b

    a, b = asyncio.run(twice())
    assert a == b == result
    assert fetch.calls == (1 if cached else 2), (
        "عطلُ دقيقةٍ خُزِّن فصار غياباً طويلاً" if not cached else "نتيجةٌ دائمةٌ لم تُخزَّن"
    )


def test_entries_expire_and_the_cache_is_bounded() -> None:
    now = [0.0]
    fetch = _GatedFetch(_OK)
    fetch.gate.set()
    cache = SC.SoilGridsCache(fetch, ttl_s=10, max_entries=2, clock=lambda: now[0])

    async def run():
        await cache.lookup(1.0, 1.0, wait_s=2)
        now[0] = 11.0
        assert cache.cached(1.0, 1.0) is None, "انقضت المدّةُ ولم تُمحَ"
        for p in (1.0, 2.0, 3.0):
            await cache.lookup(p, p, wait_s=2)
        return len(cache._entries), cache.cached(1.0, 1.0)

    size, oldest = asyncio.run(run())
    assert size == 2 and oldest is None, "الذاكرةُ تجاوزت حدَّها أو أبقت الأقدم"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("15", 15.0), ("", 7.0), ("inf", 7.0), ("-1", 7.0), ("x", 7.0), (None, 7.0)],
)
def test_env_seconds_rejects_what_would_hang_a_caller(raw, expected) -> None:
    assert SC.env_seconds(raw, 7.0) == expected


def test_two_nearby_points_never_share_a_cache_entry() -> None:
    """التقريبُ كان يدمج (44.2001,15.3501) و(44.2004,15.3504) فتُجاب الثانيةُ ببيانات
    الأولى وإحداثيّتها أسبوعاً — والنقطتان قد تقعان على جانبَي حدّ خليّة (مراجعة #1094)."""
    fetch = _GatedFetch(_OK)
    fetch.gate.set()
    cache = SC.SoilGridsCache(fetch, ttl_s=3600)

    async def run():
        await cache.lookup(44.2001, 15.3501, wait_s=2)
        await cache.lookup(44.2004, 15.3504, wait_s=2)

    asyncio.run(run())
    assert fetch.calls == 2, "نقطتان مختلفتان أُجيبتا من مدخلٍ واحد"
