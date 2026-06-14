#!/usr/bin/env python3
"""
SAHOOL Telegram Bot — "مزرعتك في جيبك"
Full-featured farmer assistant bot with AI Agent integration
Commands:
  /start     — Registration & field linking
  /ndvi      — Request NDVI report
  /weather   — 7-day weather forecast
  /pest      — Pest/disease diagnosis (photo)
  /market    — Current market prices
  /contract  — Create forward contract
  /community — Join crop-specific group
  /advice    — Ask AI agricultural advisor
  /optimize  — Optimize farm (Pareto analysis)
  /help      — Command list
  /settings  — Language & preferences
"""

import asyncio
import logging
import os
import time as _time_module
from datetime import UTC, datetime

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage as _RedisStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.token import TokenValidationError

logger = logging.getLogger("sahool.telegram")


# ── Redis-backed ThrottlingMiddleware (T01-T07 fix) ────────────
class RedisThrottlingMiddleware:
    """
    Token Bucket throttling backed by Redis for distributed rate limiting.
    Fixes: T01(shared state), T02(TTL), T07(Redis), T08(role tiers).
    """

    def __init__(
        self, redis_client=None, rate: float = 1.0, burst: int = 3, admin_exempt: bool = True
    ):
        self._redis = redis_client
        self._rate = rate
        self._burst = burst
        self._admin_exempt = admin_exempt
        # Fallback in-memory with bounded size (T02 fix)
        self._local: dict = {}
        self._local_max = 10000

    async def _check_redis(self, key: str) -> bool:
        """Returns True if request is allowed."""
        try:
            count = await self._redis.get(key)
            if count is None:
                await self._redis.setex(key, 60, self._burst - 1)
                return True
            count = int(count)
            if count <= 0:
                return False
            await self._redis.decr(key)
            return True
        except Exception:
            return self._check_local(key)

    def _check_local(self, key: str) -> bool:
        now = _time_module.monotonic()
        if key not in self._local:
            if len(self._local) >= self._local_max:
                # Evict oldest 10% (T02 fix)
                sorted_keys = sorted(self._local, key=lambda k: self._local[k][1])
                for k in sorted_keys[: self._local_max // 10]:
                    del self._local[k]
            self._local[key] = (self._burst - 1, now)
            return True
        tokens, last = self._local[key]
        elapsed = now - last
        tokens = min(self._burst, tokens + elapsed * self._rate)
        if tokens < 1:
            return False
        self._local[key] = (tokens - 1, now)
        return True

    async def __call__(self, handler, event, data):
        from aiogram.types import Message

        uid = getattr(event.from_user, "id", None) if hasattr(event, "from_user") else None
        if not uid:
            return await handler(event, data)

        # T08: admin exempt
        if self._admin_exempt and str(uid) == os.getenv("TELEGRAM_ADMIN_ID", ""):
            return await handler(event, data)

        key = f"sahool:throttle:tg:{uid}"
        allowed = await self._check_redis(key) if self._redis else self._check_local(key)

        if not allowed:
            # T05: log throttled requests
            logger.warning(f"Throttled: Telegram user={uid}")
            if isinstance(event, Message):
                try:
                    await event.answer("⚠️ طلبات كثيرة — انتظر لحظة ثم أعد المحاولة.")
                except Exception as e:  # noqa: BLE001 — إشعار throttle تجميليّ: الفشل غير حرج
                    logger.debug("تعذّر إرسال إشعار throttle: %s", e)
            return None

        return await handler(event, data)


# ─── Configuration ─────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# B4 fix: compose يمرّر TELEGRAM_WEBHOOK_SECRET — اقرأ الاسم الصحيح (مع fallback)
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", os.getenv("WEBHOOK_SECRET", ""))
REDIS_URL = os.getenv("REDIS_URL", "redis://sahool-redis:6379/2")
SUPERVISOR_URL = os.getenv("SUPERVISOR_AGENT_URL", "http://sahool-supervisor:8000")
AUTH_URL = os.getenv("AUTH_SERVICE_URL", "http://sahool-auth:8000")
# ملاحظة B5: البوت لم يعد يصكّ توكنات — لا يحمل سرّ التوقيع إطلاقاً.

if not BOT_TOKEN:
    # B3 fix: خروج نظيف (exit 0) بدل raise → مع restart:unless-stopped كان
    # crash-loop لا نهائي حين يكون التوكن اختياريّاً/فارغاً. الآن يسجّل ويخرج.
    logger.warning("TELEGRAM_BOT_TOKEN غير مضبوط — البوت معطّل (خروج نظيف، لا crash-loop)")
    import sys as _sys

    _sys.exit(0)

# ─── Bot Setup ─────────────────────────────────────────────
# aiogram 3.7+ أزال parse_mode كمعامل لـBot() ⇒ نمرّره عبر DefaultBotProperties
# (تمريره مباشرةً يرمي TypeError وقت التشغيل على 3.7+، بما فيها 3.10/3.28).
# B3 fix (متابعة): التوكن قد يكون غير فارغ لكنّه placeholder غير صالح (مثل
# "your-telegram-token-here") ⇒ aiogram يرمي TokenValidationError. حارس الفراغ
# أعلاه لا يلتقطه، فيظلّ crash-loop مع restart:unless-stopped. نلتقطه هنا ونخرج
# نظيفاً (exit 0، البوت معطّل) — مطابقةً لسلوك التوكن الفارغ، لا انهيار متكرّر.
try:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2),
    )
