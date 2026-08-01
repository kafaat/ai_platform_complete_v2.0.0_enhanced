"""SPECTRAL-COLLECTOR-ASYNC-RACE-01 — لا تُقرأ نتيجة دفعة قبل بلوغها حالةً نهائيّة.

``POST /v1/process/batch`` غير متزامن: يُرجِع ``pending`` فور جدولة المهمّة الخلفيّة،
والمهامّ الفرعيّة ``{job_id}_{indicator}`` تُنشَأ **داخلها**. فالقراءة الفوريّة كانت
تصطدم بـ404 دائماً، و``last_ndvi_mean``/``last_ndmi_mean``/``last_msi_mean`` لا تُكتَب
أبداً — وللأخيرَين لا كاتب إنتاجيّ آخر.

هذه الاختبارات تُثبِّت الإصلاح **وتُكذِّب نفسها**: أوّل اختبار يُعيد سلوك ما قبل الإصلاح
(ميزانيّة صفر) ويؤكّد أنّ لا شيء يُكتَب. ولو حُذِف الانتظار من الكود لصار هذا الاختبار
هو الوصف الصحيح للسلوك كلّه — فبقيّة الاختبارات تسقط.

ولا يكفي أن ينجح المسار السعيد: انتظار ينتهي بلا نتيجة **بصمت** يُعيد إنتاج العطل نفسه
بشكل آخر، فتُفحَص هنا أيضاً قابليّة قراءة الفشل (عدّادات مفصولة لثلاث حالات).
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


class _FakeRaster:
    """يحاكي raster-service الحقيقيّ: المهامّ الفرعيّة **غير موجودة** حتّى تكتمل الدفعة.

    هذا هو جوهر العطل — لا شكل مُتخيَّل: ``/v1/jobs/{sub}/result`` يردّ 404 ما دامت
    المهمّة الفرعيّة لم تُنشَأ بعد (``routers/jobs.py:41``)، و``/v1/jobs/{id}`` يردّ
    الحالة الجارية لأنّ الدفعة سُجِّلت قبل جدولة المهمّة الخلفيّة.
    """

    def __init__(self, *, polls_until_terminal: int, terminal: str = "completed"):
        self._remaining = polls_until_terminal
        self._terminal = terminal
        self.status_polls: list[str] = []
        self.result_reads: list[str] = []
        self.sleeps: list[float] = []

    @property
    def _done(self) -> bool:
        return self._remaining <= 0

    async def get_job_status(self, job_id, *, tenant_id=None, timeout_s=10.0):
        self.status_polls.append(job_id)
        if self._remaining > 0:
            self._remaining -= 1
            return {"job_id": job_id, "status": "processing", "progress_pct": 40}
        return {"job_id": job_id, "status": self._terminal, "progress_pct": 100}

    async def get_job_result(self, job_id, *, tenant_id=None, timeout_s=10.0):
        self.result_reads.append(job_id)
        if not self._done:
            return None  # المهمّة الفرعيّة لم تُنشَأ بعد ⇒ 404 ⇒ None
        if job_id.endswith("_ndvi"):
            return {"stats": {"mean": 0.62, "valid_pixels": 1500}}
        if job_id.endswith("_ndmi"):
            return {"stats": {"mean": 0.31, "valid_pixels": 1400}}
        if job_id.endswith("_msi"):
            return {"stats": {"mean": 1.25, "valid_pixels": 1400}}
        return None

    async def sleep(self, seconds):
        self.sleeps.append(seconds)


def _wire(monkeypatch, fake, *, budget="120", interval="0.01"):
    from api import imagery_automation as ia

    async def _fake_batch(*, tenant_id, payload, timeout_s=30.0):
        return {"job_id": "jb1", "status": "pending", "deduplicated": False}

    monkeypatch.setattr(ia, "process_indicator_batch", _fake_batch)
    monkeypatch.setattr(ia, "get_job_status", fake.get_job_status)
    monkeypatch.setattr(ia, "get_job_result", fake.get_job_result)
    monkeypatch.setattr(ia.asyncio, "sleep", fake.sleep)
    monkeypatch.setenv("IMAGERY_BATCH_WAIT_BUDGET_S", budget)
    monkeypatch.setenv("IMAGERY_BATCH_POLL_INTERVAL_S", interval)


def _field():
    from api.imagery_automation import TrackedField

    return TrackedField(field_id="fld_1", bbox=[44.0, 15.0, 44.1, 15.1], tenant_id="t1")


IMAGE = {
    "raster_url": "https://example.invalid/scene.tif",
    "id": "S2_X",
    "datetime": "2026-06-10T08:00:00Z",
}


@pytest.mark.asyncio
async def test_zero_budget_reproduces_the_defect_nothing_is_written(core_on_path, monkeypatch):
    """تكذيب: بلا انتظار (ميزانيّة صفر) لا تُكتَب أيّ قيمة — وهذا هو العطل المُسجَّل.

    لو أُزيل الانتظار من الكود لصار هذا هو السلوك الوحيد، فتسقط بقيّة الاختبارات هنا.
    """
    from api.imagery_automation import ImageryAutomation

    fake = _FakeRaster(polls_until_terminal=3)
    _wire(monkeypatch, fake, budget="0")
    ia, tf = ImageryAutomation(), _field()

    await ia._trigger_indicators(tf, IMAGE)

    assert fake.status_polls == []  # لا استطلاع إطلاقاً
    assert tf.last_ndvi_mean is None
    assert tf.last_ndmi_mean is None
    assert tf.last_msi_mean is None


@pytest.mark.asyncio
async def test_values_are_written_once_the_batch_reaches_a_terminal_state(
    core_on_path, monkeypatch
):
    from api.imagery_automation import ImageryAutomation

    fake = _FakeRaster(polls_until_terminal=3)
    _wire(monkeypatch, fake)
    ia, tf = ImageryAutomation(), _field()

    await ia._trigger_indicators(tf, IMAGE)

    assert tf.last_ndvi_mean == 0.62
    assert tf.last_ndmi_mean == 0.31
    assert tf.last_msi_mean == 1.25
    assert tf.last_ndvi_date == "2026-06-10"
    assert ia._batch_waits_terminal == 1
    assert ia._batch_waits_timed_out == 0


@pytest.mark.asyncio
async def test_the_wait_happens_once_per_batch_not_once_per_indicator(core_on_path, monkeypatch):
    """الانتظار على الدفعة لا على كلّ مؤشّر — وإلّا ضُرِب الاستطلاع في عدد المؤشّرات."""
    from api.imagery_automation import ImageryAutomation

    fake = _FakeRaster(polls_until_terminal=2)
    _wire(monkeypatch, fake)
    ia, tf = ImageryAutomation(), _field()

    await ia._trigger_indicators(tf, IMAGE)

    assert fake.status_polls == ["jb1", "jb1", "jb1"]  # مرّتان جارية + واحدة نهائيّة
    # القيمة المطلوبة 0.01 تُرفَع إلى الحدّ الأدنى 0.05: ضبط شديد الصِّغَر يحوّل الاستطلاع
    # إلى حلقة مشغولة تُغرِق raster-service بدل انتظاره.
    assert fake.sleeps == [0.05, 0.05]
    assert ia._batch_waits_terminal == 1


@pytest.mark.asyncio
async def test_timeout_writes_nothing_and_is_counted_not_silent(core_on_path, monkeypatch):
    """انتظار ينفد بلا اكتمال: لا قيمة مُختلَقة، ولا صمت — عدّاد مستقلّ."""
    from api.imagery_automation import ImageryAutomation

    fake = _FakeRaster(polls_until_terminal=10_000)  # لا تكتمل أبداً
    _wire(monkeypatch, fake, budget="0.001", interval="0.05")
    ia, tf = ImageryAutomation(), _field()

    await ia._trigger_indicators(tf, IMAGE)

    assert tf.last_ndvi_mean is None
    assert tf.last_ndmi_mean is None
    assert ia._batch_waits_timed_out == 1
    assert ia._batch_waits_terminal == 0
    assert fake.result_reads == []  # لا نداء يُعرَف سلفاً أنّه سيصطدم بـ404


@pytest.mark.asyncio
async def test_unknown_job_fails_fast_and_is_counted_apart_from_timeout(core_on_path, monkeypatch):
    """مهمّة مجهولة (404) ليست «بطئاً»: لا انتظار إطلاقاً وعدّاد منفصل.

    خلطها بالمهلة كان سيُخفي عطل نشر (حالة مهامّ بالذاكرة موزَّعة على نسختين) خلف
    تفسير خاطئ تماماً.
    """
    from api.imagery_automation import ImageryAutomation

    fake = _FakeRaster(polls_until_terminal=0)

    async def _unknown(job_id, *, tenant_id=None, timeout_s=10.0):
        fake.status_polls.append(job_id)
        return None

    _wire(monkeypatch, fake)
    from api import imagery_automation as ia_mod

    monkeypatch.setattr(ia_mod, "get_job_status", _unknown)
    ia, tf = ImageryAutomation(), _field()

    await ia._trigger_indicators(tf, IMAGE)

    assert fake.status_polls == ["jb1"]  # نداء واحد ثمّ توقّف
    assert fake.sleeps == []  # لا استهلاك للميزانيّة
    assert ia._batch_waits_unknown == 1
    assert ia._batch_waits_timed_out == 0
    assert tf.last_ndvi_mean is None


@pytest.mark.asyncio
async def test_processed_unpublished_is_terminal_and_is_read(core_on_path, monkeypatch):
    """``processed_unpublished`` نهائيّة — إغفالها كان سيُنتِج مهلةً في كلّ دورة
    تعمل بوضع الإدامة «أفضل-جهد» (``raster_persistence_policy.terminal_status``)."""
    from api.imagery_automation import ImageryAutomation

    fake = _FakeRaster(polls_until_terminal=1, terminal="processed_unpublished")
    _wire(monkeypatch, fake)
    ia, tf = ImageryAutomation(), _field()

    await ia._trigger_indicators(tf, IMAGE)

    assert ia._batch_waits_terminal == 1
    assert tf.last_ndvi_mean == 0.62


@pytest.mark.asyncio
async def test_already_terminal_batch_body_skips_polling(core_on_path, monkeypatch):
    """مسار إلغاء التكرار يُرجِع الحالة النهائيّة في الجسم نفسه ⇒ لا استطلاع."""
    from api import imagery_automation as ia_mod
    from api.imagery_automation import ImageryAutomation

    fake = _FakeRaster(polls_until_terminal=0)
    _wire(monkeypatch, fake)

    async def _dedup_batch(*, tenant_id, payload, timeout_s=30.0):
        return {"job_id": "jb1", "status": "completed", "deduplicated": True}

    monkeypatch.setattr(ia_mod, "process_indicator_batch", _dedup_batch)
    ia, tf = ImageryAutomation(), _field()

    await ia._trigger_indicators(tf, IMAGE)

    assert fake.status_polls == []
    assert ia._batch_waits_terminal == 1
    assert tf.last_ndvi_mean == 0.62


@pytest.mark.asyncio
async def test_one_incomplete_subjob_does_not_lose_the_others(core_on_path, monkeypatch):
    """مؤشّر فاشل يردّ 409؛ الباقي يُكتَب. القراءة متتابعة، فاستثناء منتشر كان يُسقِط ما بعده."""
    from api import imagery_automation as ia_mod
    from api.imagery_automation import ImageryAutomation
    from fastapi import HTTPException

    fake = _FakeRaster(polls_until_terminal=1)
    _wire(monkeypatch, fake)

    async def _result_with_one_409(job_id, *, tenant_id=None, timeout_s=10.0):
        if job_id.endswith("_ndmi"):
            raise HTTPException(409, "المهمّة غير مكتملة (الحالة: failed)")
        return await fake.get_job_result(job_id, tenant_id=tenant_id, timeout_s=timeout_s)

    monkeypatch.setattr(ia_mod, "get_job_result", _result_with_one_409)
    ia, tf = ImageryAutomation(), _field()

    await ia._trigger_indicators(tf, IMAGE)

    assert tf.last_ndmi_mean is None  # لا قيمة مُختلَقة للفاشل
    assert tf.last_msi_mean == 1.25  # ولم يضع الناجح بعده
    assert tf.last_ndvi_mean == 0.62


@pytest.mark.asyncio
async def test_counters_are_readable_from_status(core_on_path, monkeypatch):
    """العدّادات مقروءة من ``status()`` — وهي السطح المنشور عبر
    ``routers/automation.py`` — وإلّا صار الانتظار الفاشل غير مرئيّ من الخارج."""
    from api.imagery_automation import ImageryAutomation

    fake = _FakeRaster(polls_until_terminal=10_000)
    _wire(monkeypatch, fake, budget="0.001", interval="0.05")
    ia, tf = ImageryAutomation(), _field()

    await ia._trigger_indicators(tf, IMAGE)
    waits = ia.status()["batch_waits"]

    assert waits["timed_out"] == 1
    assert waits["terminal"] == 0
    assert waits["unknown"] == 0
    assert waits["budget_s"] == 0.001
