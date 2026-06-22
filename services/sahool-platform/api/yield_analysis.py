"""api/yield_analysis.py — تجميع تحليل الغلّة (زراعة↔حصاد + أداء الهجن) — منطق نقيّ.

صدق أوّلاً: لا تلفيق. يُجمِّع **فقط** البيانات المُخزَّنة فعلاً في جدول ``seasons``
(المحصول/الصنف/الهجين، تاريخ البذار، الغلّة الفعليّة بعد الحصاد، الغلّة المستهدفة).
كلّ الحقول الزراعيّة في الموسم اختياريّة (ملء تدريجيّ) — فالدالّة تتعامل مع الغياب
بصدق (تتجاوز الصفوف بلا غلّة فعليّة عند بناء الأداء، وتُعلِن الفراغ صراحةً).

منطق نماذج صرف: stdlib فقط (لا I/O ولا تبعيّة على ``api.main``). يُستهلَك من
``api.routers.yield_analysis`` الذي يجلب الصفوف من القاعدة (ضمن سياق المستأجِر/RLS)
ويمرّرها هنا. هذا يجعل التجميع قابلاً لاختبار وحدة نقيّ (بيانات مُحاكاة، لا قاعدة).
"""

from __future__ import annotations

from typing import Any

# kg/ha ← t/ha: نعرض الغلّة بالطنّ/هكتار (وحدة FieldView المألوفة) من تخزين kg/ha.
_KG_PER_TONNE = 1000.0


