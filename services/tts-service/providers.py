"""providers.py — تجريد مزوّدي تحويل النصّ إلى كلام (Provider abstraction).
================================================================================
وحدة **بلا fastapi** — منطق نقيّ قابل للاستيراد والاختبار وحدويّاً. تعرّف بروتوكول
مزوّد موحّد وتلفّ المحرّكات المتاحة:

  • ``EdgeTTSProvider`` — Microsoft edge-tts (المحرّك الإلزاميّ الوحيد والافتراضيّ؛
    متاح دوماً ما دام ``edge_tts`` يُستورَد). سلوكه أمينُ-البايت لمسار التركيب القائم.
  • ``PiperProvider`` — Piper (شبكة عصبيّة على المعالِج، اختياريّ). استيراد محروس؛
    ``available()`` = False حين تغيب المكتبة أو مسار نموذج الصوت (``PIPER_VOICE_PATH``).
  • ``XTTSProvider`` — Coqui XTTS (اختياريّ، يفضّل المعالِج الرسوميّ). استيراد محروس؛
    ``available()`` = False ما لم تُستورَد المكتبة **و** يُفعَّل صراحةً
    (``TTS_GPU_PROVIDER=xtts`` أو ``XTTS_ENABLE=1``) — تماشياً مع overlay الـGPU.

قاعدة صارمة: piper/coqui **تبعيّات اختياريّة** لا تُضاف إلى ``requirements.txt`` (كي
لا تكسر طبقة الوحدات/pip-audit). الخدمة تُستورَد وتُختبَر بدونها؛ edge يبقى الآمن.
لتفعيل piper محليّاً: ``pip install piper-tts`` + ضبط ``PIPER_VOICE_PATH``.
لتفعيل xtts (GPU): ``pip install TTS`` + ``TTS_GPU_PROVIDER=xtts``.
"""

from __future__ import annotations

import abc
import asyncio
import importlib.metadata
import io
import logging
import math
import os
import threading
from collections.abc import Awaitable, Callable
from typing import Any

# ── المحرّك الإلزاميّ الوحيد: edge_tts ─────────────────────────────────────────
try:
    import edge_tts

    _EDGE_AVAILABLE = True
except ImportError:  # pragma: no cover - edge_tts تبعيّة إلزاميّة في الخدمة
    edge_tts = None  # type: ignore[assignment]
    _EDGE_AVAILABLE = False

# ── محرّكات اختياريّة (استيراد محروس — غيابها لا يُسقِط الخدمة) ────────────────
try:
    import piper  # noqa: F401

    _PIPER_LIB_AVAILABLE = True
except ImportError:
    piper = None  # type: ignore[assignment]
    _PIPER_LIB_AVAILABLE = False

try:
    # مكتبة Coqui تُصدَّر باسم الحزمة ``TTS``.
    import TTS  # noqa: F401

    _XTTS_LIB_AVAILABLE = True
except ImportError:
    TTS = None  # type: ignore[assignment]
    _XTTS_LIB_AVAILABLE = False


# ── البروتوكول الموحّد ─────────────────────────────────────────────────────────
class TTSProvider(abc.ABC):
    """عقد مزوّد TTS: اسمٌ، فحصُ توفّر، وتركيبٌ غير متزامن يُرجِع بايتات صوت."""

    name: str = "abstract"
    #: هل يُرسِل المزوّدُ النصَّ خارج حدّ المستأجِر؟ (TTS-LOCAL-ONLY-FALLS-BACK-TO-EXTERNAL-PROVIDER-01)
    #: الافتراضيّ محلّيّ؛ كلُّ مزوّدٍ شبكيٍّ يُعلنه صراحةً فيُحجَب حين لا تسمح السياسة.
    external: bool = False
    #: نوعُ وعاء الصوت الذي يُرجِعه ``synthesize`` — تُعلِنه الاستجابةُ كما هو (مراجعة #1122:
    #: Piper يكتب WAV؛ وسمُه ``audio/mpeg`` كان يكذب على المُشغِّل). الافتراضيّ لا يدّعي صيغة.
    media_type: str = "application/octet-stream"

    @abc.abstractmethod
    def available(self) -> bool:
        """هل المزوّد جاهز فعليّاً (المكتبة + النموذج/العلم)؟ لا يرمي أبداً."""
        raise NotImplementedError

    @abc.abstractmethod
    async def synthesize(self, text: str, voice: str, rate: str, pitch: str, volume: str) -> bytes:
        """يركّب ``text`` بالصوت المُعطى ويُرجِع بايتات الصوت. يرمي إن كان غير متاح."""
        raise NotImplementedError


