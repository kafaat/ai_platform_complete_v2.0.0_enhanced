"""اختبارات الكشف العكسي للموقع (_reverse_geocode) — صرفة offline.

تغطّي: نقطة داخل اليمن → الدولة "اليمن" + إقليم (محافظة) غير فارغ؛ نقطة بعيدة
خارج اليمن → الدولة "غير محدّد"؛ إحداثيّات ناقصة → (None, None). لا قاعدة بيانات
ولا شبكة — الدالّة نقيّة (YEMEN_BBOX + geo_zone_locator).

تتحقّق هذه الاختبارات من **اسم المحافظة الفعلي** المُعاد (لا مجرّد "غير فارغ")،
عبر نقاط داخليّة محسوبة يدويّاً من صناديق المحافظات في api/geo_zone_locator.py،
وتؤكّد قاعدة "الصندوق الأصغر/الأدقّ يفوز عند التداخل" وحدود اليمن وشموليّة الحافّة.
"""

from api.geo_zone_locator import locate_field
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


# ─── تحقّق سلوكي: اسم المحافظة الفعلي لنقاط داخليّة معروفة ──────────
# الإحداثيّات أدناه نقاط داخل صناديق محدّدة في _GOVERNORATE_BOXES (محسوبة من
# حدود الصندوق نفسه، لا من معرفة جغرافيّة مسبقة)، والمحافظة المتوقّعة مشتقّة
# مباشرةً من تلك الحدود + قاعدة "الأصغر يفوز".


def test_locate_field_hudaydah_interior():
    """الحديدة: صندوق (13.5, 16.5, 42.5, 43.9). النقطة (14.0, 42.7) داخليّة
    وحصريّة (خط الطول 42.7 غرب صندوق تعز الذي يبدأ عند 43.0)."""
    loc = locate_field(14.0, 42.7)
    assert loc["supported"] is True
    assert loc["governorate_ar"] == "الحديدة"


def test_locate_field_aden_interior():
    """عدن: صندوق (12.7, 13.1, 44.8, 45.2). النقطة (12.85, 45.0) داخليّة
    وحصريّة (خط العرض 12.85 جنوب صندوق لحج الذي يبدأ عند 12.9)."""
    loc = locate_field(12.85, 45.0)
    assert loc["supported"] is True
    assert loc["governorate_ar"] == "عدن"


def test_locate_field_sadah_interior():
    """صعدة: صندوق (16.3, 17.5, 43.2, 44.4). النقطة (16.8, 44.0) داخليّة
    وحصريّة (شمال/شرق الصناديق المجاورة)."""
    loc = locate_field(16.8, 44.0)
    assert loc["supported"] is True
    assert loc["governorate_ar"] == "صعدة"


# ─── تحقّق سلوكي: الصندوق الأصغر/الأدقّ يفوز عند التداخل ───────────


def test_smallest_box_wins_amana_over_sanaa():
    """أمانة العاصمة (15.2-15.5, 44.1-44.3 — مساحة ~0.06) متداخلة داخل صنعاء
    (14.9-16.2, 43.7-44.7 — مساحة ~1.3). النقطة (15.35, 44.2) تقع في كليهما،
    ويجب أن تفوز أمانة العاصمة (الأصغر = الأدقّ)."""
    loc = locate_field(15.35, 44.2)
    assert loc["governorate_ar"] == "أمانة العاصمة"


def test_smallest_box_wins_marib_over_shabwa():
    """مأرب (15.0-15.9, 44.9-46.3) ضمن تداخل أطراف مع شبوة (13.8-16.2, 45.5-47.5).
    النقطة (15.05, 45.55) في كليهما، ويجب أن تفوز مأرب (الصندوق الأصغر)."""
    loc = locate_field(15.05, 45.55)
    assert loc["governorate_ar"] == "مأرب"


def test_smallest_box_wins_rima_over_hudaydah():
    """ريمة (14.4-14.9, 43.3-43.8) متداخلة مع الحديدة (13.5-16.5, 42.5-43.9).
    النقطة (14.6, 43.5) في كليهما، ويجب أن تفوز ريمة (الأصغر)."""
    loc = locate_field(14.6, 43.5)
    assert loc["governorate_ar"] == "ريمة"


# ─── تحقّق سلوكي: خارج اليمن لا يُرجِع محافظة خاطئة ───────────────


def test_outside_yemen_unsupported():
    """نقطة خارج صندوق اليمن في locate_field (lat 12-19.5, lon 42-54.5) ترجع
    supported=False بلا أيّ محافظة — لا تطابق خاطئ."""
    loc = locate_field(48.85, 2.35)
    assert loc["supported"] is False
    assert "governorate_ar" not in loc
    assert "خارج حدود اليمن" in loc["message_ar"]


def test_inside_yemen_but_no_box_default_string():
    """داخل حدود اليمن لكن خارج كلّ الصناديق المعرّفة (12.2, 43.0) → النظام
    يبقى مدعوماً لكن يُرجِع نصّ المحافظة الافتراضي 'غير محدّدة بدقّة' لا اسماً خاطئاً."""
    loc = locate_field(12.2, 43.0)
    assert loc["supported"] is True
    assert loc["governorate_ar"] == "غير محدّدة بدقّة"


def test_reverse_geocode_default_string_maps_to_none_region():
    """الغلاف _reverse_geocode يحوّل نصّ 'غير محدّدة بدقّة' إلى region=None
    (يبقى البلد 'اليمن' لأنّ النقطة داخل YEMEN_BBOX الأوسع)."""
    country, region = _reverse_geocode(12.2, 43.0)
    assert country == "اليمن"
    assert region is None


# ─── تحقّق سلوكي: شموليّة حافّة الصندوق ───────────────────────────


def test_box_boundary_is_inclusive():
    """_point_in_box شامل للحافّة (<=). الحافّة (14.0, 42.5) على lon_min للحديدة
    تطابق الحديدة بالضبط، بينما (14.0, 42.499) خارجها مباشرةً تقع خارج الصناديق."""
    on_edge = locate_field(14.0, 42.5)
    assert on_edge["governorate_ar"] == "الحديدة"
    just_outside = locate_field(14.0, 42.499)
    assert just_outside["supported"] is True
    assert just_outside["governorate_ar"] == "غير محدّدة بدقّة"
