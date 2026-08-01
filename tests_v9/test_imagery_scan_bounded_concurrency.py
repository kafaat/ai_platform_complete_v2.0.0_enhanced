"""IMAGERY-SCAN-SERIAL-WAIT-01 — الكنسة تفحص الحقول بتزامن محدود لا بالتتابع.

كان ``scan_all`` يمرّ على الحقول تسلسليّاً، وهو مقبول حين كان العمل لكلّ حقل نداءً أو
نداءين. بعد SPECTRAL-COLLECTOR-ASYNC-RACE-01 صار كلّ حقل بصورة جديدة **ينتظر اكتمال
دفعته** حتّى ``IMAGERY_BATCH_WAIT_BUDGET_S`` (افتراض ١٢٠ث)، و``load_from_db`` يجلب حقول
كلّ المستأجرين بلا ``LIMIT`` ⇒ أسوأ حالة للدورة = عدد الحقول × الميزانيّة.

الجدولة لا تضع مهلة على المهمّة (``scheduler.py:122`` ينتظر انتهاءها ثمّ ينام)، فالأثر
**انزياح دورة** لا تداخل ولا تعليق — لكنّه انزياح ينمو خطّيّاً بعدد الحقول. العلاج هو
نفسه المُطبَّق في ``GAP-B1-ALLFIELDS-SEQ``: ``gather`` بتزامن محدود بـ``Semaphore``.

التكذيب هنا **سلوكيّ لا شكليّ**: لا يُفتَّش عن ``gather`` في المصدر (فحصٌ كهذا يمرّ على
كود يستدعيها ولا يتزامن). بل تُمسَك ذروة التوازي المُقاسة أثناء تنفيذ حقيقيّ — إعادة
الحلقة تسلسليّةً تجعل الذروة ١ فتسقط الاختبارات.

ويُفحَص ما كان يمكن أن يكسره التزامن: عزل فشل الحقل · حتميّة ترتيب ``errors`` (``gather``
يُرجِع بترتيب الدخل لا الإتمام) · صدق العدّادات · واحترام السقف نفسه.
"""

from __future__ import annotations

import asyncio
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


class _ConcurrencyProbe:
    """يقيس ذروة التوازي الفعليّة أثناء البحث عن المشاهد.

    ``search_imagery_scenes`` هي أوّل نداء شبكيّ لكلّ حقل، فذروة المتزامنين فيها هي
    ذروة الكنسة. ``asyncio.sleep(0)`` يُسلّم الحلقة فيُتاح للأقران الدخول — بدونه قد
    تُنهي المهمّة عملها قبل أن تبدأ التالية فتبدو ذروةٌ ١ ولو كان التزامن سليماً.
    """

    def __init__(self, *, failing: set[str] | None = None):
        self.active = 0
        self.peak = 0
        self.seen: list[str] = []
        self._failing = failing or set()

    async def search(self, *, bbox, datetime_start, datetime_end, limit=5):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            for _ in range(4):
                await asyncio.sleep(0)
            scene = f"S2_{bbox[0]}"
            self.seen.append(scene)
            if scene in self._failing:
                raise RuntimeError("مزوّد غير متاح")
            return {
                "items": [
                    {
                        "id": scene,
                        "datetime": "2026-06-10T08:00:00Z",
                        "raster_url": "https://example.invalid/s.tif",
                    }
                ]
            }
        finally:
            self.active -= 1


def _wire(monkeypatch, probe, *, concurrency="8"):
    """يعزل الكنسة عن كلّ ما هو خارجها: البحث مُقاس، والمؤشّرات/الإدامة معطَّلة."""
    from api import imagery_automation as ia

    # مُرقَّعتان على الصنف ⇒ تستقبلان ``self`` أيضاً.
    async def _noop_indicators(self, tf, image):
        return None

    async def _noop_persist(self, tf):
        return None

    monkeypatch.setattr(ia, "search_imagery_scenes", probe.search)
    monkeypatch.setattr(ia.ImageryAutomation, "_trigger_indicators", _noop_indicators)
    monkeypatch.setattr(ia.ImageryAutomation, "_persist_field", _noop_persist)
    monkeypatch.setenv("IMAGERY_SCAN_CONCURRENCY", concurrency)


def _automation(n_fields: int):
    from api.imagery_automation import ImageryAutomation, TrackedField

    ia = ImageryAutomation()
    for i in range(n_fields):
        ia._fields[f"fld_{i}"] = TrackedField(
            field_id=f"fld_{i}",
            bbox=[float(i), 15.0, float(i) + 0.1, 15.1],
            tenant_id="t1",
        )
    return ia


@pytest.mark.asyncio
async def test_fields_are_scanned_concurrently_not_one_after_another(core_on_path, monkeypatch):
    """التكذيب الأساسيّ: إعادة الحلقة تسلسليّةً تجعل الذروة ١ فيسقط هذا الاختبار."""
    probe = _ConcurrencyProbe()
    _wire(monkeypatch, probe, concurrency="8")
    ia = _automation(8)

    result = await ia.scan_all()

    assert probe.peak > 1, "الحقول ما تزال تُفحَص بالتتابع — زمن الجدار = مجموع الحقول"
    assert result["scanned"] == 8
    assert result["new_images"] == 8
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_concurrency_never_exceeds_the_configured_ceiling(core_on_path, monkeypatch):
    """السقف حدٌّ فعليّ لا نيّة: ٢٠ حقلاً بسقف ٣ لا يتجاوز ٣ متزامنين قطّ.

    بلا سقف يتحوّل الإصلاح إلى عطل آخر: ٢٠ ألف حقل تعني ٢٠ ألف نداء متزامن على
    raster-service.
    """
    probe = _ConcurrencyProbe()
    _wire(monkeypatch, probe, concurrency="3")
    ia = _automation(20)

    await ia.scan_all()

    assert probe.peak <= 3
    assert probe.peak > 1