# ── إعادة المحاولة حول edge-tts (M8، مراجعة v25) ──────────────────────────────
#
# **العطلُ الذي وُجِد هذا لأجله:** ``edge_tts.Communicate`` يفتح WebSocket نحو خدمة
# Microsoft **مرّةً واحدة**؛ وأيُّ انقطاعٍ عابر (مهلةُ قراءة · قطعُ اتّصال · ردُّ 5xx ·
# رسالةٌ غيرُ متوقَّعة من الخادم) كان يصير 500 «Speech synthesis failed» مباشرةً —
# فعطلُ شبكةٍ لثانيةٍ يُقرَأ عجزاً عن التركيب.
#
# **ما يُعاد وما لا يُعاد:** يُعاد **العابرُ وحده**. المُدخَلُ الخاطئ (صوتٌ/معدّلٌ/نبرةٌ
# بصيغةٍ مرفوضة ⇒ ``ValueError``/``TypeError`` من الباني) و4xx غيرُ 408/429 **لا تُعاد**:
# إعادتُها تُضاعف الكمونَ ولا تُغيّر النتيجة.
#
# **و``NoAudioReceived`` يُعاد — وكان مُستثنى، فاستُثني بالضبط العطلُ الذي وُجِد هذا لأجله.**
# تدقيق v25 الحيّ قاس: «500 عابرة أمام Edge-TTS ("No audio was received")؛ الإعادة تنجح».
# ورسالةُ المكتبة «تحقّق من المعاملات» تصف سبباً واحداً من سببين، والثاني موثَّقٌ في
# منبعها: ``NoAudioReceived`` متقطّعٌ بمعاملاتٍ صحيحة (rany2/edge-tts#473، 2026-04) — ردٌّ
# بلا إطارات صوت حين يخنق الخادمُ الطلبَ. **والسببُ الأوّل مُغلَقٌ قبل هذا الموضع مرّتين:**
# ``TTSRequest`` يقصر ``voice`` على مفاتيح ``VOICES`` ويتحقّق من rate/volume/pitch، و
# ``TTSConfig`` في edge-tts يرفض الصيغة الخاطئة بـ``ValueError`` في الباني قبل أيّ شبكة. فما
# يبلغ هذه الحلقة بصوتٍ من القائمة هو الخنقُ لا المُدخَل. **وحدُّه:** حين يدوم الخنق (المنبعُ
# نفسُه رأى المحاولات الثلاث تفشل) تُكلِّف الإعادةُ نوماً قبل الخطأ نفسه: **~1.5ث بالافتراض**
# (3 محاولات · 0.5ث ثمّ 1ث)، و**حتى 155ث بأقصى الضبط** (6 محاولات · أساس 5ث:
# 5+10+20+40+80) — فرفعُ المتغيّرين قرارُ كمونٍ لا إعدادٌ مجّانيّ.
#
# **الصوتُ الجزئيّ لا يتسرّب:** كلُّ محاولةٍ تبني ``Communicate`` جديداً (``stream()``
# لا يُنادى إلّا مرّةً لكلّ كائن) ومخزناً جديداً، ولا يُعاد إلّا مخزنُ محاولةٍ اكتملت.
# فمحاولةٌ بثّت نصفَ الصوت ثمّ انقطعت لا تُلصَق بايتاتُها قبل المحاولة التالية.
#
# المتغيّران يُقرآن وقتَ النداء وبافتراضٍ صريح (فلا يُعدّان «مطلوبين» في حارس
# انجراف env↔compose). وقيمةٌ غيرُ رقميّة أو غيرُ منتهية أو سالبة ⇒ الافتراض، والسقفُ
# يمنع ضبطاً يُعلِّق الطلبَ دقائق (نمط ``parse_preload_retry_delays``).
DEFAULT_EDGE_RETRY_ATTEMPTS = 3
DEFAULT_EDGE_RETRY_BASE_DELAY_SECONDS = 0.5
MAX_EDGE_RETRY_ATTEMPTS = 6
MAX_EDGE_RETRY_BASE_DELAY_SECONDS = 5.0