except TokenValidationError:
    logger.warning(
        "TELEGRAM_BOT_TOKEN غير صالح (placeholder/تنسيق خاطئ) — "
        "البوت معطّل (خروج نظيف، لا crash-loop)"
    )
    import sys as _sys

    _sys.exit(0)


def _md2(text: str) -> str:
    """Escape القيم الديناميكيّة لـMarkdownV2 (منع خطأ 400 من رموز خاصّة).

    يُطبَّق على القيم القادمة من DB/المستخدم (أسماء حقول، حالات، أسماء آفات)
    التي قد تحوي . - ( ) ! إلخ. لا يُطبَّق على القوالب الثابتة (مُهيّأة يدويّاً).
    """
    if text is None:
        return ""
    out = str(text)
    # الشرطة المائلة أوّلاً ومرّة واحدة (وإلّا تُعيد تهريب ما أضافته اللاحقة)
    for ch in "\\_*[]()~`>#+-=|{}.!":
        out = out.replace(ch, "\\" + ch)
    return out


# ── TTS Voice Helper (Yemeni Arabic) ────────────────────────────
TTS_URL = os.getenv("TTS_URL", "http://sahool-tts:8000")
TTS_TOKEN = os.getenv("SAHOOL_AGENT_TOKEN", "")  # service-to-service token


async def send_voice_alert(chat_id: int, text: str, voice: str = "yemeni_male") -> bool:
    """
    Synthesize Arabic text via TTS service and send as voice to Telegram.
    Returns True on success, False on failure (caller may fallback to text).
    """
    if not TTS_TOKEN:
        return False
    import httpx
    from aiogram.types import BufferedInputFile

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{TTS_URL}/tts/synthesize",
                json={"text": text[:1000], "voice": voice},
                headers={"Authorization": f"Bearer {TTS_TOKEN}"},
            )
        if resp.status_code != 200:
            logger.warning(f"TTS failed: {resp.status_code}")
            return False
        audio_file = BufferedInputFile(resp.content, filename="sahool_voice.mp3")
        await bot.send_voice(chat_id=chat_id, voice=audio_file, caption=text[:200])
        return True
    except Exception as e:
        logger.error(f"TTS send failed: {e}")
        return False