@pytest.mark.asyncio
async def test_one_failing_field_does_not_sink_the_others(core_on_path, monkeypatch):
    """العزل الذي كانت الحلقة التسلسليّة تضمنه بـtry/except يبقى مضموناً تحت gather."""
    probe = _ConcurrencyProbe(failing={"S2_2.0", "S2_5.0"})
    _wire(monkeypatch, probe)
    ia = _automation(8)

    result = await ia.scan_all()

    assert result["scanned"] == 8
    assert result["failed"] == 2
    assert result["new_images"] == 6
    assert ia._fields["fld_2"].check_errors == 1
    assert ia._fields["fld_7"].check_errors == 0


@pytest.mark.asyncio
async def test_error_list_follows_field_order_not_completion_order(core_on_path, monkeypatch):
    """حتميّة: ``gather`` يُرجِع بترتيب الدخل، فتبقى ``errors`` مستقرّة بين التشغيلات.

    لولا ذلك لصار ``errors[:10]`` عيّنةً عشوائيّة من الفشل — تقريراً يتغيّر بلا تغيّر
    في النظام.
    """
    probe = _ConcurrencyProbe(failing={"S2_1.0", "S2_4.0", "S2_6.0"})
    _wire(monkeypatch, probe)
    ia = _automation(8)

    result = await ia.scan_all()

    assert [e.split(":")[0] for e in result["errors"]] == ["fld_1", "fld_4", "fld_6"]


@pytest.mark.asyncio
async def test_skipped_fields_are_not_scanned_and_never_reach_the_network(
    core_on_path, monkeypatch
):
    """حارس الكادينس يسبق التزامن: الحقل غير المستحقّ لا يُفتَح له مسار أصلاً."""
    from datetime import UTC, datetime

    probe = _ConcurrencyProbe()
    _wire(monkeypatch, probe)
    ia = _automation(4)
    ia._fields["fld_0"].last_image_date = datetime.now(UTC).isoformat()
    ia._fields["fld_1"].last_image_date = datetime.now(UTC).isoformat()

    result = await ia.scan_all()

    assert result["skipped"] == 2
    assert result["scanned"] == 2
    assert len(probe.seen) == 2


@pytest.mark.asyncio
async def test_no_tracked_fields_still_touches_nothing(core_on_path, monkeypatch):
    """الصدق القائم محفوظ: لا حقول ⇒ لا ضرب لـraster-service."""
    probe = _ConcurrencyProbe()
    _wire(monkeypatch, probe)
    ia = _automation(0)

    result = await ia.scan_all()

    assert result["scanned"] == 0
    assert probe.seen == []


@pytest.mark.asyncio
async def test_cancellation_propagates_and_is_not_recorded_as_a_field_failure(
    core_on_path, monkeypatch
):
    """الإلغاء إشارة تحكّم لا عطل — و``return_exceptions=True`` يلتقط ``BaseException``.

    بلا إعادة الرمي كان إيقاف الخدمة يُسجَّل «فشل فحص N حقلاً» وتمضي الكنسة إلى نهايتها
    بدل أن تنتهي: ابتلاعُ إشارة وإعادة تسميتها عطلاً — وهو النمط الذي تُصفّيه
    SILENT-EXCEPTION-HANDLERS-11-01 نفسها.
    """
    from api import imagery_automation as ia_mod

    probe = _ConcurrencyProbe()
    _wire(monkeypatch, probe)

    async def _cancelled(self, field_id, tf, start, end, semaphore):
        raise asyncio.CancelledError

    monkeypatch.setattr(ia_mod.ImageryAutomation, "_scan_one", _cancelled)
    ia = _automation(3)

    with pytest.raises(asyncio.CancelledError):
        await ia.scan_all()


@pytest.mark.asyncio
async def test_concurrency_floor_is_one_never_zero(core_on_path, monkeypatch):
    """صفر يعني ``Semaphore`` لا يُفتَح أبداً — تعليقاً تامّاً، لا «بلا حدّ»."""
    from api import imagery_automation as ia_mod

    monkeypatch.setenv("IMAGERY_SCAN_CONCURRENCY", "0")
    assert ia_mod._scan_concurrency() == 1
    monkeypatch.setenv("IMAGERY_SCAN_CONCURRENCY", "-5")
    assert ia_mod._scan_concurrency() == 1
    monkeypatch.setenv("IMAGERY_SCAN_CONCURRENCY", "ليس رقماً")
    assert ia_mod._scan_concurrency() == 8


@pytest.mark.asyncio
async def test_disabled_wait_is_counted_in_its_own_bucket(core_on_path, monkeypatch):
    """ميزانيّة صفر تُعَدّ ``disabled`` لا ``terminal``: لم يُتحقَّق من شيء.

    وبلا عدّاد أصلاً كان مجموع ``batch_waits`` أقلّ من عدد الدفعات بلا تفسير — ثقب في
    عدّادات حجّتها الأولى أنّ ما لا يُقاس يعود صمتاً بشكل آخر.
    """
    from api.imagery_automation import ImageryAutomation, TrackedField

    monkeypatch.setenv("IMAGERY_BATCH_WAIT_BUDGET_S", "0")
    ia = ImageryAutomation()
    tf = TrackedField(field_id="fld_1", bbox=[44.0, 15.0, 44.1, 15.1], tenant_id="t1")

    assert await ia._await_batch_terminal(tf, {"job_id": "jb1", "status": "pending"}) is True

    waits = ia.status()["batch_waits"]
    assert waits["disabled"] == 1
    assert waits["terminal"] == 0
    assert waits["timed_out"] == 0
    assert waits["unknown"] == 0