#: أسماءُ استثناءات ``edge_tts.exceptions`` العابرة (بروتوكول/قناة لا مُدخَل).
_EDGE_TRANSIENT_NAMES = frozenset(
    {"WebSocketError", "UnknownResponse", "UnexpectedResponse", "NoAudioReceived"}
)
#: رموزُ HTTP من فئة 4xx التي تبقى عابرة (مهلة الطلب · تجاوز المعدّل).
_TRANSIENT_4XX = frozenset({408, 429})

logger = logging.getLogger("tts.providers")


def edge_retry_attempts() -> int:
    """عددُ المحاولات **الكلّيّ** (الأولى ضمنه) — ``1`` يعني بلا إعادة."""
    raw = os.getenv("TTS_EDGE_RETRY_ATTEMPTS", str(DEFAULT_EDGE_RETRY_ATTEMPTS))
    try:
        value = float(raw.strip())
    except (AttributeError, ValueError):
        logger.warning("TTS_EDGE_RETRY_ATTEMPTS غيرُ رقميّ؛ يُستعمَل الافتراض")
        return DEFAULT_EDGE_RETRY_ATTEMPTS
    if not math.isfinite(value) or value < 1 or value != int(value):
        logger.warning("TTS_EDGE_RETRY_ATTEMPTS ليس عدداً صحيحاً ≥ 1؛ يُستعمَل الافتراض")
        return DEFAULT_EDGE_RETRY_ATTEMPTS
    return min(int(value), MAX_EDGE_RETRY_ATTEMPTS)


def edge_retry_base_delay() -> float:
    """أساسُ التباعد بالثواني (يتضاعف بعد كلّ فشل) — ``0`` يعني إعادةً فوريّة."""
    raw = os.getenv("TTS_EDGE_RETRY_BASE_DELAY_SECONDS", str(DEFAULT_EDGE_RETRY_BASE_DELAY_SECONDS))
    try:
        value = float(raw.strip())
    except (AttributeError, ValueError):
        logger.warning("TTS_EDGE_RETRY_BASE_DELAY_SECONDS غيرُ رقميّ؛ يُستعمَل الافتراض")
        return DEFAULT_EDGE_RETRY_BASE_DELAY_SECONDS
    if not math.isfinite(value) or value < 0:
        logger.warning("TTS_EDGE_RETRY_BASE_DELAY_SECONDS غيرُ منتهٍ أو سالب؛ يُستعمَل الافتراض")
        return DEFAULT_EDGE_RETRY_BASE_DELAY_SECONDS
    return min(value, MAX_EDGE_RETRY_BASE_DELAY_SECONDS)


def is_transient_edge_error(exc: BaseException) -> bool:
    """هل الفشلُ عابرٌ تُجدي إعادتُه؟ المجهولُ ⇒ **لا** (لا نُعيد ما لا نفهمه).

    تُفحَص الأصنافُ كسولاً وبالاسم لأنّ ``edge_tts``/``aiohttp`` قد يغيبان أو يُرقَّعان
    بكعبٍ في طبقة الوحدات — فلا يُسقِط غيابُهما الاستيراد.
    """
    if isinstance(exc, (ValueError, TypeError)):
        return False  # مُدخَلٌ مرفوض — الإعادةُ لا تُصلِحه
    edge_exc = getattr(edge_tts, "exceptions", None)
    if edge_exc is not None:
        for name in _EDGE_TRANSIENT_NAMES:
            cls = getattr(edge_exc, name, None)
            if isinstance(cls, type) and isinstance(exc, cls):
                return True
    try:
        import aiohttp
    except ImportError:  # pragma: no cover - aiohttp تبعيّةُ edge_tts
        aiohttp = None  # type: ignore[assignment]
    if aiohttp is not None:
        if isinstance(exc, aiohttp.ClientResponseError):
            status = int(getattr(exc, "status", 0) or 0)
            return status >= 500 or status in _TRANSIENT_4XX
        if isinstance(exc, aiohttp.ClientError):
            return True  # اتّصالٌ/انقطاعٌ/مهلةُ مقبس
    return isinstance(exc, (TimeoutError, ConnectionError))


