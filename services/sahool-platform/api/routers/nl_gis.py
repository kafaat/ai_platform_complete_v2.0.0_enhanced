"""api/routers/nl_gis.py — GIS باللغة الطبيعيّة (read-only، #9)

نقطة واحدة محروسة بعلم ``FEATURE_NATURAL_LANGUAGE_GIS`` (مُطفأة افتراضاً ⇒ 404):

  • ``POST /api/v1/nl-gis/query`` — يأخذ نصّاً عربيّاً، يُصنّفه عبر الطبقة النقيّة
    ``parse_nl_intent`` إلى **نيّة من قائمة مغلقة** (whitelist)، ثمّ يُترجم النيّة
    المعروفة فقط إلى **استعلام قراءة على مصدر موجود** (fields/alerts/ndvi_timeseries/
    irrigation_schedules) عبر ``tenant_connection`` (عزل RLS). يُدوّن كلّ استعلام في
    سجلّ التدقيق append-only ``nl_gis_audit`` (best-effort).

**حُرّاس صارمة** (شروط القبول):
  • **read_only** ثابت: لا CREATE/UPDATE/DELETE، لا أوامر، لا تغيير قرارات — SELECT فقط.
  • **whitelist intents**: أيّ نيّة خارج ``SUPPORTED_INTENTS`` ⇒ رفض صريح (لا SQL حُرّ).
  • **tenant من JWT** حصراً (``user.tenant_id``) لا من نصّ المستخدم؛ RLS يفرض العزل.
  • **RBAC**: يتطلّب صلاحيّة العرض (``RECOMMENDATION_VIEW``).
  • **لا طبقة بلا بيانات**: تعذّر المصدر/غيابه ⇒ ``needs_data`` لا تلفيق.
  • **الخانات مُمرَّرة كمعاملات** (bound params) دائماً — لا حقن نصّ المستخدم في SQL.

404 إن مُطفأ، 503 إن تعذّرت القاعدة كليّاً.
"""

from __future__ import annotations

import json as _json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)
from api.nl_gis_intent import SUPPORTED_INTENTS, parse_nl_intent

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}
_MAX_ROWS = 200  # سقف نتائج صارم (حماية القاعدة + معاينة لا تفريغ كامل)