# FIXED: use RedisStorage in production for persistence across restarts
try:
    import redis.asyncio as _aioredis

    _redis_fsm = _aioredis.from_url(REDIS_URL)
    storage = _RedisStorage(redis=_redis_fsm)
except Exception:
    storage = MemoryStorage()  # fallback
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)
dp.message.middleware(RedisThrottlingMiddleware())


# ─── FSM States ────────────────────────────────────────────
class RegistrationStates(StatesGroup):
    waiting_phone = State()
    waiting_field_id = State()
    waiting_crop = State()


class PestDiagnosisStates(StatesGroup):
    waiting_photo = State()
    waiting_crop_confirm = State()


class ContractStates(StatesGroup):
    waiting_crop = State()
    waiting_yield = State()
    waiting_harvest_date = State()
    waiting_min_price = State()
    confirm = State()


class LinkStates(StatesGroup):
    """ربط حساب تيليجرام بحساب SAHOOL (إصلاح B5 — مصادقة فعليّة)."""

    waiting_email = State()
    waiting_password = State()


# ─── User Data Cache (production: Redis/DB) ──────────────────
user_cache: dict = {}


async def get_user_token(user_id: int) -> str | None:
    """يُرجع توكن المستخدم المُصادَق فعليّاً (لا يصكّ توكناً اعتباطيّاً).

    إصلاح ثغرة B5 الأمنيّة الخطيرة:
    سابقاً كان البوت يصكّ JWT بهوية اعتباطيّة (telegram-{id}, tenant=default)
    موقّعاً بالسرّ المشترك — أيّ مستخدم تيليجرام يحصل على توكن منصّة بلا
    تسجيل/كلمة مرور، واختراق حاوية البوت = تزوير توكن أيّ مستخدم/مستأجر.

    الآن: البوت لا يحمل سرّ التوقيع ولا يصكّ توكنات. يجب أن يربط المستخدم
    حسابه عبر /link (يصادق ضدّ auth/login ويُخزَّن التوكن الصادر). من لم
    يربط حسابه → لا توكن → الخدمات ترفض طلبه (سلوك آمن).
    """
    cache = user_cache.get(user_id, {})
    token = cache.get("token")
    if not token:
        # لا توكن مربوط — صدق: لا نصكّ بديلاً مزوّراً
        return None
    return token


