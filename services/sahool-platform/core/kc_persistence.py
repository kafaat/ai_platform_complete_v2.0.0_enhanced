"""core/kc_persistence.py — رابط نقيّ: Kc المُشتقّ ⇐ سجلّ crop_kc_timeseries (تخزين دائم).

الفجوة المسدودة: Kc المُشتقّ كان يُحسَب كلّ مرّة بلا أثر — لا مقارنة تاريخيّة عبر المواسم.
هذه الوحدة هي الرابط النقيّ بين `FaoStageKc` (مخرَج kc_extraction_engine) وصفّ جدول
`crop_kc_timeseries` (مخطّط v76): تحويل صرف إلى قاموس جاهز للإدراج (INSERT)، ومقارنة
صفوف موسمين بلا I/O. الكتابة الفعليّة (asyncpg + RLS) تبقى في الراوتر (غلاف رفيع).

نقيّ حتميّ: لا I/O، لا قاعدة بيانات. السيناريوهات تطابق قيد CHECK في v76.
"""

from __future__ import annotations

from core.kc_extraction_engine import FaoStageKc

# سيناريوهات مسموحة — تطابق CHECK في migrations/v76_crop_kc_timeseries.sql.
KC_SCENARIOS: frozenset[str] = frozenset({"potential", "actual", "full_irrigation", "deficit"})

_DERIVED_SOURCE = "مُشتقّ من محاكاة WOFOST (CFET+تنعيم)"


def build_kc_record(
    stage_kc: FaoStageKc,
    *,
    field_id: str,
    tenant_id: str,
    crop_id: str,
    season_id: str,
    scenario_type: str = "potential",
    cfet: float = 1.0,
    source: str = _DERIVED_SOURCE,
) -> dict:
    """يبني صفّ crop_kc_timeseries من Kc المُشتقّ (مخطّط v76) — جاهز للإدراج.

    قيم Kc الناقصة (None) تبقى None (لا نختلق). يرفع ValueError إن كان السيناريو خارج
    KC_SCENARIOS (يطابق قيد CHECK في القاعدة — فشل مبكر واضح بدل خطأ إدراج غامض).
    """
    if scenario_type not in KC_SCENARIOS:
        raise ValueError(
            f"scenario_type غير صالح: {scenario_type} — المسموح: {sorted(KC_SCENARIOS)}"
        )
    return {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "crop_id": crop_id,
        "season_id": season_id,
        "scenario_type": scenario_type,
        "kc_ini": stage_kc.kc_ini,
        "kc_mid": stage_kc.kc_mid,
        "kc_end": stage_kc.kc_end,
        "kcb_ini": stage_kc.kcb_ini,
        "kcb_mid": stage_kc.kcb_mid,
        "kcb_end": stage_kc.kcb_end,
        "cfet": cfet,
        "source": source,
    }


def _delta(cur: float | None, prev: float | None) -> float | None:
    """فرق قيمتي Kc؛ None إن غابت أيّ منهما (لا نقارن مجهولاً)."""
    if cur is None or prev is None:
        return None
    return round(cur - prev, 4)


def compare_kc_rows(current: dict, previous: dict) -> dict:
    """يقارن صفّي Kc لموسمين (الحاليّ مقابل السابق) — اتّجاه كلّ مرحلة + حُكم عربيّ.

    يأخذ صفّين بمفاتيح kc_ini/kc_mid/kc_end (قاموسا build_kc_record أو صفّا قاعدة).
    لكلّ مرحلة: القيمتان والفرق (None-آمن). الحُكم من مرحلة المنتصف (الأكثر دلالةً على
    احتياج الماء الذرويّ): ارتفاع kc_mid ⇒ احتياج ماء أعلى. نقيّ حتميّ.
    """
    stages = {}
    for stage in ("kc_ini", "kc_mid", "kc_end"):
        cur, prev = current.get(stage), previous.get(stage)
        d = _delta(cur, prev)
        stages[stage] = {
            "current": cur,
            "previous": prev,
            "delta": d,
            "direction": ("flat" if d is None or d == 0 else ("up" if d > 0 else "down")),
        }

    mid = stages["kc_mid"]["delta"]
    if mid is None:
        verdict = "تعذّرت مقارنة kc_mid (قيمة ناقصة) — لا حُكم على احتياج الماء الذرويّ."
    elif mid > 0:
        verdict = "ارتفع Kc الذرويّ (المنتصف) — احتياج ماء أعلى هذا الموسم."
    elif mid < 0:
        verdict = "انخفض Kc الذرويّ (المنتصف) — احتياج ماء أقلّ هذا الموسم."
    else:
        verdict = "Kc الذرويّ ثابت بين الموسمين."

    return {
        "crop_id": current.get("crop_id"),
        "current_season_id": current.get("season_id"),
        "previous_season_id": previous.get("season_id"),
        "stages": stages,
        "verdict_ar": verdict,
    }