def _nl_gis_enabled() -> bool:
    """هل ميزة GIS باللغة الطبيعيّة مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_NATURAL_LANGUAGE_GIS", "").strip().lower() in _TRUTHY


def _crop_region_clauses(slots: dict, args: list, start_idx: int) -> tuple[str, list]:
    """يبني شروط محصول/منطقة اختياريّة كمعاملات مربوطة (لا حقن نصّ) — يعيد (SQL, args).

    الخانات من whitelist الطبقة النقيّة وتُمرَّر دائماً كـ``$n`` — لا تُدمَج في النصّ.
    """
    clauses = ""
    idx = start_idx
    crop = slots.get("crop")
    region = slots.get("region")
    if crop:
        clauses += f" AND f.crop ILIKE '%' || ${idx} || '%'"
        args.append(crop)
        idx += 1
    if region:
        clauses += f" AND f.gov ILIKE '%' || ${idx} || '%'"
        args.append(region)
        idx += 1
    return clauses, args


async def _dispatch_alert_filter(conn, slots: dict) -> dict:
    """حقول بتنبيه نشط (نوع/محصول/منطقة اختياريّة) — قراءة من alerts ⋈ fields."""
    args: list = []
    where = "a.status = 'active'"
    if slots.get("alert_type"):
        args.append(slots["alert_type"])
        where += f" AND a.alert_type = ${len(args)}"
    extra, args = _crop_region_clauses(slots, args, len(args) + 1)
    sql = (
        "SELECT f.field_id, f.name, f.crop, f.gov, a.alert_type, a.severity, a.title_ar "
        "FROM alerts a JOIN fields f ON f.field_id = a.field_id "
        f"WHERE {where}{extra} "
        f"ORDER BY a.created_at DESC LIMIT {_MAX_ROWS}"
    )
    rows = await conn.fetch(sql, *args)
    return {
        "api_called": "alerts⋈fields",
        "items": [dict(r) for r in rows],
    }


async def _dispatch_ndvi_drop(conn, slots: dict) -> dict:
    """حقول انخفض NDVI فيها ≥ عتبة٪ (أحدث قراءة مقابل سابقتها) — من ndvi_timeseries."""
    threshold = float(slots.get("threshold_pct") or 0)
    args: list = [threshold]
    extra, args = _crop_region_clauses(slots, args, 2)
    sql = (
        "WITH ranked AS ("
        "  SELECT field_id, ndvi_mean, acquisition_date, "
        "         ROW_NUMBER() OVER (PARTITION BY field_id ORDER BY acquisition_date DESC) AS rn "
        "  FROM ndvi_timeseries), "
        "pair AS ("
        "  SELECT r1.field_id, r1.ndvi_mean AS latest, r2.ndvi_mean AS prev, "
        "         r1.acquisition_date AS latest_date "
        "  FROM ranked r1 JOIN ranked r2 ON r1.field_id = r2.field_id AND r2.rn = 2 "
        "  WHERE r1.rn = 1) "
        "SELECT p.field_id, f.name, f.crop, f.gov, "
        "       ROUND(p.latest, 4) AS ndvi_latest, ROUND(p.prev, 4) AS ndvi_prev, "
        "       ROUND(((p.prev - p.latest) / NULLIF(p.prev, 0) * 100)::numeric, 1) AS drop_pct, "
        "       p.latest_date "
        "FROM pair p JOIN fields f ON f.field_id = p.field_id "
        "WHERE p.prev > 0 AND ((p.prev - p.latest) / p.prev * 100) >= $1"
        f"{extra} "
        f"ORDER BY drop_pct DESC LIMIT {_MAX_ROWS}"
    )
    rows = await conn.fetch(sql, *args)
    return {
        "api_called": "ndvi_timeseries",
        "items": [dict(r) for r in rows],
    }


async def _dispatch_irrigation_gap(conn, slots: dict) -> dict:
    """حقول لم تُروَ منذ N يوم (أو بلا تشغيل) — من irrigation_schedules.last_run_at."""
    days = int(slots.get("days") or 0)
    args: list = [days]
    extra, args = _crop_region_clauses(slots, args, 2)
    sql = (
        "SELECT f.field_id, f.name, f.crop, f.gov, MAX(s.last_run_at) AS last_run_at "
        "FROM fields f LEFT JOIN irrigation_schedules s ON s.field_id = f.field_id "
        f"WHERE 1 = 1{extra} "
        "GROUP BY f.field_id, f.name, f.crop, f.gov "
        "HAVING MAX(s.last_run_at) IS NULL "
        "    OR MAX(s.last_run_at) < now() - make_interval(days => $1) "
        f"ORDER BY last_run_at ASC NULLS FIRST LIMIT {_MAX_ROWS}"
    )
    rows = await conn.fetch(sql, *args)
    return {
        "api_called": "irrigation_schedules",
        "items": [dict(r) for r in rows],
    }


_DISPATCHERS = {
    "alert_filter": _dispatch_alert_filter,
    "ndvi_drop": _dispatch_ndvi_drop,
    "irrigation_gap": _dispatch_irrigation_gap,
}


async def _append_nl_gis_audit(
    conn,
    user: UserSchema,
    query_text: str,
    intent: str,
    slots: dict,
    api_called: str | None,
    result_status: str,
    result_count: int | None,
) -> None:
    """يُدرِج قيد تدقيق append-only داخل **savepoint** best-effort — فشله (مثلاً غياب
    الجدول قبل v85) لا يكسر الاستجابة. الصدق: read_only=TRUE دائماً، الخانات كما استُخلِصت.
    """
    try:
        async with conn.transaction():  # SAVEPOINT داخل معاملة tenant_connection
            await conn.execute(
                """INSERT INTO nl_gis_audit
                    (tenant_id, query_text, intent, slots, api_called,
                     result_status, result_count, read_only, actor)
                   VALUES ($1::uuid, $2, $3, $4::jsonb, $5, $6, $7, TRUE, $8)""",
                str(user.tenant_id),
                query_text,
                intent,
                _json.dumps(slots, ensure_ascii=False),
                api_called,
                result_status,
                result_count,
                str(user.user_id),
            )
    except Exception:  # noqa: BLE001 — تدقيق best-effort: فشله لا يكسر الاستجابة
        pass


class NlGisQueryRequest(BaseModel):
    query: str


def _serialize(items: list[dict]) -> list[dict]:
    """يطبّع القيم غير الـJSON (تواريخ/أرقام دقيقة) إلى نصّ — صدق بلا فقد دقّة صامت."""
    out: list[dict] = []
    for it in items:
        row = {}
        for k, v in it.items():
            row[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
        out.append(row)
    return out


@router.post("/api/v1/nl-gis/query")
async def nl_gis_query_endpoint(
    req: NlGisQueryRequest,
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """يفسّر استعلاماً عربيّاً ويُعيد معاينة قراءة فقط من مصدر موجود — 404 إن مُطفأ.

    المسار: تصنيف نيّة (قائمة مغلقة) → حارس whitelist → استعلام قراءة عبر tenant_connection
    (عزل RLS، tenant من JWT) → تدقيق append-only. لا إنشاء/تعديل/حذف، لا SQL حُرّ، لا تلفيق:
    تعذّر المصدر ⇒ needs_data؛ نيّة غير مدعومة ⇒ unsupported.
    """
    if not _nl_gis_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة GIS باللغة الطبيعيّة غير مُفعَّلة (اضبط FEATURE_NATURAL_LANGUAGE_GIS).",
        )

    parsed = parse_nl_intent(req.query)
    intent = parsed["intent"]
    slots = parsed.get("slots", {})

    # حارس whitelist: نيّة غير مدعومة ⇒ رفض صريح + تدقيق (لا استدعاء، لا SQL).
    if intent not in SUPPORTED_INTENTS:
        try:
            async with tenant_connection(user) as conn:
                await _append_nl_gis_audit(
                    conn, user, req.query, intent, slots, None, "unsupported", None
                )
        except Exception:  # noqa: BLE001 — تعذّر التدقيق لا يمنع الردّ الصريح
            pass
        return {
            "read_only": True,
            "intent": intent,
            "supported": False,
            "status": "unsupported",
            "reason_ar": parsed.get("reason_ar", "طلب غير مدعوم."),
            "items": [],
            "count": 0,
            "tenant_id": str(user.tenant_id),
        }

    # نيّة مدعومة: استعلام قراءة best-effort (غياب المصدر ⇒ needs_data، لا تلفيق).
    try:
        async with tenant_connection(user) as conn:
            try:
                result = await _DISPATCHERS[intent](conn, slots)
                items = _serialize(result["items"])
                api_called = result["api_called"]
                status = "ok"
                count: int | None = len(items)
            except Exception:  # noqa: BLE001 — جدول غائب/استعلام تعذّر ⇒ needs_data صادق
                items, api_called, status, count = (
                    [],
                    _DISPATCHERS[intent].__name__,
                    "needs_data",
                    None,
                )
            await _append_nl_gis_audit(
                conn, user, req.query, intent, slots, api_called, status, count
            )
    except Exception as e:  # noqa: BLE001 — تعذّر فتح اتّصال المستأجِر ⇒ 503 موثَّق
        raise _db_unavailable("استعلام NL-GIS", e) from e

    note_ar = None
    if status == "needs_data":
        note_ar = "المصدر غير متاح حاليّاً (جدول غائب أو استعلام تعذّر) — لا تُعرَض طبقة دون بيانات."
    elif count == 0:
        note_ar = "لا حقول تطابق هذا الطلب (نتيجة صادقة، لا تلفيق)."

    return {
        "read_only": True,
        "intent": intent,
        "supported": True,
        "status": status,
        "slots": slots,
        "confidence": parsed.get("confidence"),
        "api_called": api_called,
        "items": items,
        "count": count if count is not None else 0,
        "note_ar": note_ar,
        "tenant_id": str(user.tenant_id),
    }