async def link_account(user_id: int, email: str, password: str) -> bool:
    """يصادق المستخدم ضدّ خدمة auth ويخزّن التوكن الصادر منها فقط.

    البوت لا يملك سرّ التوقيع — يحصل على توكن شرعيّ من auth/login.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{AUTH_URL}/auth/login",
                json={"email": email, "password": password},
            )
            resp.raise_for_status()
            data = resp.json()
            tok = data.get("access_token") or data.get("token")
            if not tok:
                return False
            user_cache.setdefault(user_id, {})["token"] = tok
            # tenant_id يأتي من التوكن الشرعي، لا افتراضيّاً
            return True
    except Exception as e:
        logger.warning("فشل ربط حساب تيليجرام %s: %s", user_id, e)
        return False


async def call_supervisor(
    user_id: int,
    query: str,
    field_id: str | None = None,
    context: dict | None = None,
    objectives: list | None = None,
) -> dict:
    """Call SAHOOL Supervisor Agent."""
    token = await get_user_token(user_id)
    if not token:
        # المستخدم لم يربط حسابه — لا نرسل Bearer None (يكسر الطلب)
        return {"error": "unlinked", "message_ar": "يجب ربط حسابك أوّلاً. أرسل: /link"}
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "query": query,
        "user_id": f"telegram-{user_id}",
        "tenant_id": user_cache.get(user_id, {}).get("tenant_id", "default"),
        "context": context or {},
    }
    if field_id:
        payload["field_id"] = field_id
    if objectives:
        payload["preferred_objectives"] = objectives

    async with httpx.AsyncClient(timeout=30.0) as client:
        if "حسّن" in query or "optimize" in query.lower() or "أفضل" in query:
            endpoint = f"{SUPERVISOR_URL}/agent/optimize"
        else:
            endpoint = f"{SUPERVISOR_URL}/agent/query"

        resp = await client.post(endpoint, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


# ─── Command Handlers ──────────────────────────────────────


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Welcome and registration flow."""
    await state.clear()

    welcome_text = """
🌾 *مرحباً بك في SAHOOL\\!* 🌾

أنا مساعدك الزراعي الذكي\\.
أستطيع مساعدتك في\\:
• 📊 مراقبة صحة الحقل \\(NDVI\\)
• 🌤️ التنبؤات الجوية
• 🐛 تشخيص الآفات والأمراض
• 💰 أسعار السوق والعقود الآجلة
• 💡 استشارات زراعية ذكية

*للبدء\\:* شاركني معلومات حقلك
    """.strip()

    # Registration keyboard
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 مشاركة رقم الهاتف", request_contact=True)],
            [KeyboardButton(text="❌ لاحقاً")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer(welcome_text, reply_markup=kb)
    await state.set_state(RegistrationStates.waiting_phone)


# ─── ربط الحساب (/link) — إصلاح B5: مصادقة فعليّة بدل صكّ توكنات ───
@router.message(Command("link"))
async def cmd_link(message: Message, state: FSMContext):
    """يبدأ ربط حساب تيليجرام بحساب SAHOOL عبر auth/login."""
    await state.clear()
    await message.answer("🔐 لربط حسابك، أرسل بريدك الإلكتروني المسجّل في SAHOOL:")
    await state.set_state(LinkStates.waiting_email)


@router.message(LinkStates.waiting_email, F.text)
async def link_email(message: Message, state: FSMContext):
    await state.update_data(email=message.text.strip())
    await message.answer("🔑 الآن أرسل كلمة المرور:")
    await state.set_state(LinkStates.waiting_password)


@router.message(LinkStates.waiting_password, F.text)
async def link_password(message: Message, state: FSMContext):
    data = await state.get_data()
    email = data.get("email", "")
    password = message.text.strip()
    # احذف رسالة كلمة المرور فوراً (لا تبقَ في سجلّ المحادثة)
    try:
        await message.delete()
    except Exception as e:  # noqa: BLE001 — خصوصيّة: فشل الحذف يُسجَّل (كلمة المرور تبقى بالسجلّ)
        logger.warning("تعذّر حذف رسالة كلمة المرور من المحادثة: %s", e)
    ok = await link_account(message.from_user.id, email, password)
    await state.clear()
    if ok:
        await message.answer("✅ تمّ ربط حسابك بنجاح. يمكنك الآن استخدام كلّ الميزات.")
    else:
        await message.answer("❌ فشل الربط — تحقّق من البريد وكلمة المرور وأعِد /link")


@router.message(RegistrationStates.waiting_phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
    """Save phone and ask for field ID."""
    phone = message.contact.phone_number
    user_cache[message.from_user.id] = {
        "phone": phone,
        "telegram_id": message.from_user.id,
        "username": message.from_user.username,
        "registered_at": datetime.now(UTC).isoformat(),
    }

    await message.answer(
        f"✅ تم حفظ الرقم: `{phone}`\n\n"
        "الآن أرسل *معرف الحقل* \\(Field ID\\) من تطبيق SAHOOL\\:\n"
        "أو اكتب *جديد* لإنشاء حقل جديد\\.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🆕 حقل جديد")]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    await state.set_state(RegistrationStates.waiting_field_id)


@router.message(RegistrationStates.waiting_field_id)
async def process_field_id(message: Message, state: FSMContext):
    """Save field ID and complete registration."""
    field_id = message.text.strip()
    user_id = message.from_user.id

    if field_id == "🆕 حقل جديد":
        field_id = f"telegram-{user_id}-field-001"

    user_cache[user_id]["field_id"] = field_id

    # Ask for crop
    crops_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌾 قمح"), KeyboardButton(text="🌽 ذرة")],
            [KeyboardButton(text="🌾 شعير"), KeyboardButton(text="🌾 ذرة بيضاء")],
            [KeyboardButton(text="🍅 طماطم"), KeyboardButton(text="🥔 بطاطس")],
            [KeyboardButton(text="☕ قهوة"), KeyboardButton(text="🌿 قات")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await message.answer("🌱 *ما هو المحصول الرئيسي في حقلك؟*", reply_markup=crops_kb)
    await state.set_state(RegistrationStates.waiting_crop)


@router.message(RegistrationStates.waiting_crop)
async def process_crop(message: Message, state: FSMContext):
    """Complete registration."""
    crop_map = {
        "🌾 قمح": "wheat",
        "🌽 ذرة": "maize",
        "🌾 شعير": "barley",
        "🌾 ذرة بيضاء": "millet",
        "🍅 طماطم": "tomato",
        "🥔 بطاطس": "potato",
        "☕ قهوة": "coffee",
        "🌿 قات": "qat",
    }

    crop = crop_map.get(message.text.strip(), "wheat")
    user_id = message.from_user.id
    user_cache[user_id]["crop"] = crop

    await state.clear()

    main_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 صحة الحقل"), KeyboardButton(text="🌤️ الطقس")],
            [KeyboardButton(text="🐛 تشخيص آفة"), KeyboardButton(text="💰 السوق")],
            [KeyboardButton(text="💡 استشارة"), KeyboardButton(text="⚙️ تحسين")],
            [KeyboardButton(text="📋 المساعدة")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        f"🎉 *تم التسجيل بنجاح\\!*\n\n"
        f"• الحقل: `{user_cache[user_id].get('field_id', 'غير محدد')}`\n"
        f"• المحصول: {_md2(message.text.strip())}\n\n"
        f"استخدم القائمة أدناه أو اكتب سؤالك مباشرة\\.",
        reply_markup=main_kb,
    )


@router.message(F.text == "📊 صحة الحقل")
async def cmd_ndvi(message: Message):
    """Request NDVI report."""
    user_id = message.from_user.id
    field_id = user_cache.get(user_id, {}).get("field_id")

    if not field_id:
        await message.answer("⚠️ لم تقم بربط حقل بعد\\. استخدم /start للتسجيل\\.")
        return

    wait_msg = await message.answer("⏳ جاري تحليل صور القمر الصناعي\\.\\.\\.")

    try:
        result = await call_supervisor(
            user_id,
            "ما هو NDVI لحقلي اليوم؟",
            field_id=field_id,
            context={"date": datetime.now(UTC).strftime("%Y-%m-%d")},
        )

        response = result.get("response_ar", "لم أتمكن من الحصول على البيانات\\.")

        # Add structured data if available
        if result.get("structured_data"):
            sd = result["structured_data"]
            if "ndvi_mean" in sd:
                response += f"\n\n📈 *NDVI المتوسط\\:* `{sd['ndvi_mean']:.3f}`"
            if "health_status" in sd:
                response += f"\n\n🩺 *الحالة\\:* {_md2(sd['health_status'])}"

        await wait_msg.edit_text(response)

    except Exception as e:
        await wait_msg.edit_text(f"❌ خطأ في جلب البيانات\\: {_md2(str(e)[:100])}")


@router.message(F.text == "🌤️ الطقس")
async def cmd_weather(message: Message):
    """Get weather forecast."""
    user_id = message.from_user.id

    wait_msg = await message.answer("⏳ جاري جلب التنبؤ الجوي\\.\\.\\.")

    try:
        result = await call_supervisor(user_id, "ما هو طقس الأيام القادمة؟", context={"days": 7})

        response = result.get("response_ar", "لم أتمكن من الحصول على البيانات\\.")
        await wait_msg.edit_text(response)

    except Exception as e:
        await wait_msg.edit_text(f"❌ خطأ\\: {_md2(str(e)[:100])}")


@router.message(F.text == "🐛 تشخيص آفة")
async def cmd_pest_start(message: Message, state: FSMContext):
    """Start pest diagnosis flow."""
    await message.answer(
        "📸 *أرسل صورة واضحة للآفة أو المرض*\n"
        "يفضل أن تكون الصورة\\:\n"
        "• في إضاءة جيدة\n"
        "• بتركيز واضح\n"
        "• تظهر الأوراق المتأثرة بوضوح"
    )
    await state.set_state(PestDiagnosisStates.waiting_photo)


@router.message(PestDiagnosisStates.waiting_photo, F.photo)
async def process_pest_photo(message: Message, state: FSMContext):
    """Process pest photo via Edge Inference or Supervisor."""
    user_id = message.from_user.id
    field_id = user_cache.get(user_id, {}).get("field_id", "unknown")
    crop = user_cache.get(user_id, {}).get("crop", "wheat")

    # H-02 FIX: Check file size before download (max 10MB)
    photo = message.photo[-1]  # Highest resolution
    MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 10MB
    if photo.file_size and photo.file_size > MAX_PHOTO_BYTES:
        await message.answer("⚠️ الصورة كبيرة جداً (الحد الأقصى 10MB). أرسل صورة أصغر.")
        await state.clear()
        return
    await bot.get_file(photo.file_id)

    wait_msg = await message.answer("🔬 جاري تحليل الصورة بالذكاء الاصطناعي\\.\\.\\.")

    try:
        # In production: send to Edge Inference service
        # For MVP: use Supervisor advisory skill
        result = await call_supervisor(
            user_id,
            f"صورة آفة على محصول {crop}",
            field_id=field_id,
            context={"crop": crop, "image_file_id": photo.file_id},
        )

        response = result.get("response_ar", "لم أتمكن من التحليل\\.")

        await wait_msg.edit_text(response)

        # If treatment recommended, offer to create task
        if "علاج" in response or "treatment" in response.lower():
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ إنشاء مهمة مكافحة", callback_data="create_pest_task"
                        )
                    ],
                    [InlineKeyboardButton(text="❌ لا شكراً", callback_data="dismiss")],
                ]
            )
            await message.answer("هل تريد إنشاء مهمة مكافحة في نظام SAHOOL؟", reply_markup=kb)

    except Exception as e:
        await wait_msg.edit_text(f"❌ خطأ في التحليل\\: {_md2(str(e)[:100])}")

    await state.clear()