class EdgeTTSProvider(TTSProvider):
    """المزوّد الافتراضيّ: Microsoft edge-tts (متّصل بالإنترنت، على المعالِج).

    سلوك التركيب مطابقٌ حرفيّاً لمسار ``main._generate_speech`` السابق (نفس نداء
    ``edge_tts.Communicate`` ونفس تجميع البايتات) — فالمخرجات أمينةُ-البايت. والفرقُ
    الوحيد: فشلٌ **عابر** يُعاد بتباعدٍ أُسّيّ محدود (انظر الكتلة أعلاه).

    ``sleep`` محقونٌ كي تُختبَر حلقةُ الإعادة **نفسُها** بلا انتظارٍ حقيقيّ.
    """

    name = "edge_tts"
    external = True  # يُرسِل النصَّ إلى خدمة Microsoft — خارج حدّ المستأجِر.
    media_type = "audio/mpeg"

    def __init__(self, sleep: Callable[[float], Awaitable[object]] | None = None) -> None:
        self._sleep = sleep or asyncio.sleep

    def available(self) -> bool:
        return _EDGE_AVAILABLE

    async def _synthesize_once(
        self, text: str, voice: str, rate: str, pitch: str, volume: str
    ) -> bytes:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume=volume,
        )
        audio = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
        return audio.getvalue()

    async def synthesize(self, text: str, voice: str, rate: str, pitch: str, volume: str) -> bytes:
        if not _EDGE_AVAILABLE:  # pragma: no cover - edge إلزاميّ في الخدمة
            raise RuntimeError("edge_tts غير متوفّر")
        attempts = edge_retry_attempts()
        base_delay = edge_retry_base_delay()
        for attempt in range(1, attempts + 1):
            try:
                # مخزنٌ جديدٌ لكلّ محاولة: بايتاتُ محاولةٍ منقطعة لا تبلغ الناتج.
                return await self._synthesize_once(text, voice, rate, pitch, volume)
            except Exception as exc:
                if attempt >= attempts or not is_transient_edge_error(exc):
                    raise
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "edge-tts فشلٌ عابر (%s) في المحاولة %d/%d؛ إعادةٌ بعد %.2fث",
                    type(exc).__name__,
                    attempt,
                    attempts,
                    delay,
                )
                await self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover - الحلقة تُعيد أو ترمي


#: الإصدارُ الوحيد الذي فُحصت واجهتُه (توقيعات ``load``/``synthesize``/``synthesize_wav``).
PIPER_TTS_TARGET_VERSION = "1.8.0"


class PiperLoadError(RuntimeError):
    """النموذجُ موجودٌ لكنّه لا يُحمَّل (تالف/غير متوافق) — خطأٌ صريح، لا رجوعَ إلى مزوّدٍ آخر."""


def _require_audible_wav(audio: bytes) -> None:
    """ترويسةُ RIFF/WAVE صحيحة + معاملاتٌ معقولة + إطاراتٌ موجودةٌ فعلاً بطولها المُعلَن."""
    import wave

    if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise PiperLoadError("مخرجُ Piper ليس RIFF/WAVE")
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            channels, width, rate, frames = (
                w.getnchannels(),
                w.getsampwidth(),
                w.getframerate(),
                w.getnframes(),
            )
            data = w.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise PiperLoadError(f"WAV تالف: {exc}") from exc
    if channels < 1 or width not in (1, 2, 3, 4) or rate <= 0:
        raise PiperLoadError("معاملاتُ WAV غير صالحة")
    if frames <= 0 or len(data) != frames * channels * width:
        raise PiperLoadError("Piper أعاد WAV بلا إطاراتٍ صوتيّة كاملة")


