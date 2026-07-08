"""api/season_integrity.py — تقوية سلامة الموسم (Season Integrity) — منطق صرف.

مساعدات نقيّة (بلا I/O، بلا تبعيّة على main/db) لحراسة سلامة بيانات الموسم قبل الكتابة:

  • ``resolve_and_check_date_order`` — يدمج تعديلاً جزئيّاً مع القيم المخزّنة ويؤكّد أنّ
    الترتيب النهائيّ (بذار ≤ نهاية) سليم. يعالج الحالة التي يُرسَل فيها ``season_end`` وحده
    فيقع قبل ``sowing_date`` المخزّن (لا يُفحَص إلّا عند إرسال الاثنين معاً في المسار القديم).

  • ``validate_custom_stages`` — يتحقّق من مراحل الموسم المخصّصة: صيغة التاريخ (YYYY-MM-DD)،
    الترتيب الزمنيّ غير المتراجع، وقوعها داخل نافذة الموسم [بذار، نهاية]، وعدم تكرار الأسماء؛
    ويُعيد المراحل المُنظَّفة (بلا الفارغة) + قائمة أخطاء عربيّة. لا يُغيّر السلوك القديم
    (تصفية الفارغة) بل يضيف تحقّقاً فوقه.

كلاهما منطق حتميّ قابل للاختبار بلا خدمات — يُستدعى من routers/fields (CRUD المواسم).
"""

from __future__ import annotations

from datetime import date

# حارس «غير مُمرَّر» لتمييز «لم يُرسَل الحقل» عن «أُرسِل None صراحةً».
_UNSET: object = object()
UNSET = _UNSET  # اسم عامّ للاستدعاء من الراوترات (نفس الحارس)


def parse_iso_date(value: str) -> date | None:
    """يحلّل تاريخاً صارماً بصيغة ``YYYY-MM-DD`` فقط؛ ``None`` إن فشل. لا يرفع."""
    if not isinstance(value, str):
        return None
    v = value.strip()
    if len(v) != 10 or v[4] != "-" or v[7] != "-":
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def resolve_and_check_date_order(
    *,
    current_sowing: date | None,
    current_end: date | None,
    new_sowing: date | None | object = _UNSET,
    new_end: date | None | object = _UNSET,
) -> str | None:
    """يدمج تعديل التواريخ الجزئيّ مع المخزّن ويؤكّد بذار ≤ نهاية على القيم **النهائيّة**.

    ``new_sowing``/``new_end`` تُمرَّر فقط إن أرسلها العميل (وإلّا تبقى ``_UNSET`` فتُستعمل
    القيمة المخزّنة). يُعيد رسالة خطأ عربيّة إن كانت النهاية قبل البذار بعد الدمج، وإلّا ``None``.
    """
    final_sowing = current_sowing if new_sowing is _UNSET else new_sowing
    final_end = current_end if new_end is _UNSET else new_end
    if isinstance(final_sowing, date) and isinstance(final_end, date) and final_end < final_sowing:
        return "نهاية الموسم قبل البذار (بعد دمج التعديل مع القيم المخزّنة للموسم)"
    return None


def _stage_field(stage: object, key: str) -> str:
    """يستخرج حقلاً نصّيّاً من مرحلة (dict أو نموذج Pydantic) مُقلَّماً."""
    if isinstance(stage, dict):
        val = stage.get(key, "")
    else:
        val = getattr(stage, key, "")
    return (val or "").strip() if isinstance(val, str) else ""


def validate_custom_stages(
    stages: list,
    *,
    sowing_date: date | None = None,
    season_end: date | None = None,
) -> tuple[list[dict], list[str]]:
    """يُنظّف مراحل الموسم المخصّصة ويتحقّق من سلامتها الزمنيّة.

    القواعد (صدق: لا Timeline مضلِّل):
      • المرحلة الفارغة كليّاً (name/date/notes فارغة) تُسقَط بصمت (سلوك قديم محفوظ).
      • المرحلة المؤرَّخة يجب أن تكون بصيغة ``YYYY-MM-DD`` صالحة.
      • المراحل المؤرَّخة يجب ألّا تتراجع زمنيّاً عبر القائمة (ترتيب غير متراجع).
      • المرحلة المؤرَّخة يجب أن تقع داخل نافذة الموسم [بذار، نهاية] متى عُرِفت الحدود.
      • أسماء المراحل غير الفارغة يجب ألّا تتكرّر (بلا حساسيّة لحالة الأحرف).

    يُعيد ``(cleaned, errors)`` — ``cleaned`` مراحل مُنظَّفة (dicts بمفاتيح name/date/notes)،
    و``errors`` قائمة رسائل عربيّة (فارغة ⇒ سليمة).
    """
    errors: list[str] = []
    cleaned: list[dict] = []
    seen_names: set[str] = set()
    prev_dated: date | None = None

    for stage in stages:
        name = _stage_field(stage, "name")
        datestr = _stage_field(stage, "date")
        notes = _stage_field(stage, "notes")
        if not (name or datestr or notes):
            continue  # فارغة كليّاً ⇒ تُسقَط (سلوك قديم)

        label = name or datestr  # للرسائل

        if name:
            key = name.casefold()
            if key in seen_names:
                errors.append(f"اسم مرحلة مكرّر: «{name}»")
            seen_names.add(key)

        if datestr:
            d = parse_iso_date(datestr)
            if d is None:
                errors.append(
                    f"تاريخ مرحلة غير صالح (المتوقّع YYYY-MM-DD): «{datestr}» في «{label}»"
                )
            else:
                if sowing_date is not None and d < sowing_date:
                    errors.append(f"مرحلة «{label}» قبل تاريخ البذار")
                if season_end is not None and d > season_end:
                    errors.append(f"مرحلة «{label}» بعد نهاية الموسم")
                if prev_dated is not None and d < prev_dated:
                    errors.append(f"ترتيب المراحل متراجع زمنيّاً عند «{label}»")
                prev_dated = d

        cleaned.append({"name": name, "date": datestr, "notes": notes})

    return cleaned, errors