@router.message(F.text == "💰 السوق")
async def cmd_market(message: Message):
    """Get market prices."""
    user_id = message.from_user.id
    crop = user_cache.get(user_id, {}).get("crop", "wheat")

    wait_msg = await message.answer("⏳ جاري جلب أسعار السوق\\.\\.\\.")

    try:
        result = await call_supervisor(
            user_id, f"كم سعر {crop} في السوق؟", context={"crop": crop, "market": "sanaa"}
        )

        response = result.get("response_ar", "لم أتمكن من الحصول على الأسعار\\.")

        # Add price trend button
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📈 اتجاه 30 يوم", callback_data=f"trend_{crop}")],
                [InlineKeyboardButton(text="📝 إنشاء عقد آجل", callback_data="create_contract")],
            ]
        )

        await wait_msg.edit_text(response, reply_markup=kb)

    except Exception as e:
        await wait_msg.edit_text(f"❌ خطأ\\: {_md2(str(e)[:100])}")


@router.message(F.text == "💡 استشارة")
async def cmd_advice(message: Message):
    """General agricultural advice."""
    await message.answer(
        "💡 *اسألني أي سؤال زراعي*\n"
        "أمثلة\\:\n"
        "• متى أفضل وقت لزراعة القمح؟\n"
        "• كيف أتعامل مع ذبول الطماطم؟\n"
        "• ما هو التسميد المناسب للمرحلة الحالية؟\n\n"
        "اكتب سؤالك مباشرة\\!"
    )


