"""soilgrids_cache.py — جلبُ SoilGrids خلفيّاً بتخزينٍ مؤقّت، كي لا ينتظر المستدعي المزوّد.

**العطلُ الذي وُجِد هذا لأجله** (قياس Railway staging، 2026-09-29):

- ISRIC أجاب نقطةً زراعيّةً (وادي زبيد) في **أكثرَ من 90 ثانية**، والخدمةُ أعادت 503
  عند مهلتها (60.6ث). وأجاب نقطةً مُقنَّعةً في 5ث مرّةً و32ث مرّةً أخرى.
- والمستهلكُ الفعليّ (بطاقة ذكاء الحقل في المنصّة) ينتظر **20 ثانية** فقط
  (``ADAPTER_TIMEOUT``). فرفعُ مهلة الخدمة لا يصل إليه أصلاً: كلُّ نقطةٍ حقيقيّةٍ تصل
  إلى البطاقة «مفقودة» مهما كانت مهلةُ الخدمة.

والعلاج: الجلبُ يجري في **مهمّةٍ خلفيّة** تملأ ذاكرةً مؤقّتة، والمستدعي ينتظر حدّاً
قصيراً (``wait_s``). إن جاء الجوابُ ضمنه عاد به؛ وإلّا عاد «قيد الجلب» والمهمّةُ
مستمرّة، فالنداءُ التالي لنفس النقطة يُجاب من الذاكرة فوراً.

- **مهمّةٌ واحدةٌ لكلّ نقطة** (single-flight): نداءان متزامنان لا يُطلِقان جلبَين —
  يحمي حدَّ الاستخدام العادل لـISRIC أيضاً.
- **ما يُخزَّن:** ``ok`` و``no_coverage`` فقط. خصائصُ SoilGrids نموذجٌ ثابتٌ لا يتغيّر
  بين ساعةٍ وأخرى، و«لا تغطية» دائمة. أمّا ``unavailable`` فعابرٌ ولا يُخزَّن، وإلّا
  صار عطلُ دقيقةٍ غياباً لأسبوع.

**حدودُ صدقٍ مُعلَنة:**

- الذاكرةُ **داخل العمليّة**. بعاملَي Uvicorn قد يصل النداءُ الثاني إلى العامل الآخر
  فيجد ذاكرةً فارغةً ويُطلِق جلبَه هو. لا ذاكرةَ مشتركة هنا.
- «قيد الجلب» لا يعني أنّ الجلبَ سينجح. إن فشل لا يُخزَّن، والنداءُ التالي يُعيد.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable

# نفسُ قِيَم ``soilgrids_client`` — مكرَّرةٌ عمداً كي تبقى الوحدةُ بلا استيرادٍ داخليّ
# فتُحمَّل معزولةً في الاختبار. تطابقُها مُثبَّتٌ باختبار.
OK = "ok"
NO_COVERAGE = "no_coverage"
UNAVAILABLE = "unavailable"
PENDING = "pending"

#: ما يُخزَّن. ``unavailable`` عابرٌ فلا يُخزَّن (انظر أعلاه).
_CACHEABLE = frozenset({OK, NO_COVERAGE})


def env_seconds(raw: str | None, default: float) -> float:
    """ثوانٍ من البيئة: منتهيةٌ غيرُ سالبة وإلّا الافتراض — كي لا يصير ``inf`` انتظاراً أبديّاً."""
    try:
        value = float((raw or "").strip())
    except ValueError:
        return default
    return value if math.isfinite(value) and value >= 0 else default


def point_key(lon: float, lat: float) -> tuple[float, float]:
    """الإحداثيّةُ **كما طُلِبت** — بلا تقريب.

    كان التقريبُ إلى ثلاث خانات يدمج نقطتين قد تقعان على جانبَي حدّ خليّة SoilGrids،
    فتُجاب الثانيةُ ببيانات الأولى **وبإحداثيّتها** أسبوعاً (رصده مراجعُ #1094). الدقّةُ
    العشريّة لا تُثبِت هويّةَ الخليّة، ولا معرّفَ خليّةٍ من المزوّد. والمستدعي الفعليّ
    (بطاقة الحقل) يطلب النقطةَ نفسَها للحقل نفسِه، فالمطابقةُ التامّة تكفيه.
    """
    return (float(lon), float(lat))


class SoilGridsCache:
    """ذاكرةٌ مؤقّتةٌ بجلبٍ خلفيّ. ``fetch(lon, lat) -> dict`` متزامنٌ ويُشغَّل في خيط."""

    def __init__(
        self,
        fetch: Callable[[float, float], dict],
        *,
        ttl_s: float,
        max_entries: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._ttl_s = ttl_s
        self._max = max(1, int(max_entries))
        self._clock = clock
        self._entries: dict[tuple[float, float], tuple[float, dict]] = {}
        self._inflight: dict[tuple[float, float], asyncio.Task] = {}

    def cached(self, lon: float, lat: float) -> dict | None:
        key = point_key(lon, lat)
        hit = self._entries.get(key)
        if hit is None:
            return None
        stored_at, result = hit
        if self._clock() - stored_at > self._ttl_s:
            del self._entries[key]
            return None
        return result

    def _store(self, key: tuple[float, float], result: dict) -> None:
        if result.get("outcome") not in _CACHEABLE:
            return
        self._entries.pop(key, None)
        self._entries[key] = (self._clock(), result)
        while len(self._entries) > self._max:
            del self._entries[next(iter(self._entries))]

    async def _run(self, key: tuple[float, float], lon: float, lat: float) -> dict:
        try:
            result = await asyncio.to_thread(self._fetch, lon, lat)
        except Exception:  # noqa: BLE001 — المُجلِب لا يرمي عادةً؛ وإن رمى فهو تعذّر
            result = {"outcome": UNAVAILABLE, "reason": "unreachable"}
        finally:
            self._inflight.pop(key, None)
        self._store(key, result)
        return result

    async def lookup(self, lon: float, lat: float, *, wait_s: float) -> dict:
        """من الذاكرة، أو ينتظر الجلبَ الجاري حتّى ``wait_s`` ثمّ يعود ``pending``."""
        hit = self.cached(lon, lat)
        if hit is not None:
            return hit
        key = point_key(lon, lat)
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._run(key, lon, lat))
            self._inflight[key] = task
        try:
            # shield: انقضاءُ انتظار المستدعي لا يُلغي الجلب — هو ما سيملأ الذاكرة.
            return await asyncio.wait_for(asyncio.shield(task), timeout=wait_s)
        except TimeoutError:
            return {"outcome": PENDING}
