"""إعادةُ المحاولة حول edge-tts (M8، مراجعة v25) — تُختبَر الحلقةُ **نفسُها** لا نسخةٌ منها.

**العطلُ:** ``EdgeTTSProvider.synthesize`` كان يبني ``edge_tts.Communicate`` ويبثّ
**مرّةً واحدة**، فأيُّ انقطاعٍ عابر (مهلة · قطعُ اتّصال · 5xx) صار 500 مباشرةً.

**ما يُثبِته هذا الملفّ** بـ``Communicate`` مُزيَّف (مُبرمَج الفشل) ونومٍ محقون:
  • فشلٌ عابرٌ N مرّةً ثمّ نجاح ⇒ يُعاد النجاحُ بتباعدٍ أُسّيّ مُعلَن.
  • محاولةٌ بثّت صوتاً جزئيّاً ثمّ انقطعت ⇒ لا تتسرّب بايتاتُها إلى الناتج.
  • نفادُ المحاولات ⇒ يُرفَع **آخرُ** استثناءٍ مقيس (لا ابتلاع).
  • المُدخَلُ المرفوض و``NoAudioReceived`` و4xx ⇒ **لا** إعادة.
  • قراءةُ البيئة آمنة: غيرُ الرقميّ/غيرُ المنتهي/السالب ⇒ الافتراض، والسقفُ يُحترَم.

**ما لا يفحصه، صراحةً:** لا يتّصل بخدمة Microsoft. تصنيفُ «العابر» مبنيٌّ على أصناف
``edge_tts.exceptions`` (7.2.8) و``aiohttp`` — لا على قياسٍ حيٍّ لتوزيع أعطالها.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SVC_DIR = Path(__file__).resolve().parents[1] / "services" / "tts-service"
if str(_SVC_DIR) not in sys.path:
    sys.path.insert(0, str(_SVC_DIR))

import providers as P  # noqa: E402


# ── edge_tts مُزيَّف: أصنافُ الاستثناءات بأسمائها الحقيقيّة (edge_tts 7.2.8) ─────────
class _EdgeTTSException(Exception):
    pass


class WebSocketError(_EdgeTTSException):
    pass


class UnknownResponse(_EdgeTTSException):
    pass


class UnexpectedResponse(_EdgeTTSException):
    pass


class NoAudioReceived(_EdgeTTSException):
    pass


_FAKE_EXC = types.SimpleNamespace(
    EdgeTTSException=_EdgeTTSException,
    WebSocketError=WebSocketError,
    UnknownResponse=UnknownResponse,
    UnexpectedResponse=UnexpectedResponse,
    NoAudioReceived=NoAudioReceived,
)


def _install(monkeypatch: pytest.MonkeyPatch, script: list) -> list[dict]:
    """يُركّب ``Communicate`` مُبرمَجاً: كلُّ عنصرٍ في ``script`` يصف محاولةً واحدة.

    العنصر: ``(chunks, exc)`` — تُبثّ ``chunks`` (بايتات صوت) ثمّ يُرفَع ``exc`` إن وُجِد.
    أو استثناءٌ مجرّد ⇒ يُرفَع **من الباني** (كما يفعل edge_tts مع مُدخَلٍ مرفوض).
    """
    constructed: list[dict] = []
    plan = list(script)

    class FakeCommunicate:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
            step = plan.pop(0)
            if isinstance(step, BaseException):
                raise step
            self._chunks, self._exc = step
            self._streamed = False

        async def stream(self):
            assert not self._streamed, "stream() يُنادى مرّةً لكلّ كائن في edge_tts الحقيقيّ"
            self._streamed = True
            for data in self._chunks:
                yield {"type": "WordBoundary"}
                yield {"type": "audio", "data": data}
            if self._exc is not None:
                raise self._exc

    monkeypatch.setattr(
        P, "edge_tts", types.SimpleNamespace(Communicate=FakeCommunicate, exceptions=_FAKE_EXC)
    )
    monkeypatch.setattr(P, "_EDGE_AVAILABLE", True)
    return constructed


def _run(provider: P.EdgeTTSProvider) -> bytes:
    return asyncio.run(provider.synthesize("مرحبا", "ar-SA-HamedNeural", "+0%", "+0Hz", "+0%"))


def _provider() -> tuple[P.EdgeTTSProvider, list[float]]:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    return P.EdgeTTSProvider(sleep=fake_sleep), slept


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TTS_EDGE_RETRY_ATTEMPTS", raising=False)
    monkeypatch.delenv("TTS_EDGE_RETRY_BASE_DELAY_SECONDS", raising=False)


# ── الحلقة ────────────────────────────────────────────────────────────────────
def test_transient_failures_then_success_returns_the_successful_audio(monkeypatch) -> None:
    constructed = _install(
        monkeypatch,
        [([], TimeoutError("sock_read")), ([], WebSocketError("closed")), ([b"OK"], None)],
    )
    provider, slept = _provider()
    assert _run(provider) == b"OK"
    assert len(constructed) == 3, "كلُّ محاولةٍ تبني Communicate جديداً"
    assert slept == [0.5, 1.0], "التباعدُ الأُسّيّ من الافتراض المُعلَن (0.5 ثمّ 1.0)"


def test_a_partially_streamed_attempt_does_not_leak_into_the_result(monkeypatch) -> None:
    """الشاهدُ على المخزن الجديد لكلّ محاولة: ``PART`` بُثَّ ثمّ انقطع القناة."""
    _install(
        monkeypatch,
        [([b"PART-1", b"PART-2"], ConnectionError("reset")), ([b"FULL"], None)],
    )
    provider, _ = _provider()
    assert _run(provider) == b"FULL"


def test_exhausted_attempts_raise_the_last_measured_failure(monkeypatch) -> None:
    last = UnexpectedResponse("third")
    constructed = _install(
        monkeypatch,
        [([], TimeoutError("first")), ([b"x"], ConnectionError("second")), ([], last)],
    )
    provider, slept = _provider()
    with pytest.raises(UnexpectedResponse) as ei:
        _run(provider)
    assert ei.value is last
    assert len(constructed) == 3, "الإعادةُ محدودةٌ بالافتراض (3 محاولات كلّيّة)"
    assert slept == [0.5, 1.0], "لا نومَ بعد المحاولة الأخيرة"


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(ValueError("Invalid rate '+abc%'."), id="مُدخَل مرفوض من الباني"),
        pytest.param(TypeError("text must be str"), id="نوع مرفوض من الباني"),
    ],
)
def test_invalid_input_raised_by_the_constructor_is_never_retried(monkeypatch, failure) -> None:
    constructed = _install(monkeypatch, [failure, ([b"never"], None)])
    provider, slept = _provider()
    with pytest.raises(type(failure)):
        _run(provider)
    assert len(constructed) == 1 and slept == []


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(NoAudioReceived("verify parameters"), id="NoAudioReceived"),
        pytest.param(RuntimeError("unknown"), id="مجهول ⇒ لا إعادة"),
    ],
)
def test_non_transient_stream_failures_are_not_retried(monkeypatch, failure) -> None:
    constructed = _install(monkeypatch, [([], failure), ([b"never"], None)])
    provider, slept = _provider()
    with pytest.raises(type(failure)):
        _run(provider)
    assert len(constructed) == 1 and slept == []


def test_http_status_classification_retries_5xx_and_429_but_not_other_4xx() -> None:
    aiohttp = pytest.importorskip("aiohttp")

    def err(status: int) -> BaseException:
        return aiohttp.ClientResponseError(request_info=None, history=(), status=status)

    assert P.is_transient_edge_error(err(503)) is True
    assert P.is_transient_edge_error(err(429)) is True
    assert P.is_transient_edge_error(err(408)) is True
    assert P.is_transient_edge_error(err(400)) is False
    assert P.is_transient_edge_error(err(403)) is False
    assert P.is_transient_edge_error(aiohttp.ServerDisconnectedError()) is True
    assert P.is_transient_edge_error(aiohttp.InvalidURL("x")) is False, "ValueError ⇒ مُدخَل"


def test_attempts_of_one_disables_retry_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("TTS_EDGE_RETRY_ATTEMPTS", "1")
    constructed = _install(monkeypatch, [([], TimeoutError("x")), ([b"never"], None)])
    provider, slept = _provider()
    with pytest.raises(TimeoutError):
        _run(provider)
    assert len(constructed) == 1 and slept == []


def test_the_environment_overrides_attempts_and_delay(monkeypatch) -> None:
    monkeypatch.setenv("TTS_EDGE_RETRY_ATTEMPTS", "4")
    monkeypatch.setenv("TTS_EDGE_RETRY_BASE_DELAY_SECONDS", "0.25")
    _install(
        monkeypatch,
        [([], TimeoutError()), ([], TimeoutError()), ([], TimeoutError()), ([b"OK"], None)],
    )
    provider, slept = _provider()
    assert _run(provider) == b"OK"
    assert slept == [0.25, 0.5, 1.0]


# ── قراءة البيئة ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("2", 2, id="صالح"),
        pytest.param(" 1 ", 1, id="1 ⇒ بلا إعادة"),
        pytest.param("100", P.MAX_EDGE_RETRY_ATTEMPTS, id="فوق السقف ⇒ السقف"),
        pytest.param("0", P.DEFAULT_EDGE_RETRY_ATTEMPTS, id="صفر ⇒ الافتراض"),
        pytest.param("-3", P.DEFAULT_EDGE_RETRY_ATTEMPTS, id="سالب"),
        pytest.param("2.5", P.DEFAULT_EDGE_RETRY_ATTEMPTS, id="كسريّ"),
        pytest.param("inf", P.DEFAULT_EDGE_RETRY_ATTEMPTS, id="inf"),
        pytest.param("nan", P.DEFAULT_EDGE_RETRY_ATTEMPTS, id="nan"),
        pytest.param("abc", P.DEFAULT_EDGE_RETRY_ATTEMPTS, id="غير رقميّ ⇒ لا يُسقِط"),
        pytest.param("", P.DEFAULT_EDGE_RETRY_ATTEMPTS, id="فارغ"),
    ],
)
def test_attempts_parser_is_finite_and_bounded(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("TTS_EDGE_RETRY_ATTEMPTS", raw)
    assert P.edge_retry_attempts() == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("0", 0.0, id="صفر ⇒ فوريّ"),
        pytest.param("1.5", 1.5, id="صالح"),
        pytest.param("99", P.MAX_EDGE_RETRY_BASE_DELAY_SECONDS, id="فوق السقف"),
        pytest.param("-0.1", P.DEFAULT_EDGE_RETRY_BASE_DELAY_SECONDS, id="سالب"),
        pytest.param("inf", P.DEFAULT_EDGE_RETRY_BASE_DELAY_SECONDS, id="inf"),
        pytest.param("nan", P.DEFAULT_EDGE_RETRY_BASE_DELAY_SECONDS, id="nan"),
        pytest.param("soon", P.DEFAULT_EDGE_RETRY_BASE_DELAY_SECONDS, id="غير رقميّ"),
    ],
)
def test_delay_parser_is_finite_non_negative_and_bounded(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("TTS_EDGE_RETRY_BASE_DELAY_SECONDS", raw)
    assert P.edge_retry_base_delay() == expected


def test_unset_environment_uses_the_declared_defaults() -> None:
    assert P.edge_retry_attempts() == P.DEFAULT_EDGE_RETRY_ATTEMPTS == 3
    assert P.edge_retry_base_delay() == P.DEFAULT_EDGE_RETRY_BASE_DELAY_SECONDS == 0.5