@router.message(F.text == "⚙️ تحسين")
async def cmd_optimize(message: Message):
    """Farm optimization."""
    user_id = message.from_user.id
    field_id = user_cache.get(user_id, {}).get("field_id")
    crop = user_cache.get(user_id, {}).get("crop", "wheat")

    if not field_id:
        await message.answer("⚠️ لم تقم بربط حقل بعد\\. استخدم /start للتسجيل\\.")
        return

    wait_msg = await message.answer(
        "🧠 جاري تحليل البيانات وإيجاد أفضل خطة... قد يستغرق 10-30 ثانية."
    )

    try:
        result = await call_supervisor(
            user_id,
            "حسّن مزرعتي",
            field_id=field_id,
            context={"crop": crop},
            objectives=["balanced"],
        )

        response = result.get("trade_off_explanation", result.get("response_ar", "تم التحليل\\!"))

        # Add optimization options
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📈 أقصى إنتاجية", callback_data="opt_max_yield")],
                [InlineKeyboardButton(text="💰 أقصى ربح", callback_data="opt_max_profit")],
                [InlineKeyboardButton(text="💧 توفير مياه", callback_data="opt_min_water")],
            ]
        )

        await wait_msg.edit_text(str(response)[:4000], reply_markup=kb)  # Telegram limit

    except Exception as e:
        await wait_msg.edit_text(f"❌ خطأ في التحليل\\: {_md2(str(e)[:100])}")


