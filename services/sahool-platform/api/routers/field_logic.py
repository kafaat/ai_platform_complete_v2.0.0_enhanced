"""api/routers/field_logic.py — منطق نقيّ لنطاق الحقول (مُستخرَج من ``fields.py``).

دوالّ مساعِدة نقيّة بلا قاعدة بيانات/شبكة/حالة عامّة: حلّ تعارُض التحديث (3-way merge)
وحارس الهندسة الموحَّد للدمج/الانقسام. نُقِلت حرفيّاً من ``api/routers/fields.py``
(تقليص الوحدة الأحاديّة) وتُعاد استيرادها هناك — السلوك محفوظ بالكامل.

لا استيراد من ``fields.py`` (تفادي الدورة): تستورد ما تحتاجه مباشرةً من مصادره
(``fastapi.HTTPException`` و``api.gis_geometry_guard.guard_field_geometry``).
"""

from __future__ import annotations

from fastapi import HTTPException

from api.gis_geometry_guard import guard_field_geometry


def _conflict_changed_fields(client_changes: dict, server_record: dict) -> list[str]:
    """الحقول التي حاول العميل تغييرها وتختلف عن قيمة الخادم الحاليّة (لحلّ التعارض).

    دالّة نقيّة: تُقارن ما أرسله العميل بما في سجلّ الخادم — المفاتيح المشتركة فقط
    (تُقارَن في نفس وضع التسلسُل). تُغذّي Conflict Resolution Workflow في الواجهة.
    """
    return [k for k, v in client_changes.items() if k in server_record and server_record[k] != v]


def _field_merge_plan(
    client_changes: dict, server_record: dict, base_values: dict | None
) -> tuple[bool, list[str]]:
    """خطّة دمج 3-way لتعارض تحديث الحقل (دالّة نقيّة، Level 3).

    لكلّ عمود غيّره العميل: إن طابق الخادمُ نيّةَ العميل (server == new) ⇒ لا-عمل؛
    وإلّا إن طابق الخادمُ أساسَ العميل (server == base) ⇒ آمن للدمج (الطرف الآخر لم
    يمسّ العمود)؛ وإلّا ⇒ تعارض حقيقيّ (غيّر الطرفان العمود نفسه، أو لا أساس لتحديد
    الأمان ⇒ fail-closed). يُرجِع (can_auto_merge, conflict_fields). الدمج الآليّ
    ممكن فقط حين تُتاح base_values ولا تعارض حقيقيّ.
    """
    conflicts: list[str] = []
    for col, new_val in client_changes.items():
        if col not in server_record:
            continue
        srv = server_record[col]
        if srv == new_val:
            continue  # الخادم == نيّة العميل (لا-عمل)
        if base_values is not None and col in base_values and srv == base_values[col]:
            continue  # الخادم لم يتغيّر عن أساس العميل ⇒ آمن للدمج
        conflicts.append(col)
    return (bool(base_values) and not conflicts), conflicts


def _guard_merge_split_geometry(
    raw_geometry: object,
) -> tuple[dict, float, tuple[float | None, float | None]]:
    """حارس هندسة موحَّد للدمج/الانقسام — نفس شكل خطأ _persist_field (422) عند الفشل.

    يُرجِع (geometry, area_ha, (lat, lon)). لا I/O — منطق تحقّق صرف عبر guard_field_geometry.
    """
    try:
        guarded = guard_field_geometry(raw_geometry)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message_ar": "هندسة الحقل غير صالحة — صحّح الحدود وأعد المحاولة.",
                "code": "invalid_field_geometry",
                "issues": str(exc).split(","),
            },
        ) from exc
    return guarded.geometry, round(guarded.area_ha, 2), guarded.centroid