class PiperProvider(TTSProvider):
    """Piper — شبكة عصبيّة على المعالِج (اختياريّ). لا يُتاح إلّا بالمكتبة + نموذج.

    مسار النموذج يُقرأ وقت النداء من ``PIPER_VOICE_PATH`` (أو تجاوز في الباني) كي
    تلتقط الاختبارات ضبط البيئة (monkeypatch) دون إعادة بناء.

    TTS-PIPER-PROVIDER-CALLS-THE-PRE-1.3-API-01: ``piper-tts`` ≥ 1.3 جعل ``synthesize`` مولِّدَ
    ``AudioChunk`` ونقل الكتابةَ إلى ``synthesize_wav(text, wav_file)``؛ النداءُ القديم
    ``synthesize(text, wav)`` يُمرِّر ملفَّ WAV مكانَ ``syn_config`` فلا يُكتب صوت. لذا:
      • ``synthesize_wav`` وحدَه، ورفضٌ صريح لمكتبةٍ لا تحمله (لا تخمينَ واجهة).
      • النموذجُ يُحمَّل **مرّةً لكلّ عمليّة** لكلّ مسار (قفلٌ يمنع التحميل المزدوج).
      • التركيبُ الثقيل في خيطٍ (``asyncio.to_thread``) لا في حلقة الطلبات، وبحدٍّ للتزامن
        (``PIPER_MAX_CONCURRENCY``، افتراضاً 1) كي لا يتنافس على المعالِج بلا سقف.
      • فشلُ التحميل أو مخرجٌ بلا إطارات ⇒ ``PiperLoadError`` صريح؛ والمُعالِجُ لا يرجع إلى edge.
      • الإصدارُ المستهدف صريح (``PIPER_TTS_TARGET_VERSION``): وجودُ ``synthesize_wav`` لا يُثبت
        توافقَ كلّ ≥ 1.3، فغيرُ المستهدف يُرفض بالاسم بدل أن يُفترض متوافقاً.
      • إلغاءُ الطلب لا يوقف خيطَ التركيب؛ لذا يُحرَّر مقعدُ التزامن عند **انتهاء الخيط** لا عند
        الإلغاء، فلا يتجاوز عددُ الخيوط العاملة الحدَّ.
    """

    name = "piper"
    media_type = "audio/wav"  # ``wave.open(buf, "wb")`` أدناه — وعاءُ RIFF/WAV.

    #: نماذجُ محمَّلة لكلّ مسار — مشتركة بين نسخ المزوّد في العمليّة نفسها.
    _voices: dict[str, Any] = {}
    _load_lock = threading.Lock()

    def __init__(self, voice_path: str | None = None) -> None:
        self._voice_path_override = voice_path
        self._semaphore: asyncio.Semaphore | None = None

    def _voice_path(self) -> str:
        return self._voice_path_override or os.getenv("PIPER_VOICE_PATH", "")

    def available(self) -> bool:
        path = self._voice_path()
        return bool(_PIPER_LIB_AVAILABLE and path and os.path.exists(path))

    @staticmethod
    def _installed_version() -> str | None:
        try:
            return importlib.metadata.version("piper-tts")
        except importlib.metadata.PackageNotFoundError:
            return None

    def _max_concurrency(self) -> int:
        try:
            return max(1, int(os.getenv("PIPER_MAX_CONCURRENCY", "1")))
        except ValueError:
            return 1

    def _load(self, path: str) -> Any:
        voice = self._voices.get(path)
        if voice is not None:
            return voice
        with self._load_lock:
            voice = self._voices.get(path)
            if voice is None:
                from piper import PiperVoice  # type: ignore[import-not-found]

                installed = self._installed_version()
                if installed != PIPER_TTS_TARGET_VERSION:
                    raise PiperLoadError(
                        f"piper-tts {installed or 'غير معروف'} ليس الإصدارَ المستهدف "
                        f"{PIPER_TTS_TARGET_VERSION} (لم يُتحقَّق من توافقه)"
                    )
                if not hasattr(PiperVoice, "synthesize_wav"):
                    raise PiperLoadError("piper-tts غير مدعوم: لا synthesize_wav (يلزم ≥ 1.3)")
                try:
                    voice = PiperVoice.load(path)
                except Exception as exc:  # noqa: BLE001 - أيُّ فشل تحميل ⇒ خطأٌ مُسمّى
                    raise PiperLoadError(f"تعذّر تحميل نموذج Piper: {type(exc).__name__}") from exc
                self._voices[path] = voice
        return voice

    def _synthesize_blocking(self, path: str, text: str) -> bytes:
        import wave

        voice = self._load(path)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            voice.synthesize_wav(text, wav)
        audio = buf.getvalue()
        _require_audible_wav(audio)
        return audio

    async def synthesize(self, text: str, voice: str, rate: str, pitch: str, volume: str) -> bytes:
        if not self.available():
            raise RuntimeError("Piper غير متاح (المكتبة أو PIPER_VOICE_PATH مفقود)")
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrency())
        semaphore = self._semaphore
        await semaphore.acquire()
        try:
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(None, self._synthesize_blocking, self._voice_path(), text)
        except BaseException:
            semaphore.release()
            raise
        # المقعدُ يُحرَّر حين ينتهي الخيطُ فعلاً — لا حين يُلغى الطلبُ المنتظِر (shield).
        future.add_done_callback(lambda _f: semaphore.release())
        return await asyncio.shield(future)