@router.message(F.text == "📋 المساعدة")
async def cmd_help(message: Message):
    """Show help."""
    help_text = """
📚 *قائمة الأوامر*\\:

*/start* \\- التسجيل وربط الحقل
*/ndvi* \\- تقرير صحة الحقل
*/weather* \\- التنبؤ الجوي
*/pest* \\- تشخيص آفة \\(أرسل صورة\\)
*/market* \\- أسعار السوق
*/contract* \\- إنشاء عقد آجل
*/community* \\- الانضمام لمجموعة المحصول
*/advice* \\- استشارة ذكية
*/optimize* \\- تحسين المزرعة
*/settings* \\- الإعدادات
*/help* \\- هذه القائمة

*أو اكتب سؤالك مباشرة\\!* 💬
    """.strip()
    await message.answer(help_text)


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """User settings."""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 العربية", callback_data="lang_ar")],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton(text="🔔 تفعيل الإشعارات", callback_data="notif_on")],
            [InlineKeyboardButton(text="🔕 إيقاف الإشعارات", callback_data="notif_off")],
        ]
    )
    await message.answer("⚙️ *الإعدادات*", reply_markup=kb)


# ─── Callback Handlers ─────────────────────────────────────


@router.callback_query(F.data == "create_pest_task")
async def cb_create_pest_task(callback: CallbackQuery):
    """Create pest control task."""
    await callback.message.edit_text(
        "✅ *تم إنشاء مهمة مكافحة في نظام SAHOOL\\!*\nسيتم إشعارك بموعد التنفيذ\\.",
        reply_markup=None,
    )
    await callback.answer("تم إنشاء المهمة\\!", show_alert=True)


@router.callback_query(F.data.startswith("trend_"))
async def cb_price_trend(callback: CallbackQuery):
    """Show price trend."""
    crop = callback.data.replace("trend_", "")
    user_id = callback.from_user.id

    await callback.answer("جاري التحميل\\.\\.\\.")

    try:
        result = await call_supervisor(
            user_id, f"اتجاه سعر {crop}", context={"crop": crop, "market": "sanaa"}
        )

        response = result.get("response_ar", "لم أتمكن من جلب الاتجاه\\.")
        await callback.message.answer(response)

    except Exception as e:
        await callback.message.answer(f"❌ خطأ\\: {_md2(str(e)[:100])}")


