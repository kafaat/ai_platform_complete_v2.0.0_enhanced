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
import io
import os

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

    @abc.abstractmethod
    def available(self) -> bool:
        """هل المزوّد جاهز فعليّاً (المكتبة + النموذج/العلم)؟ لا يرمي أبداً."""
        raise NotImplementedError

    @abc.abstractmethod
    async def synthesize(self, text: str, voice: str, rate: str, pitch: str, volume: str) -> bytes:
        """يركّب ``text`` بالصوت المُعطى ويُرجِع بايتات الصوت. يرمي إن كان غير متاح."""
        raise NotImplementedError


class EdgeTTSProvider(TTSProvider):
    """المزوّد الافتراضيّ: Microsoft edge-tts (متّصل بالإنترنت، على المعالِج).

    سلوك التركيب مطابقٌ حرفيّاً لمسار ``main._generate_speech`` السابق (نفس نداء
    ``edge_tts.Communicate`` ونفس تجميع البايتات) — فالمخرجات أمينةُ-البايت.
    """

    name = "edge_tts"

    def available(self) -> bool:
        return _EDGE_AVAILABLE

    async def synthesize(self, text: str, voice: str, rate: str, pitch: str, volume: str) -> bytes:
        if not _EDGE_AVAILABLE:  # pragma: no cover - edge إلزاميّ في الخدمة
            raise RuntimeError("edge_tts غير متوفّر")
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


class PiperProvider(TTSProvider):
    """Piper — شبكة عصبيّة على المعالِج (اختياريّ). لا يُتاح إلّا بالمكتبة + نموذج.

    مسار النموذج يُقرأ وقت النداء من ``PIPER_VOICE_PATH`` (أو تجاوز في الباني) كي
    تلتقط الاختبارات ضبط البيئة (monkeypatch) دون إعادة بناء.
    """

    name = "piper"

    def __init__(self, voice_path: str | None = None) -> None:
        self._voice_path_override = voice_path

    def _voice_path(self) -> str:
        return self._voice_path_override or os.getenv("PIPER_VOICE_PATH", "")

    def available(self) -> bool:
        path = self._voice_path()
        return bool(_PIPER_LIB_AVAILABLE and path and os.path.exists(path))

    async def synthesize(self, text: str, voice: str, rate: str, pitch: str, volume: str) -> bytes:
        if not self.available():
            raise RuntimeError("Piper غير متاح (المكتبة أو PIPER_VOICE_PATH مفقود)")
        # مسار فعليّ (يُنفَّذ فقط حين تتوفّر المكتبة والنموذج — غير مُغطّى بالوحدات).
        import wave  # pragma: no cover

        from piper import PiperVoice  # type: ignore[import-not-found]  # pragma: no cover

        pv = PiperVoice.load(self._voice_path())  # pragma: no cover
        buf = io.BytesIO()  # pragma: no cover
        with wave.open(buf, "wb") as wav:  # pragma: no cover
            pv.synthesize(text, wav)  # pragma: no cover
        return buf.getvalue()  # pragma: no cover


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