class XTTSProvider(TTSProvider):
    """Coqui XTTS — تركيب عصبيّ يفضّل المعالِج الرسوميّ (اختياريّ، أفضل-جهد).

    لا يُتاح إلّا حين تُستورَد مكتبة ``TTS`` **و** يُفعَّل صراحةً عبر البيئة
    (``TTS_GPU_PROVIDER=xtts`` أو ``XTTS_ENABLE=1``) — تماشياً مع
    ``docker-compose.v9.gpu.yml`` (يضبط ``TTS_GPU_PROVIDER``). CPU/edge يبقى الآمن.
    """

    name = "xtts"

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or os.getenv(
            "XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2"
        )

    def _enabled(self) -> bool:
        gpu = os.getenv("TTS_GPU_PROVIDER", "").strip().lower() == "xtts"
        flag = os.getenv("XTTS_ENABLE", "").strip().lower() in {"1", "true", "yes", "on"}
        return gpu or flag

    def available(self) -> bool:
        return bool(_XTTS_LIB_AVAILABLE and self._enabled())

    async def synthesize(self, text: str, voice: str, rate: str, pitch: str, volume: str) -> bytes:
        if not self.available():
            raise RuntimeError("XTTS غير متاح (المكتبة غير مثبّتة أو غير مُفعَّل)")
        # مسار فعليّ (يُنفَّذ فقط على بيئة GPU مُفعّلة — غير مُغطّى بالوحدات).
        from TTS.api import TTS as CoquiTTS  # type: ignore[import-not-found]  # pragma: no cover

        engine = CoquiTTS(self._model_name)  # pragma: no cover
        return engine.tts(text=text, language="ar")  # pragma: no cover


# ── السجلّ والاختيار (منطق نقيّ) ───────────────────────────────────────────────
DEFAULT_PROVIDER_NAME = "edge_tts"


def build_registry() -> list[TTSProvider]:
    """يبني سجلّ المزوّدين مرتّباً؛ edge أوّلاً ودائماً هو الافتراضيّ.

    البناء لا يستورد أيّ محرّك اختياريّ ولا يرمي — كائنات المزوّدين خفيفة، وتوفّرها
    يُحسَب كسولاً في ``available()``.
    """
    return [EdgeTTSProvider(), PiperProvider(), XTTSProvider()]


def _default_provider(registry: list[TTSProvider]) -> TTSProvider:
    by_name = {p.name: p for p in registry}
    if DEFAULT_PROVIDER_NAME in by_name:
        return by_name[DEFAULT_PROVIDER_NAME]
    # حارس: سجلّ بلا edge (لا يحدث في الخدمة) ⇒ أوّل متاح، وإلّا أوّل عنصر.
    for p in registry:
        if p.available():
            return p
    return registry[0]


def select_provider(requested: str | None, registry: list[TTSProvider]) -> TTSProvider:
    """يختار المزوّد المناسب بلا اختيار صامت لغير المتاح.

    القواعد:
      • طلب صريح لمزوّد **متاح** ⇒ يُختار هو.
      • طلب صريح لمزوّد **غير متاح** (أو اسم مجهول) ⇒ سقوطٌ آمن إلى edge الافتراضيّ.
      • لا طلب (None/فارغ) ⇒ المزوّد الافتراضيّ (edge).

    دالّة نقيّة: تعتمد فقط على ``requested`` و``registry`` (وعلى ``available()`` لكلّ
    مزوّد) — قابلة للاختبار بمزوّدين وهميّين يتحكّمون بـ``available()``.
    """
    default = _default_provider(registry)
    if not requested:
        return default
    by_name = {p.name: p for p in registry}
    chosen = by_name.get(requested)
    if chosen is not None and chosen.available():
        return chosen
    return default


def select_provider_for_policy(
    requested: str | None, registry: list[TTSProvider], external_allowed: bool
) -> TTSProvider | None:
    """يختار مزوّداً **تسمح به السياسة** أو ``None`` — لا سقوطَ صامتاً إلى مزوّدٍ خارجيّ.

    TTS-LOCAL-ONLY-FALLS-BACK-TO-EXTERNAL-PROVIDER-01: ``select_provider`` يسقط إلى edge
    حين يتعذّر المطلوب، وهذا صحيحٌ فقط حين يُسمَح بالإرسال الخارجيّ. حين لا يُسمَح:
    مزوّدٌ محلّيٌّ متاح (المطلوبُ إن كان محلّيّاً متاحاً، وإلّا أوّلُ محلّيٍّ متاح)، وإلّا
    ``None`` ليُعيد المُعالِج 503 مُسمّى بلا أيّ نداءٍ خارجيّ.
    """
    if external_allowed:
        return select_provider(requested, registry)
    local = [p for p in registry if not p.external and p.available()]
    for p in local:
        if p.name == requested:
            return p
    return local[0] if local else None
