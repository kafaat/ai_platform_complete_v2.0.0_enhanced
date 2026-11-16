"""api/routers/nl_gis.py — GIS باللغة الطبيعيّة (read-only، #9)

نقطة واحدة محروسة بعلم ``FEATURE_NATURAL_LANGUAGE_GIS`` (مُطفأة افتراضاً ⇒ 404):

  • ``POST /api/v1/nl-gis/query`` — يأخذ نصّاً عربيّاً، يُصنّفه عبر الطبقة النقيّة
    ``parse_nl_intent`` إلى **نيّة من قائمة مغلقة** (whitelist)، ثمّ يُترجم النيّة
    المعروفة فقط إلى **استعلام قراءة على مصدر موجود** (fields/alerts/irrigation_schedules)
    عبر ``tenant_connection`` (عزل RLS)، و NDVI من raster-service (W1-21: لا من جدول البذرة
    ``ndvi_timeseries``). يُدوّن كلّ استعلام في سجلّ التدقيق append-only ``nl_gis_audit``
    (best-effort).

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

import asyncio
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
from api.raster_service_client import latest_index_points

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}
_MAX_ROWS = 200  # سقف نتائج صارم (حماية القاعدة + معاينة لا تفريغ كامل)
# ndvi_drop يقرأ raster لكلّ حقل: سقف حقول المسح وتزامن النداءات (حماية raster-service).
_NDVI_SCAN_FIELDS = 50
_RASTER_CONCURRENCY = 8
# مهلة المسح كلّه وقراءة الحقل الواحد (ث): raster معلَّق لا يتجاوز مهلة البوّابة (60ث فأكثر)؛
# حقل لم يُقرأ قبل انقضاء المهلة يُعدّ «تعذّرت قراءته» لا «بلا انخفاض».
_NDVI_SCAN_DEADLINE_S = 40.0
_NDVI_FIELD_TIMEOUT_S = 15.0
_NDVI_SOURCE = "raster-service:/v1/fields/{id}/timeseries"


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
    """المرحلة الأولى لـndvi_drop (القاعدة): حقول المستأجِر المرشّحة (محصول/منطقة اختياريّة).

    قيم NDVI لا تُقرأ هنا: W1-21 (remote-2/data-7) — جدول ``ndvi_timeseries`` بذرةُ ``RANDOM()``
    بلا مستأجِر ولا كاتب حيّ. المرحلة الثانية ``_raster_ndvi_drop`` تقرأ أحدث قراءتين من
    raster-service بعد إغلاق اتّصال القاعدة.
    """
    args: list = []
    extra, args = _crop_region_clauses(slots, args, 1)
    sql = (
        "SELECT f.field_id, f.name, f.crop, f.gov FROM fields f "
        f"WHERE 1 = 1{extra} "
        f"ORDER BY f.field_id LIMIT {_NDVI_SCAN_FIELDS + 1}"
    )
    rows = await conn.fetch(sql, *args)
    return {"api_called": _NDVI_SOURCE, "items": [], "fields": [dict(r) for r in rows]}


async def _raster_ndvi_drop(result: dict, slots: dict, tenant_id: str) -> dict:
    """المرحلة الثانية لـndvi_drop: انخفاض أحدث NDVI مرصود عن سابقه ≥ عتبة٪ (raster-service).

    حقل تعذّرت قراءته (أو لم يُقرأ قبل ``_NDVI_SCAN_DEADLINE_S``) يُعدّ في ``raster_unavailable``
    (لا يُعامَل كحقل بلا انخفاض)؛ إن تعذّر raster لكلّ الحقول يرفع فيصير الردّ ``needs_data``
    صادقاً. حقل بأقلّ من قراءتين (بلا تاريخ NDVI معالَج أو بقراءة واحدة) يُعدّ في
    ``insufficient_history``، وحقل قراءته السابقة ≤ 0 (لا نسبة انخفاض معرَّفة) في
    ``not_comparable`` — كلّ حقل متخطّى يُعدّ بسببه. ``coverage.complete`` كاذب إن تخطّى حقلٌ
    لأيّ سبب أو بُتر المسح عند السقف — فيصير الردّ ``partial`` لا «لا حقول تطابق».
    """
    threshold = float(slots.get("threshold_pct") or 0)
    candidates = result["fields"]
    truncated = len(candidates) > _NDVI_SCAN_FIELDS
    candidates = candidates[:_NDVI_SCAN_FIELDS]
    gate = asyncio.Semaphore(_RASTER_CONCURRENCY)

    async def read(field: dict):
        async with gate:
            return await latest_index_points(
                str(field["field_id"]),
                tenant_id=tenant_id,
                index="ndvi",
                count=2,
                timeout_s=_NDVI_FIELD_TIMEOUT_S,
            )

    tasks = [asyncio.ensure_future(read(f)) for f in candidates]
    readings: list = [None] * len(tasks)
    if tasks:
        _done, pending = await asyncio.wait(tasks, timeout=_NDVI_SCAN_DEADLINE_S)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for i, task in enumerate(tasks):
            if task in pending or task.cancelled() or task.exception() is not None:
                continue  # لم يُقرأ قبل المهلة/فشل ⇒ يبقى None (تعذّر، لا «بلا انخفاض»)
            readings[i] = task.result()
    unavailable = sum(1 for r in readings if r is None)
    if candidates and unavailable == len(candidates):
        raise RuntimeError("raster-service unavailable for every candidate field")
    items: list[dict] = []
    insufficient = 0
    not_comparable = 0
    for field, points in zip(candidates, readings, strict=True):
        if points is None:
            continue  # عُدّ أعلاه في raster_unavailable
        if len(points) < 2:
            insufficient += 1  # لا قراءتين مرصودتين ⇒ مجهول، لا «بلا انخفاض»
            continue
        latest, prev = points[0]["mean"], points[1]["mean"]
        if prev <= 0:
            not_comparable += 1  # لا نسبة انخفاض معرَّفة ⇒ مجهول
            continue
        drop_pct = (prev - latest) / prev * 100
        if drop_pct < threshold:
            continue
        items.append(
            {
                **field,
                "ndvi_latest": round(latest, 4),
                "ndvi_prev": round(prev, 4),
                "drop_pct": round(drop_pct, 1),
                "latest_date": points[0]["datetime"],
                "prev_date": points[1]["datetime"],
            }
        )
    items.sort(key=lambda it: it["drop_pct"], reverse=True)
    return {
        "api_called": _NDVI_SOURCE,
        "items": items[:_MAX_ROWS],
        "coverage": {
            "fields_scanned": len(candidates),
            "fields_truncated": truncated,
            "raster_unavailable": unavailable,
            "insufficient_history": insufficient,
            "not_comparable": not_comparable,
            "complete": not truncated and unavailable + insufficient + not_comparable == 0,
        },
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
# نيّات لها مرحلة raster بعد القاعدة (تعمل بعد إغلاق الاتّصال — لا HTTP داخل معاملة).
_RASTER_STAGES = {"ndvi_drop": _raster_ndvi_drop}


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


def _partial_note_ar(coverage: dict, count: int) -> str:
    """شرح مسح ناقص: كم حقلاً لم يُقَس، وهل بُتر المسح — فلا يُقرأ الفراغ كنتيجة صادقة."""
    parts = []
    unavailable = int(coverage.get("raster_unavailable") or 0)
    if unavailable:
        parts.append(f"تعذّرت قراءة NDVI لـ{unavailable} من {coverage.get('fields_scanned')} حقل")
    insufficient = int(coverage.get("insufficient_history") or 0)
    if insufficient:
        parts.append(
            f"{insufficient} من {coverage.get('fields_scanned')} حقل بلا قراءتَي NDVI مرصودتين"
            " للمقارنة"
        )
    not_comparable = int(coverage.get("not_comparable") or 0)
    if not_comparable:
        parts.append(
            f"{not_comparable} من {coverage.get('fields_scanned')} حقل قراءته السابقة ≤ 0"
            " فلا نسبة انخفاض معرَّفة"
        )
    if coverage.get("fields_truncated"):
        parts.append(f"فُحص أوّل {_NDVI_SCAN_FIELDS} حقلاً فقط (ضيّق الطلب بمحصول أو منطقة)")
    head = "نتيجة ناقصة: " + "؛ ".join(parts) + "."
    if count == 0:
        return head + " لا يعني ذلك أنّ أيّ حقل لم ينخفض — الحقول غير المقيسة مجهولة."
    return head + " الحقول المعروضة مقيسة؛ غير المقيسة مجهولة."


def _status_after_raster(result: dict) -> str:
    """``partial`` إن كان مسح raster ناقصاً (حقل تعذّر أو بتر عند السقف)، وإلّا ``ok``."""
    return "ok" if (result.get("coverage") or {}).get("complete", True) else "partial"


def _audit_status(status: str, count: int | None) -> str:
    """جدول التدقيق يقبل مجموعة مغلقة (v85 CHECK): المسح الناقص بلا نتيجة لا يُدوَّن ``ok``."""
    if status == "partial":
        return "ok" if count else "needs_data"
    return status


def _response_note_ar(status: str, count: int | None, coverage: dict) -> str | None:
    """شرح الحالة للواجهة: الفراغ الصادق يُقال فقط حين قيس كلّ حقل."""
    if status == "needs_data":
        return "المصدر غير متاح حاليّاً (جدول غائب أو استعلام تعذّر) — لا تُعرَض طبقة دون بيانات."
    if status == "partial":
        return _partial_note_ar(coverage, count or 0)
    if count == 0:
        return "لا حقول تطابق هذا الطلب (نتيجة صادقة، لا تلفيق)."
    return None


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
    raster_stage = _RASTER_STAGES.get(intent)
    result: dict = {}
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
            if raster_stage is None:
                await _append_nl_gis_audit(
                    conn, user, req.query, intent, slots, api_called, status, count
                )
    except Exception as e:  # noqa: BLE001 — تعذّر فتح اتّصال المستأجِر ⇒ 503 موثَّق
        raise _db_unavailable("استعلام NL-GIS", e) from e

    if raster_stage is not None:
        if status == "ok":
            try:
                result = await raster_stage(result, slots, str(user.tenant_id))
                items = _serialize(result["items"])
                count = len(items)
                status = _status_after_raster(result)
            except Exception:  # noqa: BLE001 — raster تعذّر ⇒ needs_data صادق، لا طبقة فارغة
                items, status, count = [], "needs_data", None
        try:
            async with tenant_connection(user) as conn:
                await _append_nl_gis_audit(
                    conn,
                    user,
                    req.query,
                    intent,
                    slots,
                    api_called,
                    _audit_status(status, count),
                    count,
                )
        except Exception:  # noqa: BLE001 — تدقيق best-effort: فشله لا يكسر الاستجابة
            pass

    note_ar = _response_note_ar(status, count, result.get("coverage") or {})

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
        "coverage": result.get("coverage") if status in ("ok", "partial") else None,
        "tenant_id": str(user.tenant_id),
    }
