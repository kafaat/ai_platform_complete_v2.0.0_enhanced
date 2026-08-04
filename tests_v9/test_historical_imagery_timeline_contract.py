from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
MAPHUB = (ROOT / "frontend/src/sections/MapHub.tsx").read_text(encoding="utf-8")
THUMB = (ROOT / "frontend/src/components/maphub/ImageryTimelineThumb.tsx").read_text(
    encoding="utf-8"
)
API = (ROOT / "frontend/src/services/api.ts").read_text(encoding="utf-8")
FACADE = (ROOT / "services/sahool-platform/api/routers/field_workspace_imagery.py").read_text(
    encoding="utf-8"
)


def test_timeline_uses_persisted_thumbnail_and_real_capture_timestamp():
    # الشاشة تستهلك `available-dates` مباشرةً وتبني رابط المصغّرة عميلاً عبر
    # `fieldCdseThumbnailUrl(... source=persisted)`. تحويلها إلى واجهة
    # `/imagery/timeline` إعادةُ توصيلٍ لها اختباراتها الساكنة القائمة
    # (MapHubHistoricalTimeline.static.test.ts)، ولا يلزم لأيّ من إصلاحَي هذه
    # الشريحة. التأكيد يقيس **السياسة** لا نقطة النهاية: المصغّرة من الأصل
    # المُدَام حصراً، فلا اكتشاف حيّ يُظهر مشهد تاريخ آخر.
    assert "source=persisted" in MAPHUB or "'source', 'persisted'" in API
    # الشاشة تستهلك `available-dates` التي لا تُرجِع `thumbnail_url`؛ تفضيلُ حقلٍ
    # لا يصل أبداً شيفرةٌ ميتة تبدو احتياطاً. الرابط يُبنى عميلاً بالسياسة نفسها
    # (`source=persisted`)، والحقل يبقى مُصرَّحاً في النوع لمستهلكي الواجهة.
    assert "fieldCdseThumbnailUrl(" in MAPHUB
    # المُنسِّق المُنزَل `captureTime`: يقرأ الطابع نصّاً (لا `new Date`)، ويسم
    # الساعة UTC صراحةً كي لا تتناقض مع التاريخ المشتقّ خادميّاً بـUTC، ويُعلن
    # تناقض الطابع مع تاريخ البطاقة بدل ابتلاعه.
    assert "captureTime(d.acquisition_datetime, d.date)" in MAPHUB
    assert "acquisition_datetime" in MAPHUB
    assert "thumbnail_url?: string | null" in API
    assert '"acquisition_datetime": row.get("acquisition_datetime")' in FACADE
    assert "source=persisted" in FACADE


def test_timeline_is_horizontal_accessible_and_keeps_pending_dates_visible():
    assert "overflow-x-auto" in MAPHUB
    assert "snap-x snap-mandatory" in MAPHUB
    # لا `dir="ltr"`: الواجهة عربيّة والمشاهد مرتّبة من الأحدث، ففرض LTR يضع
    # الأحدث يساراً عكس ترتيب القراءة. المشكلة الحقيقيّة في RTL ليست الاتّجاه بل
    # اصطلاح أصل التمرير (`scrollLeft` من سالب إلى صفر)، وقد عولجت بحساب فرق
    # المستطيلين + `scrollBy` — محايد الاتّجاه ويعمل تحت RTL وLTR معاً.
    assert "getBoundingClientRect()" in MAPHUB
    assert "container.scrollBy(" in MAPHUB
    assert "aria-current={active" in MAPHUB
    assert "scrollImageryTimeline" in MAPHUB
    # الاتّجاه منطقيّ لا فيزيائيّ، و`scrollBy` نسبيّ ⇒ يعمل تحت RTL وLTR.
    assert "'newer'" in MAPHUB and "'older'" in MAPHUB
    assert "aria-current={active" in MAPHUB
    assert "has_cog" in MAPHUB
    assert "قيد المعالجة" in THUMB


def test_thumbnail_loading_and_failures_are_explicit():
    assert 'loading="lazy"' in THUMB
    assert 'decoding="async"' in THUMB
    assert "جارٍ تحميل المعاينة" in THUMB
    assert "تعذّر العرض" in THUMB
    assert "style={{ display:" not in THUMB
    assert ".style.display" not in THUMB


def test_timeline_window_uses_utc_calendar_months_not_31_day_approximation():
    assert "_subtract_calendar_months" in FACADE
    assert "datetime.now(UTC).date()" in FACADE
    assert "months * 31" not in FACADE
