"""job_store.py — تخزين نتائج مهامّ المعالجة (Redis مشترك + ارتداد للذاكرة).

الفجوة: كانت نتائج المهامّ تُحفظ في dict في الذاكرة (`_jobs`) داخل main.py.
أثره: تُفقد عند إعادة التشغيل، ولا تُشارَك عبر العمّال/العمليّات — فيفشل
`GET /jobs/{id}/result` على عامل آخر أو بعد إعادة التشغيل.

الحلّ: مخزن مهامّ بطبقتين كنمط بقيّة الخدمة (مثل STAC cache وdb_persist):
  ١) Redis (مشترك عبر النسخ + يبقى بعد إعادة التشغيل) إن توفّر REDIS_URL وكان
     قابلاً للوصول — مفاتيح `sahool:raster:job:{id}` بقيمة JSON وبـTTL (24h).
  ٢) dict في الذاكرة (fallback) إن غاب Redis أو تعذّر — فتعمل الخدمة في
     التطوير/CI بلا Redis (نفس نمط التدهور اللطيف والصدق في الكود).

⚠ سلامة حلقة الحدث (event-loop): كتابات المهامّ تجري في **خيط خلفيّ** عبر
BackgroundTasks (دالّة متزامنة ⇒ يشغّلها FastAPI في threadpool بلا حلقة حدث)،
بينما القراءات تجري في حلقة الخادم. مشاركة عميل redis async (pool) عبر حلقتين
تكسر بـ'another operation is in progress' — نفس درس db_persist.py. لذا نستخدم
عميل **redis المتزامن** (sync) هنا: عمليّات المهمّة نادرة وقصيرة، والعميل
المتزامن آمن للاستدعاء من حلقة الخادم (نداء حاجب وجيز) ومن خيط الخلفيّة على
حدّ سواء، فيتجنّب مشكلة عبور الحلقات تماماً.

التسلسل: JSON. القيم enum (مثل JobStatus) تُسلسَل لقيمتها النصّيّة عبر default.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("raster-service.jobs")

JOB_KEY_PREFIX = "sahool:raster:job:"
# TTL افتراضيّ: 24 ساعة (نتيجة المهمّة تبقى يوماً ثمّ تُنظَّف تلقائيّاً في Redis).
JOB_TTL_SECONDS = int(os.getenv("RASTER_JOB_TTL_SECONDS", str(24 * 60 * 60)))


def _json_default(o):
    """يسلسِل القيم غير القابلة للـJSON افتراضيّاً (enum → قيمته النصّيّة)."""
    val = getattr(o, "value", None)
    if val is not None:
        return val
    return str(o)


class JobStore:
    """مخزن مهامّ بطبقتين: Redis (مشترك) إن توفّر، وإلّا الذاكرة (fallback).

    الواجهة تُحاكي نمط الـdict القديم لكن بعمليّات صريحة كي تَنفُذ التغييرات إلى
    Redis (لا تكفي مطفرة dict في الذاكرة إذا أردنا المشاركة عبر العمليّات):
      - create(job_id, data) / set(job_id, data) — كتابة كاملة (تجدّد TTL).
      - update(job_id, **fields) — قراءة-تعديل-كتابة (للمطفرات المكانيّة سابقاً).
      - get(job_id) — يُرجِع dict أو None (مفقود/منتهٍ ⇒ None، نفس سلوك .get()).
      - values() — كلّ المهامّ (للمقاييس).
    """

    def __init__(self, redis_url: str | None = None):
        self._mem: dict[str, dict] = {}
        self._redis = None
        self._redis_url = redis_url
        if redis_url:
            try:
                import redis as _redis

                # عميل متزامن قصير العمليّات؛ decode_responses ليُرجِع str لا bytes.
                client = _redis.Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
                client.ping()
                self._redis = client
                logger.info("job store: Redis متّصل (مشترك + يبقى بعد إعادة التشغيل)")
            except Exception as e:  # noqa: BLE001 — Redis غير متاح ⇒ ذاكرة
                logger.warning("job store: Redis غير متاح (%s) — ذاكرة فقط (fallback)", e)
                self._redis = None
        else:
            logger.info("job store: REDIS_URL غير مضبوط — ذاكرة فقط (تطوير/CI)")

    # ─── أدوات داخليّة ───────────────────────────────────────────────
    def _key(self, job_id: str) -> str:
        return f"{JOB_KEY_PREFIX}{job_id}"

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    # ─── الكتابة ─────────────────────────────────────────────────────
    def set(self, job_id: str, data: dict) -> None:
        """يكتب حالة المهمّة كاملةً (يجدّد TTL في Redis). يرتدّ للذاكرة عند الفشل."""
        if self._redis is not None:
            try:
                self._redis.set(
                    self._key(job_id),
                    json.dumps(data, default=_json_default),
                    ex=JOB_TTL_SECONDS,
                )
                return
            except Exception as e:  # noqa: BLE001 — فشل Redis ⇒ ارتداد للذاكرة
                logger.warning("job store: كتابة Redis فشلت (%s) — ارتداد للذاكرة", e)
        self._mem[job_id] = data

    # create مرادف صريح لـset (إنشاء مهمّة جديدة) — لوضوح مواقع الاستدعاء.
    create = set

    def update(self, job_id: str, **fields) -> dict | None:
        """قراءة-تعديل-كتابة: يحدّث حقولاً على مهمّة قائمة ويعيد كتابتها.

        يحلّ محلّ مطفرة dict المكانيّة القديمة (`job["x"] = y`) بحيث تَنفُذ
        التغييرات إلى Redis. يُرجِع dict المُحدَّث أو None إن غابت المهمّة.
        """
        cur = self.get(job_id)
        if cur is None:
            return None
        cur.update(fields)
        self.set(job_id, cur)
        return cur

    # ─── القراءة ─────────────────────────────────────────────────────
    def get(self, job_id: str) -> dict | None:
        """يُرجِع نسخة من حالة المهمّة، أو None إن غابت/انتهت صلاحيّتها."""
        if self._redis is not None:
            try:
                raw = self._redis.get(self._key(job_id))
                if raw is None:
                    return None
                return json.loads(raw)
            except Exception as e:  # noqa: BLE001 — فشل Redis ⇒ ارتداد للذاكرة
                logger.warning("job store: قراءة Redis فشلت (%s) — ارتداد للذاكرة", e)
        v = self._mem.get(job_id)
        # نُرجِع نسخة كي لا تُطفَّر الحالة المُخزَّنة مكانيّاً دون set صريح.
        return dict(v) if v is not None else None

    def values(self) -> list[dict]:
        """كلّ المهامّ (للمقاييس). على Redis يمسح المفاتيح بالبادئة (scan)."""
        if self._redis is not None:
            try:
                out: list[dict] = []
                for k in self._redis.scan_iter(match=f"{JOB_KEY_PREFIX}*"):
                    raw = self._redis.get(k)
                    if raw is not None:
                        out.append(json.loads(raw))
                return out
            except Exception as e:  # noqa: BLE001 — فشل Redis ⇒ ارتداد للذاكرة
                logger.warning("job store: مسح Redis فشل (%s) — ارتداد للذاكرة", e)
        return [dict(v) for v in self._mem.values()]

    def clear(self) -> None:
        """ينظّف الحالة (للاختبارات/الذاكرة فقط — لا يلمس Redis)."""
        self._mem.clear()
