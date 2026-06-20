"""api/routers/evidence_map.py — خريطة الدليل (قراءة فقط، #4)

نقطة واحدة محروسة بعلم ``FEATURE_EVIDENCE_MAP`` (مُطفأة افتراضاً ⇒ 404):

  • ``GET /api/v1/evidence/map`` — لكلّ حقل للمستأجِر: **مستوى الدليل** خلف قراراته
    (مؤكَّد ميدانيّاً/مدعوم/إرشاديّ/needs_data) مُجمَّعاً من ``decision_record`` +
    ``outcome_record`` المُدامين (عزل RLS)، مع إحداثيّات الحقل الحقيقيّة للرسم.

**الصدق**: المستوى من العدّ المُدام فقط — لا ترقية دون قياس فعليّ؛ الحقل بلا دليل
``needs_data`` (لا تلوين افتراضيّ). كلّ تجميع فرعيّ best-effort: جدول الدليل الغائب
(قبل تطبيق هجراته) ⇒ أعداد 0 لا انهيار. لا إحداثيّات مُختلقة (الحقل بلا lat/lon لا
يُرسَم). 503 فقط إن تعذّر فتح اتّصال المستأجِر أصلاً.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from api.evidence_map import shape_evidence_map
from api.main import (
    Permission,
    UserSchema,
    _db_unavailable,
    require_permission,
    tenant_connection,
)

router = APIRouter()

_TRUTHY = {"1", "true", "yes", "on"}
_MAX_FIELDS = 500  # سقف صارم (خريطة لا تفريغ كامل)


def _evidence_map_enabled() -> bool:
    """هل ميزة خريطة الدليل مُفعَّلة؟ (مُطفأة افتراضاً — إنضاج تدريجيّ)."""
    return os.getenv("FEATURE_EVIDENCE_MAP", "").strip().lower() in _TRUTHY


async def _field_evidence_rows(conn) -> list[dict]:
    """يجمّع لكلّ حقل عدد قراراته وقياساته المُدامة + إحداثيّاته — best-effort.

    LEFT JOIN على عدّادات ``decision_record``/``outcome_record`` المُجمَّعة مسبقاً (لا
    تضخيم بصفّ مكرّر). أيّ خطأ (جدول دليل غائب قبل هجرته) ⇒ يُرفع للمُتصل ليُترجَم needs_data
    عبر استعلام احتياطيّ على الحقول وحدها (لا انهيار).
    """
    sql = (
        "SELECT f.field_id, f.name, f.crop, f.gov, f.lat, f.lon, "
        "       COALESCE(d.cnt, 0) AS decisions, "
        "       COALESCE(o.cnt, 0) AS outcomes, "
        "       COALESCE(o.successes, 0) AS successes, "
        "       o.last_outcome_at "
        "FROM fields f "
        "LEFT JOIN (SELECT field_id, COUNT(*) AS cnt FROM decision_record "
        "           WHERE field_id IS NOT NULL GROUP BY field_id) d "
        "       ON d.field_id = f.field_id "
        "LEFT JOIN (SELECT field_id, COUNT(*) AS cnt, "
        "                  COUNT(*) FILTER (WHERE success IS TRUE) AS successes, "
        "                  MAX(created_at) AS last_outcome_at FROM outcome_record "
        "           WHERE field_id IS NOT NULL GROUP BY field_id) o "
        "       ON o.field_id = f.field_id "
        f"ORDER BY f.field_id LIMIT {_MAX_FIELDS}"
    )
    rows = await conn.fetch(sql)
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        last = d.get("last_outcome_at")
        if last is not None and hasattr(last, "isoformat"):
            d["last_outcome_at"] = last.isoformat()
        # lat/lon قد تكون Decimal — مرّرها كما هي؛ الطبقة النقيّة تتحقّق رقميّتها.
        out.append(d)
    return out


async def _fields_only_rows(conn) -> list[dict]:
    """احتياطيّ: الحقول وحدها (إن غاب جدول دليل) — كلّها ستُصنَّف needs_data بصدق."""
    rows = await conn.fetch(
        f"SELECT field_id, name, crop, gov, lat, lon FROM fields ORDER BY field_id LIMIT {_MAX_FIELDS}"
    )
    return [dict(r) for r in rows]


@router.get("/api/v1/evidence/map")
async def evidence_map_endpoint(
    user: UserSchema = Depends(require_permission(Permission.RECOMMENDATION_VIEW)),
) -> dict:
    """خريطة دليل المستأجِر (RLS) — قراءة فقط. 404 إن مُطفأ، 503 إن تعذّرت القاعدة.

    يجمّع مستوى الدليل لكلّ حقل من القرارات/القياسات المُدامة ثمّ يُشكّله عبر الطبقة
    النقيّة. غياب جدول الدليل ⇒ سقوط لطيف إلى الحقول وحدها (كلّها needs_data، لا تلفيق).
    """
    if not _evidence_map_enabled():
        raise HTTPException(
            status_code=404,
            detail="ميزة خريطة الدليل غير مُفعَّلة (اضبط FEATURE_EVIDENCE_MAP).",
        )
    try:
        async with tenant_connection(user) as conn:
            try:
                fields = await _field_evidence_rows(conn)
            except Exception:  # noqa: BLE001 — جدول دليل غائب ⇒ احتياطيّ الحقول وحدها
                fields = await _fields_only_rows(conn)
    except Exception as e:  # noqa: BLE001 — تعذّر فتح اتّصال المستأجِر ⇒ 503 موثَّق
        raise _db_unavailable("خريطة الدليل", e) from e

    out = shape_evidence_map(fields, generated_at=datetime.now(UTC).isoformat())
    out["tenant_id"] = str(user.tenant_id)  # أثر: لِمن هذه الخريطة (RLS)
    return out
