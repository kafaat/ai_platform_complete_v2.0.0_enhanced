"""
SAHOOL v9.1.0 — services/tts-service/main.py
Text-to-Speech service using Microsoft Edge TTS with Yemeni Arabic voices.

Voices supported:
  - ar-YE-MaryamNeural  (Yemeni female)
  - ar-YE-SalehNeural   (Yemeni male)
  - ar-SA-HamedNeural   (Saudi male, fallback)
  - ar-EG-SalmaNeural   (Egyptian female, fallback)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from contextlib import asynccontextmanager

# edge_tts يبقى مستورَداً هنا رغم عدم استعماله مباشرةً في main: مُعالِج
# ``/tts/stream`` في ``routers/tts.py`` ينفذ إليه عبر ``main.edge_tts.Communicate``
# (تفكيك محفوظ السلوك) — إزالته تكسر البثّ. التركيب غير-البثّيّ يمرّ عبر providers.
import edge_tts  # noqa: F401
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from jose import JWTError, jwt
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field, field_validator

try:
    from shared.logging_config import setup_logging

    logger = setup_logging("tts-service")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","svc":"tts","level":"%(levelname)s","msg":"%(message)s"}',
    )
    logger = logging.getLogger("tts-service")

VERSION = "9.1.0"
_JWT_PUBLIC = os.getenv("JWT_PUBLIC_KEY", "")
JWT_SECRET = _JWT_PUBLIC if _JWT_PUBLIC else os.getenv("JWT_SECRET", "")
_JWT_ALG = "RS256" if _JWT_PUBLIC else "HS256"
# المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكّ التوكن (تدقيق B: iss لم يُفحَص).
_ALLOWED_ISS = {"sahool-auth", "sahool-platform"}

# تحصين الإنتاج (fail-closed، تماثُل مع auth/المنصّة): RS256 إلزاميّ — HS256 سرّ متماثل
# مشترَك لا يُنهي shared trust domain (أيّ خدمة تحمله تُزوّر توكناً). في الإنتاج بلا
# JWT_PUBLIC_KEY نرفض الإقلاع ما لم يُعطَّل صراحةً (مهرب ترحيل SAHOOL_ALLOW_HS256_IN_PROD=1).
if (
    not os.getenv("JWT_PUBLIC_KEY", "").strip()
    and os.getenv("SAHOOL_ENV", "development").strip().lower() == "production"
    and os.getenv("SAHOOL_ALLOW_HS256_IN_PROD", "").strip().lower()
    not in {"1", "true", "yes", "on"}
):
    raise RuntimeError(
        "RS256 مطلوب في الإنتاج: اضبط JWT_PUBLIC_KEY (HS256 لا يُنهي shared trust domain). "
        "للترحيل المؤقّت فقط: SAHOOL_ALLOW_HS256_IN_PROD=1."
    )
# توكن خدمة للنداءات خدمة-لخدمة (notification → tts). يطابق نمط بقيّة الخدمات
# (soil/guardrails): X-Agent-Token == SAHOOL_AGENT_TOKEN. يُقرأ وقت التشغيل في
# الدالّة كي تلتقط الاختبارات ضبط البيئة (monkeypatch) دون إعادة استيراد.
REDIS_URL = os.getenv("REDIS_URL", "redis://sahool-redis:6379/2")
CACHE_TTL = int(os.getenv("TTS_CACHE_TTL", "86400"))  # 24h
MAX_TEXT_LEN = int(os.getenv("TTS_MAX_TEXT_LEN", "1000"))

# Available voices
VOICES = {
    "yemeni_female": "ar-YE-MaryamNeural",
    "yemeni_male": "ar-YE-SalehNeural",
    "saudi_male": "ar-SA-HamedNeural",
    "egyptian_female": "ar-EG-SalmaNeural",
}
DEFAULT_VOICE = "yemeni_female"


# Metrics
def _metric(factory, name: str, *args, **kwargs):
    """ينشئ مقياساً أو يعيد القائم إن سُجِّل مسبقاً (يتحمّل إعادة تحميل الوحدة).

    سجلّ prometheus عامّ ويرمي «Duplicated timeseries» عند تكرار التسجيل — يحدث
    حين تُنفَّذ ``main`` مرّتين تحت اسمين مختلفين (تعدّد محمّلات الاختبارات، أو إعادة
    تحميل ساخنة). عوض الانهيار نعيد المجمِّع القائم. المسار الإنتاجيّ (تحميل واحد)
    يسلك الفرع الأوّل دون تغيير سلوك.
    """
    from prometheus_client import REGISTRY

    try:
        return factory(name, *args, **kwargs)
    except ValueError:
        existing = REGISTRY._names_to_collectors.get(name)
        if existing is None:  # pragma: no cover - تعارض بلا مجمِّع مطابق (لا يُتوقّع)
            raise
        return existing


TTS_REQUESTS = _metric(
    Counter,
    "sahool_tts_requests_total",
    "Total TTS requests",
    ["voice", "status", "cache"],
)
TTS_LATENCY = _metric(
    Histogram,
    "sahool_tts_latency_seconds",
    "TTS generation latency",
    ["voice"],
)

_redis: aioredis.Redis | None = None
_security = HTTPBearer(auto_error=False)


# ── Lifespan ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    try:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=False)
        await _redis.ping()
        logger.info("✅ Redis connected for TTS cache")
    except Exception as e:
        logger.warning(f"Redis unavailable — caching disabled: {e}")
        _redis = None
    logger.info("✅ TTS service started")
    yield
    if _redis:
        await _redis.aclose()
    logger.info("TTS service stopped")


app = FastAPI(
    title="SAHOOL TTS Service (Yemeni Arabic)",
    version=VERSION,
    lifespan=lifespan,
)


# ── Auth ─────────────────────────────────────────────────────
def _agent_token_valid(x_agent_token: str | None) -> bool:
    """مصادقة خدمة-لخدمة عبر السرّ المشترك X-Agent-Token == SAHOOL_AGENT_TOKEN.

    fail-closed: بلا سرّ مضبوط (التطوير/CI) ⇒ يُرفض هذا المسار (لا يفتح باباً
    بمفتاح فارغ) — كبقيّة الخدمات (soil/guardrails). يُقرأ السرّ وقت النداء كي
    تلتقط الاختبارات ضبط البيئة (monkeypatch) دون إعادة استيراد. مقارنة بزمن ثابت.
    """
    expected = os.getenv("SAHOOL_AGENT_TOKEN", "")
    if not expected or not x_agent_token:
        return False
    return hmac.compare_digest(x_agent_token, expected)


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_security),
    x_agent_token: str | None = Header(None, alias="X-Agent-Token"),
) -> dict:
    """Authenticate the caller via EITHER a service token OR a JWT (aud=sahool).

    مساران صريحان وكلاهما فشل-مغلق:
      • خدمة-لخدمة: رأس X-Agent-Token مطابق لـSAHOOL_AGENT_TOKEN (notification → tts).
        يُعيد هويّة خدميّة داخليّة بمستأجِر معزول (لا يخلط ذاكرة المستأجرين).
      • مستخدم: JWT بحاملة Bearer، aud=sahool، ومُصدِر داخليّ مسموح.
    إن غاب كلاهما/كانا غير صالحين ⇒ 401 (لا قبول لطلب غير مُصادَق).
    """
    # المسار الأوّل: توكن الخدمة المشترك (لا يتطلّب JWT_SECRET).
    if _agent_token_valid(x_agent_token):
        return {"sub": "service:internal", "iss": "sahool-service", "tenant_id": "__service__"}

    if not creds:
        raise HTTPException(401, "Authentication required")
    if not JWT_SECRET:
        raise HTTPException(500, "JWT_SECRET not configured")
    try:
        payload = jwt.decode(
            creds.credentials,
            JWT_SECRET,
            algorithms=[_JWT_ALG],
            audience="sahool",
        )
    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {e}") from e
    # تدقيق B: افرض المُصدِر بعد فكّ ناجح — مُصدِر مجهول ⇒ 401 كتوكن غير صالح.
    if payload.get("iss") not in _ALLOWED_ISS:
        raise HTTPException(401, "مُصدِر التوكن غير مسموح")
    return payload


# ── Models ───────────────────────────────────────────────────
class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN)
    voice: str = Field(default=DEFAULT_VOICE, description="Voice key from VOICES")
    rate: str = Field(default="+0%", description="Speech rate (e.g. -20%, +10%)")
    pitch: str = Field(default="+0Hz", description="Pitch adjustment")
    volume: str = Field(default="+0%", description="Volume adjustment")
    # اختياريّان (تراجُع آمن): طلب مزوّد صريح، وتطبيع نصّ عربيّ قبل التركيب. حين
    # يغيبان (الافتراضيّ) يبقى المسار edge بلا تطبيع ⇒ مخرجاتٌ أمينةُ-البايت.
    provider: str | None = Field(
        default=None, description="Explicit TTS provider (edge_tts/piper/xtts)"
    )
    normalize: bool = Field(default=False, description="Normalize Arabic text before synthesis")

    @field_validator("voice")
    @classmethod
    def validate_voice(cls, v: str) -> str:
        if v not in VOICES:
            raise ValueError(f"voice must be one of: {list(VOICES.keys())}")
        return v

    @field_validator("rate", "volume")
    @classmethod
    def validate_percent(cls, v: str) -> str:
        # FIX: الفحص السابق (بادئة +/- ولاحقة % فقط) كان يقبل قيماً مشوّهة مثل
        # '+abc%' أو '+%' فتُمرَّر إلى محرّك TTS. نفرض الصيغة الكاملة ±عدد%.
        if not re.fullmatch(r"[+-]\d+%", v):
            raise ValueError("rate/volume must be like '+10%' or '-20%'")
        return v


class VoicesResponse(BaseModel):
    voices: dict
    default: str
    # قائمة المزوّدين وتوفّرهم [{name, available, is_default}] — تُملأ في مُعالِج
    # /tts/voices (اختياريّة، افتراضها فارغ للتوافق مع المستهلِكين القائمين).
    providers: list = Field(default_factory=list)


# ── Core TTS ─────────────────────────────────────────────────
def _cache_key(
    tenant_id: str,
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    volume: str,
    provider: str | None = None,
    normalize: bool = False,
) -> str:
    """Generate deterministic, tenant-scoped cache key.

    عزل المستأجِر: tenant_id جزء من المفتاح (وبادئة منفصلة) كي لا يُقدَّم صوت
    مُخزَّن لمستأجِر إلى آخر (تسميم/تسريب ذاكرة عابر للمستأجرين). tenant فارغ
    يُطبَّع إلى '_' فلا يصطدم نطاقه بنطاق مستأجِر مُسمّى.

    provider/normalize يدخلان المفتاح **فقط** حين يخرجان عن الافتراضيّ (edge بلا
    تطبيع) — فتبقى مفاتيح المسار الافتراضيّ مطابقةً تماماً للسابق، بينما لا يختلط
    صوتُ مزوّد/نصٍّ مُطبَّع بصوت الافتراضيّ (لا تلوّث ذاكرة).
    """
    tid = tenant_id or "_"
    raw = f"{tid}:{voice}:{rate}:{pitch}:{volume}:{text}"
    if provider or normalize:
        raw = f"{raw}:prov={provider or ''}:norm={int(bool(normalize))}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"sahool:tts:{tid}:{digest}"


async def _generate_speech(
    text: str,
    voice_key: str,
    rate: str,
    pitch: str,
    volume: str,
    *,
    provider: str | None = None,
    normalize: bool = False,
) -> bytes:
    """Generate audio bytes via the selected TTS provider (edge default).

    المسار الافتراضيّ (provider=None، normalize=False) مطابقٌ حرفيّاً للسابق:
    اختيار edge + بلا تطبيع ⇒ نفس نداء ``edge_tts.Communicate`` ونفس تجميع
    البايتات ⇒ مخرجاتٌ أمينةُ-البايت. عند طلب مزوّد/تطبيع صريح يُطبَّق التطبيع أوّلاً
    ثمّ يُختار المزوّد المتاح (غير المتاح ⇒ سقوطٌ آمن إلى edge).
    """
    speak_text = ArabicTextNormalizer().normalize(text) if normalize else text
    prov = select_provider(provider, _PROVIDER_REGISTRY)
    voice = VOICES[voice_key]
    with TTS_LATENCY.labels(voice=voice_key).time():
        return await prov.synthesize(speak_text, voice, rate, pitch, volume)


# ── Endpoints ────────────────────────────────────────────────
# نُقلت كلّ المُعالِجات إلى وحدات ``routers/`` (تفكيك محفوظ السلوك). تُضمّ تلقائيّاً
# عبر ``register_routers(app)`` أدناه — المسارات/المعاملات/المخرجات/المصادقة مطابقة.


# ── تسجيل الراوترات تلقائيّاً (في النهاية، بعد app وكلّ التبعيّات المشتركة) ──────
# نضمن أنّ مجلّد الخدمة على ``sys.path`` كي يُحلّ ``router_registry``/``routers``
# مهما كانت آليّة تحميل ``main`` (تشغيل عاديّ، أو استيراد كحزمة، أو exec عبر spec في
# الاختبارات) — لا يغيّر أيّ سلوك مسار.
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_SVC_DIR = str(_Path(__file__).resolve().parent)
if _SVC_DIR not in _sys.path:
    _sys.path.insert(0, _SVC_DIR)

# تجريد المزوّدين + مطبّع النصّ العربيّ (وحدتان نقيّتان بلا fastapi). يُستوردان بعد
# ضمان _SVC_DIR على sys.path — كما يُحلّ router_registry — كي يعملا مهما كانت آليّة
# تحميل main (تشغيل/استيراد/exec عبر spec في الاختبارات). لا استيراد دائريّ:
# providers/arabic_normalizer لا يستوردان main.
from arabic_normalizer import ArabicTextNormalizer  # noqa: E402
from providers import (  # noqa: E402
    DEFAULT_PROVIDER_NAME,
    build_registry,
    select_provider,
)

# سجلّ المزوّدين المبنيّ مرّةً — edge افتراضيّ ودائم التوفّر؛ piper/xtts اختياريّان
# يُحسَب توفّرهما كسولاً. يُستهلَك في _generate_speech وفي مُعالِجات الحالة/الأصوات.
_PROVIDER_REGISTRY = build_registry()


def _provider_status() -> list[dict]:
    """لقطة توفّر لكلّ مزوّد [{name, available, is_default}] — تُشارك في voices/status."""
    return [
        {
            "name": p.name,
            "available": p.available(),
            "is_default": p.name == DEFAULT_PROVIDER_NAME,
        }
        for p in _PROVIDER_REGISTRY
    ]


from router_registry import register_routers  # noqa: E402

register_routers(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
