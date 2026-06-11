"""اختبارات الكشف العكسي للموقع (_reverse_geocode) — صرفة offline.

تغطّي: نقطة داخل اليمن → الدولة "اليمن" + إقليم (محافظة) غير فارغ؛ نقطة بعيدة
خارج اليمن → الدولة "غير محدّد"؛ إحداثيّات ناقصة → (None, None). لا قاعدة بيانات
ولا شبكة — الدالّة نقيّة (YEMEN_BBOX + geo_zone_locator).
"""

from api.main import _reverse_geocode


def test_reverse_geocode_inside_yemen():
    # وادي سبأ (مأرب/البيضاء) — داخل اليمن
    country, region = _reverse_geocode(15.05, 45.55)
    assert country == "اليمن"
    assert region  # محافظة غير فارغة
    assert isinstance(region, str)


def test_reverse_geocode_far_outside():
    # نقطة بعيدة (وسط أوروبا) — خارج اليمن تماماً
    country, region = _reverse_geocode(48.85, 2.35)
    assert country == "غير محدّد"
    assert region is None


def test_reverse_geocode_handles_none():
    assert _reverse_geocode(None, None) == (None, None)
    assert _reverse_geocode(15.0, None) == (None, None)


def test_reverse_geocode_known_governorate():
    # صنعاء (~15.35, 44.2) — يجب أن يطابق محافظة معروفة
    country, region = _reverse_geocode(15.35, 44.2)
    assert country == "اليمن"
    assert region is not None