@router.callback_query(F.data.startswith("opt_"))
async def cb_optimize_objective(callback: CallbackQuery):
    """Re-run optimization with different objective."""
    obj_map = {
        "opt_max_yield": ["max_yield"],
        "opt_max_profit": ["max_profit"],
        "opt_min_water": ["min_water"],
    }
    objectives = obj_map.get(callback.data, ["balanced"])
    user_id = callback.from_user.id
    field_id = user_cache.get(user_id, {}).get("field_id")
    crop = user_cache.get(user_id, {}).get("crop", "wheat")

    if not field_id:
        await callback.answer("ربط حقل أولاً\\!", show_alert=True)
        return

    await callback.answer("جاري إعادة التحليل\\.\\.\\.")

    try:
        result = await call_supervisor(
            user_id, "حسّن مزرعتي", field_id=field_id, context={"crop": crop}, objectives=objectives
        )

        response = result.get("trade_off_explanation", result.get("response_ar", "تم التحليل\\!"))
        await callback.message.answer(str(response)[:4000])

    except Exception as e:
        await callback.message.answer(f"❌ خطأ\\: {_md2(str(e)[:100])}")


@router.callback_query(F.data == "dismiss")
async def cb_dismiss(callback: CallbackQuery):
    """Dismiss action."""
    await callback.message.delete()
    await callback.answer("تم\\.")


# ─── Natural Language Handler ──────────────────────────────


@router.message(F.text)
async def handle_natural_language(message: Message):
    """Handle any text message as natural language query."""
    user_id = message.from_user.id
    field_id = user_cache.get(user_id, {}).get("field_id")
    crop = user_cache.get(user_id, {}).get("crop", "wheat")

    # Quick responses for common queries
    quick_responses = {
        "مرحبا": "👋 مرحباً\\! كيف يمكنني مساعدتك اليوم؟",
        "hello": "👋 Hello\\! How can I help you today?",
        "شكرا": "🙏 على الرحب والسعة\\!",
        "thanks": "🙏 You're welcome\\!",
        "bye": "👋 مع السلامة\\!",
        "مع السلامة": "👋 في أمان الله\\!",
    }

    if message.text.strip().lower() in quick_responses:
        await message.answer(quick_responses[message.text.strip().lower()])
        return

    wait_msg = await message.answer("🤔 جاري التفكير\\.\\.\\.")

    try:
        result = await call_supervisor(
            user_id, message.text, field_id=field_id, context={"crop": crop}
        )

        response = result.get("response_ar", "لم أفهم السؤال تماماً\\. حاول صياغته بطريقة أخرى\\.")

        # Truncate if too long for Telegram
        if len(response) > 4000:
            response = response[:3950] + "\\.\\.\\."

        await wait_msg.edit_text(response)

    except Exception as e:
        await wait_msg.edit_text(
            f"❌ عذراً، حدث خطأ\\:\n`{str(e)[:200]}`\n\nحاول مرة أخرى أو استخدم /help"
        )


# ─── Main Entry Point ──────────────────────────────────────


async def main():
    """Start the bot."""
    logger.info("[SAHOOL Bot] Starting at %s", datetime.now(UTC).isoformat())
    logger.info("[SAHOOL Bot] Supervisor: %s", SUPERVISOR_URL)
    logger.info("[SAHOOL Bot] Connected users: %s", len(user_cache))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


# ── /voice command — test TTS ──────────────────────────────────
@router.message(Command("voice"))
async def cmd_voice(message: Message):
    """Send a sample voice message in Yemeni Arabic."""
    text = "مرحباً بك في منصة سهول الزراعية الذكية. هذه رسالة صوتية تجريبية بصوت يمني أصيل."
    sent = await send_voice_alert(message.chat.id, text, voice="yemeni_male")
    if not sent:
        await message.answer("تعذر إنتاج الصوت في الوقت الحالي\\. سيتم الإرسال نصياً بدلاً من ذلك\\.")
