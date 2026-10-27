"""
stac_client.py — عميل STAC مرن (تحسين قلب النظام: الاستشعار).

المشكلة: SAHOOL يعتمد على Earth Search (بنية عامّة). في اليمن، الـlatency
عالية والانقطاعات متكرّرة. بحث STAC فاشل = لا صور = كلّ الخدمات تتوقّف.

هذه الوحدة تضيف مرونة تشغيليّة لقلب النظام:
  - إعادة محاولة بـbackoff أُسّي (مقاومة الانقطاع المؤقّت)
  - cache محلّي بـTTL (يقلّل الضغط على المصدر + مرونة ضدّ الانقطاع)
  - fallback للـcache المنتهي عند فشل المصدر (stale-if-error — أفضل من لا شيء)
  - تسجيل صحّة المصدر (للمراقبة)

صدق: لا تخترع صوراً. عند فشل المصدر + لا cache → تُبلّغ بالفشل بوضوح.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time

logger = logging.getLogger("sahool.stac_client")

# EXTRA-3: نسخة مخطّط المغلَّف المخزَّن (تدخل مفتاح الـcache فتعزل المُدخَلات القديمة).
_CACHE_SCHEMA = 2
_FALLBACK_WARNING = "المصدر الأساس متعذّر — نتيجة من مصدر احتياطي"


def _page_complete(data: dict) -> bool:
    """هل الصفحة المُعادة هي كلّ ما طابق البحث؟ (رابط next أو matched>returned ⇒ لا)."""
    links = data.get("links") or []
    if any(isinstance(link, dict) and link.get("rel") == "next" for link in links):
        return False
    matched = data.get("numberMatched")
    returned = data.get("numberReturned")
    if isinstance(matched, int) and isinstance(returned, int) and matched > returned:
        return False
    return True


class _Flight:
    """رحلة single-flight مشتركة: مهمّة حلّ واحدة + عدد المنتظِرين عليها."""

    __slots__ = ("task", "waiters")

    def __init__(self, task: asyncio.Task):
        self.task = task
        self.waiters = 0


class _CacheEntry:
    __slots__ = ("data", "fetched_at")

    def __init__(self, data: dict, fetched_at: float):
        self.data = data
        self.fetched_at = fetched_at

    def age(self) -> float:
        return time.time() - self.fetched_at


class ResilientStacClient:
    """عميل STAC بإعادة محاولة + cache + stale-if-error.

    cache طبقتان: Redis (مشترك عبر النسخ، يبقى عبر إعادة التشغيل) إن توفّر،
    وإلّا الذاكرة (للجلسة). يتدهور بلطف: فشل Redis → ذاكرة، لا يعطّل الخدمة.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        cache_ttl: float = 900.0,
        redis_url: str | None = None,
        fallback_url: str | None = None,
        fallback_urls: list | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_ttl = cache_ttl  # 15 دقيقة افتراضي (الصور لا تتغيّر سريعاً)
        self.redis_url = redis_url
        # مصادر احتياطيّة (سلسلة): تُجرَّب بالترتيب عند فشل الأساس قبل stale.
        # fallback_url (مفرد) للتوافق الخلفي؛ fallback_urls (قائمة) للتعدّد.
        chain = []
        if fallback_url:
            chain.append(fallback_url.rstrip("/"))
        if fallback_urls:
            chain.extend(u.rstrip("/") for u in fallback_urls if u)
        self.fallback_urls = chain
        self._cache: dict[str, _CacheEntry] = {}  # ذاكرة (fallback)
        self._redis = None  # يُهيّأ كسولاً
        self._redis_tried = False
        # v6-F6: single-flight — طلبات miss متطابقة متزامنة تتشارك POST واحداً بدل
        # قصف المصدر العامّ (Earth Search). خريطة مفتاح→Future (داخل العمليّة).
        self._inflight: dict[str, _Flight] = {}
        # عدّادات صحّة المصدر (للمراقبة /metrics)
        self.stats = {
            "requests": 0,
            "cache_hits": 0,
            "retries": 0,
            "failures": 0,
            "stale_served": 0,
            "redis_hits": 0,
            "fallback_served": 0,
            "coalesced": 0,
        }

    async def _get_redis(self):
        """يهيّئ Redis كسولاً مرّة واحدة. فشله لا يعطّل (يتدهور للذاكرة)."""
        if self._redis_tried:
            return self._redis
        self._redis_tried = True
        if not self.redis_url:
            return None
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
            await r.ping()
            self._redis = r
            logger.info("STAC cache: Redis متّصل (مشترك)")
        except Exception as e:  # noqa: BLE001
            logger.warning("STAC cache: Redis غير متاح (%s) — ذاكرة فقط", e)
            self._redis = None
        return self._redis

    def _key(self, payload: dict) -> str:
        """مفتاح cache مستقرّ من محتوى البحث + إعداد المزوّدين.

        EXTRA-3: Redis مشترك عبر النسخ؛ نسخة مضبوطة على كتالوج/سلسلة احتياطي مختلفة
        لا يجوز أن تقرأ نتيجة مزوّد آخر. ``_CACHE_SCHEMA`` يعزل المُدخَلات القديمة الخام
        (بلا مغلَّف provenance) فلا تُقدَّم بعد الترقية بلا هويّة مصدرها.
        """
        norm = json.dumps(
            {
                "schema": _CACHE_SCHEMA,
                "primary": self.base_url,
                "fallbacks": self.fallback_urls,
                "payload": payload,
            },
            sort_keys=True,
        )
        return hashlib.sha256(norm.encode()).hexdigest()[:24]

    async def _cache_get(self, key: str) -> _CacheEntry | None:
        """يقرأ من Redis (مشترك) ثمّ الذاكرة. يُرجِع _CacheEntry أو None."""
        r = await self._get_redis()
        if r is not None:
            try:
                raw = await r.get(f"stac:{key}")
                if raw:
                    obj = json.loads(raw)
                    self.stats["redis_hits"] += 1
                    return _CacheEntry(obj["data"], obj["fetched_at"])
            except Exception:  # noqa: BLE001 — فشل Redis → ذاكرة
                pass
        return self._cache.get(key)

    async def _cache_set(self, key: str, data: dict) -> None:
        """يكتب في Redis (مشترك، بـTTL) + الذاكرة (fallback)."""
        now = time.time()
        self._cache[key] = _CacheEntry(data, now)
        r = await self._get_redis()
        if r is not None:
            try:
                payload = json.dumps({"data": data, "fetched_at": now})
                # TTL مضاعف في Redis للسماح بـstale-if-error بعد انتهاء الصلاحيّة
                await r.set(f"stac:{key}", payload, ex=int(self.cache_ttl * 4))
            except Exception:  # noqa: BLE001
                pass

    async def search(self, payload: dict) -> dict:
        """يبحث STAC مع مرونة كاملة. يُرجِع نتيجة JSON أو يرفع عند الفشل التامّ.

        الترتيب: cache طازج (Redis→ذاكرة) → الأساس بإعادة محاولة →
        مصدر احتياطي (Planetary Computer) → cache منتهٍ (stale) → فشل.
        """
        self.stats["requests"] += 1
        key = self._key(payload)

        # ١. cache طازج؟ (Redis مشترك ثمّ ذاكرة)
        entry = await self._cache_get(key)
        if entry and entry.age() < self.cache_ttl:
            self.stats["cache_hits"] += 1
            return {**entry.data, "_cache": "fresh"}

        # v6-F6: single-flight — إن كان طلب متطابق قيد التنفيذ، انتظر نتيجته بدل POST
        # ثانٍ على المصدر العامّ (تفادي stampede عند backfill متزامن لنفس الحقل/النافذة).
        # EXTRA-2: الحلّ يجري في مهمّة مشتركة مستقلّة عن أيّ طالب، وكلّ طالب (قائداً
        # أو تابعاً) ينتظرها عبر ``shield``: إلغاء القائد لا يترك التابعين على Future
        # لم يُحسَم (كان ``except Exception`` لا يلتقط CancelledError)، وإلغاء تابعٍ لا
        # يُلغي العمل المشترك على البقيّة. تُلغى المهمّة فقط حين يغادر آخر منتظِر.
        flight = self._inflight.get(key)
        coalesced = flight is not None
        if flight is None:
            flight = _Flight(asyncio.ensure_future(self._resolve_uncached(key, payload, entry)))
            self._inflight[key] = flight
            flight.task.add_done_callback(lambda task, k=key, f=flight: self._flight_done(k, f))
        else:
            self.stats["coalesced"] += 1
        flight.waiters += 1
        try:
            data = await asyncio.shield(flight.task)  # يشارك نجاح/فشل الرحلة
        finally:
            flight.waiters -= 1
            if flight.waiters == 0 and not flight.task.done():
                # لا منتظِر باقٍ: لا عمل يتيم، ولا يرث طلبٌ لاحق رحلةً تُلغى.
                self._forget_flight(key, flight)
                flight.task.cancel()
        return {**data, "_cache": "coalesced"} if coalesced else data

    def _forget_flight(self, key: str, flight: _Flight) -> None:
        if self._inflight.get(key) is flight:
            del self._inflight[key]

    def _flight_done(self, key: str, flight: _Flight) -> None:
        """تنظيف الرحلة عند حسمها بأيّ نتيجة (نجاح/فشل/إلغاء)."""
        self._forget_flight(key, flight)
        if not flight.task.cancelled():
            flight.task.exception()  # يُعَدّ مُستلَماً حتّى إن غادر كلّ المنتظِرين

    async def _resolve_uncached(self, key: str, payload: dict, entry: _CacheEntry | None) -> dict:
        """يحلّ نتيجة STAC عند غياب cache طازج (الأساس→احتياطي→stale→فشل). يُلَفّ بـ
        single-flight في ``search`` فيتشارك المتزامنون هذه المكالمة الواحدة."""
        # ٢. طلب بإعادة محاولة + backoff أُسّي (يحتاج httpx)
        import httpx

        # EXTRA-3: المغلَّف المخزَّن يحمل هويّة المصدر الفعليّ (أساس/احتياطي، المحاولات،
        # الاكتمال) قبل الكتابة في الـcache، فتعود الهويّة نفسها على miss/fresh/stale.
        attempts: list[dict] = []
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(f"{self.base_url}/search", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                attempts.append({"endpoint": self.base_url, "role": "primary", "ok": True})
                # نجح → خزّن في cache (Redis + ذاكرة)
                envelope = self._envelope(data, self.base_url, "primary", attempts)
                await self._cache_set(key, envelope)
                return {**envelope, "_cache": "miss"}
            except Exception as e:  # noqa: BLE001 — نلتقط لإعادة المحاولة
                last_err = e
                attempts.append({"endpoint": self.base_url, "role": "primary", "ok": False})
                if attempt < self.max_retries - 1:
                    self.stats["retries"] += 1
                    # backoff أُسّي: 1s, 2s, 4s ... (مع سقف)
                    await asyncio.sleep(min(2**attempt, 8))
                    logger.warning("STAC محاولة %d فشلت: %s", attempt + 1, e)

        # ٣. الأساس فشل — جرّب المصادر الاحتياطيّة بالترتيب (PC ثمّ غيره).
        # نفس بنية STAC، فنفس payload يعمل. تخزين النتيجة في cache المشترك.
        for fb_url in self.fallback_urls:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(f"{fb_url}/search", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                attempts.append({"endpoint": fb_url, "role": "fallback", "ok": True})
                self.stats["fallback_served"] += 1
                envelope = self._envelope(data, fb_url, "fallback", attempts)
                await self._cache_set(key, envelope)
                logger.warning("STAC الأساس فشل — قُدّم من احتياطي: %s", fb_url)
                return {**envelope, "_cache": "miss"}
            except Exception as e:  # noqa: BLE001 — هذا الاحتياطي فشل، جرّب التالي
                attempts.append({"endpoint": fb_url, "role": "fallback", "ok": False})
                logger.warning("احتياطي فشل (%s): %s", fb_url, e)

        # ٤. الكلّ فشل — قدّم cache منتهياً إن وُجد (stale-if-error)
        if entry is not None:
            self.stats["stale_served"] += 1
            logger.warning("STAC فشل — أقدّم cache منتهياً (عمر %.0fث)", entry.age())
            return {
                **entry.data,
                "_cache": "stale",
                "_warning": "المصدر غير متاح — نتيجة محفوظة قد تكون قديمة",
            }

        # ٥. لا cache + فشل تامّ — أبلِغ بصدق (لا تخترع)
        self.stats["failures"] += 1
        raise RuntimeError(f"STAC غير متاح بعد {self.max_retries} محاولات ولا cache: {last_err}")

    def _envelope(self, data: dict, endpoint: str, role: str, attempts: list[dict]) -> dict:
        """يغلّف استجابة STAC بهويّة مصدرها قبل التخزين (EXTRA-3)."""
        envelope = {
            **data,
            "_source": role,
            "_provenance": {
                "role": role,
                "endpoint": endpoint,
                "primary_endpoint": self.base_url,
                "attempts": [dict(a) for a in attempts],
                "complete": _page_complete(data),
            },
        }
        if role == "fallback":
            envelope["_fallback_url"] = endpoint
            envelope["_warning"] = _FALLBACK_WARNING
        return envelope

    def health(self) -> dict:
        """صحّة المصدر للمراقبة (يُضاف لـ/metrics)."""
        total = max(self.stats["requests"], 1)
        return {
            **self.stats,
            "cache_size": len(self._cache),
            "cache_hit_rate": round(self.stats["cache_hits"] / total, 3),
            "redis_enabled": self._redis is not None,
        }

    def clear_cache(self) -> int:
        n = len(self._cache)
        self._cache.clear()
        return n