def _to_float(v: Any) -> float | None:
    """تحويل آمن إلى float — None/غير الرقميّ ⇒ None (لا تلفيق صفر)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # يُسقِط NaN


def _kg_ha_to_t_ha(v: Any) -> float | None:
    f = _to_float(v)
    return round(f / _KG_PER_TONNE, 3) if f is not None else None


def _primary_crop(crops: Any) -> str | None:
    """المحصول الأساسيّ من مصفوفة المحاصيل (أوّل عنصر نصّيّ غير فارغ)، أو None."""
    if isinstance(crops, list):
        for c in crops:
            if isinstance(c, str) and c.strip():
                return c.strip()
    elif isinstance(crops, str) and crops.strip():
        return crops.strip()
    return None


def _date_str(v: Any) -> str | None:
    """تاريخ → ISO نصّيّ (date/datetime له isoformat)؛ النصّ يُمرَّر؛ غيره ⇒ None."""
    if v is None:
        return None
    if isinstance(v, str):
        return v or None
    iso = getattr(v, "isoformat", None)
    return iso() if callable(iso) else None


def _hybrid_label(row: dict[str, Any]) -> str | None:
    """تسمية الهجين/الصنف للمقارنة — cultivar إن وُجد، وإلّا seed_variety_source.

    لا اختراع: إن غاب كلاهما ⇒ None (الصفّ لا يدخل مقارنة أداء الهجن، لكنّه يبقى
    في مقارنة الزراعة↔الحصاد للحقل/الموسم).
    """
    for key in ("cultivar", "seed_variety_source"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def build_planting_vs_harvest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """صفّ لكلّ موسم: الزراعة (محصول/هجين/تاريخ بذار/مستهدف) مقابل الحصاد (غلّة فعليّة).

    يُبقي كلّ صفّ موسم كما هو (حتى بلا غلّة فعليّة — فجوة بيانات صريحة تُعرَض «—»).
    التواريخ/الأرقام تُمرَّر كما خُزِّنت؛ الغلّة تُحوَّل إلى طنّ/هكتار. لا فرز هنا
    (الراوتر يُمرّر الصفوف بترتيب القاعدة — الأحدث أوّلاً).
    """
    out: list[dict[str, Any]] = []
    for r in rows:
        actual_t = _kg_ha_to_t_ha(r.get("actual_yield_kg_ha"))
        target_t = _kg_ha_to_t_ha(r.get("target_yield_kg_ha"))
        maturity = r.get("maturity")
        out.append(
            {
                "season_id": r.get("season_id"),
                "field_id": r.get("field_id"),
                "field_name": r.get("field_name") or r.get("name"),
                "crop": _primary_crop(r.get("crops")),
                "hybrid": _hybrid_label(r),
                "maturity": maturity if isinstance(maturity, str) else None,
                "sowing_date": _date_str(r.get("sowing_date")),
                "season_end": _date_str(r.get("season_end")),
                "status": r.get("status"),
                "target_yield_t_ha": target_t,
                "actual_yield_t_ha": actual_t,
                # فجوة الفعليّ↔المستهدف (طنّ/هكتار) — فقط حين توفّر الطرفان (لا تلفيق).
                "yield_gap_t_ha": (
                    round(actual_t - target_t, 3)
                    if actual_t is not None and target_t is not None
                    else None
                ),
                "has_harvest": actual_t is not None,
            }
        )
    return out


def build_hybrid_performance(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """متوسّط الغلّة الفعليّة لكلّ هجين/صنف عبر الحقول/المواسم (مقارنة أداء).

    يدخل المقارنة **فقط** صفّ له هجين معروف **و** غلّة فعليّة مُسجَّلة (حصاد حقيقيّ).
    الصفوف بلا هجين أو بلا حصاد تُستبعَد بصدق (لا تُحتسَب صفراً، لا تُختلَق). تُرتَّب
    تنازليّاً بمتوسّط الغلّة (الأعلى أداءً أوّلاً). فارغة تماماً حين لا حصاد مُسجَّل.
    """
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        hybrid = _hybrid_label(r)
        actual_t = _kg_ha_to_t_ha(r.get("actual_yield_kg_ha"))
        if hybrid is None or actual_t is None:
            continue
        bucket = agg.setdefault(
            hybrid,
            {"hybrid": hybrid, "yields": [], "crops": set(), "fields": set()},
        )
        bucket["yields"].append(actual_t)
        crop = _primary_crop(r.get("crops"))
        if crop:
            bucket["crops"].add(crop)
        fid = r.get("field_id")
        if fid:
            bucket["fields"].add(fid)

    out: list[dict[str, Any]] = []
    for b in agg.values():
        ys: list[float] = b["yields"]
        n = len(ys)
        out.append(
            {
                "hybrid": b["hybrid"],
                "crops": sorted(b["crops"]),
                "season_count": n,
                "field_count": len(b["fields"]),
                "avg_yield_t_ha": round(sum(ys) / n, 3),
                "min_yield_t_ha": round(min(ys), 3),
                "max_yield_t_ha": round(max(ys), 3),
            }
        )
    out.sort(key=lambda x: x["avg_yield_t_ha"], reverse=True)
    return out


def assemble_yield_analysis(
    rows: list[dict[str, Any]],
    *,
    field_id: str | None = None,
    season: str | None = None,
) -> dict[str, Any]:
    """يجمّع تقرير تحليل الغلّة الكامل من صفوف المواسم المُخزَّنة (صدق أوّلاً).

    يبني (أ) مقارنة الزراعة↔الحصاد لكلّ موسم، و(ب) مقارنة أداء الهجن (متوسّط الغلّة)،
    و(ج) ملخّصاً صادقاً (عدد المواسم، كم منها بحصاد مُسجَّل). كلّ شيء من البيانات
    المُخزَّنة فقط — حين تغيب الأغلال (لا حصاد) تكون قوائم الأداء فارغة وتُعلَن الفجوة
    عبر ``note_ar``.
    """
    rows = rows or []
    planting_vs_harvest = build_planting_vs_harvest(rows)
    hybrid_performance = build_hybrid_performance(rows)

    seasons_total = len(planting_vs_harvest)
    seasons_with_harvest = sum(1 for r in planting_vs_harvest if r["has_harvest"])

    note_ar: str | None = None
    if seasons_total == 0:
        note_ar = (
            "لا مواسم مُسجَّلة لهذا النطاق — أنشئ موسماً (محصول/هجين/تاريخ بذار) "
            "ثمّ سجّل الغلّة الفعليّة بعد الحصاد لتظهر هنا. لا أرقام مُختلَقة."
        )
    elif seasons_with_harvest == 0:
        note_ar = (
            "توجد مواسم مُسجَّلة لكن بلا غلّة فعليّة بعد — سجّل actual_yield_kg_ha "
            "بعد الحصاد لتظهر مقارنة الزراعة↔الحصاد وأداء الهجن. لا تلفيق."
        )

    return {
        "scope": {"field_id": field_id, "season": season},
        "summary": {
            "seasons_total": seasons_total,
            "seasons_with_harvest": seasons_with_harvest,
            "hybrids_compared": len(hybrid_performance),
        },
        "planting_vs_harvest": planting_vs_harvest,
        "hybrid_performance": hybrid_performance,
        "units": {"yield": "t/ha"},
        "provenance": {
            "source": "seasons",
            "honesty": "stored_only",
            "note_ar": note_ar,
        },
    }
