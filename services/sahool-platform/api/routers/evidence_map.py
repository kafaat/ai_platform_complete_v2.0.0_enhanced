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

from api.decision_service_client import decision_post_json
from api.decision_sor_mode import get_platform_decision_sor_mode
from api.evidence_map import EVALUATED_OUTCOME_PREDICATE, shape_evidence_map
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


async def _field_evidence_rows(conn, tenant_id) -> list[dict]:
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
        "           WHERE tenant_id=$1::uuid AND field_id IS NOT NULL GROUP BY field_id) d "
        "       ON d.field_id = f.field_id "
        # الصفوفُ المُقيَّمة فقط (n_evaluated > 0) — كما في سجلّ الدليل (Copilot على #1001).
        f"LEFT JOIN (SELECT field_id, COUNT(*) FILTER (WHERE {EVALUATED_OUTCOME_PREDICATE}) AS cnt, "
        f"                  COUNT(*) FILTER (WHERE success IS TRUE AND {EVALUATED_OUTCOME_PREDICATE}) AS successes, "
        f"                  MAX(created_at) FILTER (WHERE {EVALUATED_OUTCOME_PREDICATE}) AS last_outcome_at "
        "           FROM outcome_record WHERE tenant_id=$1::uuid AND field_id IS NOT NULL GROUP BY field_id) o "
        "       ON o.field_id = f.field_id "
        f"WHERE f.tenant_id=$1::uuid ORDER BY f.field_id LIMIT {_MAX_FIELDS}"
    )
    rows = await conn.fetch(sql, tenant_id)
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        last = d.get("last_outcome_at")
        if last is not None and hasattr(last, "isoformat"):
            d["last_outcome_at"] = last.isoformat()
        # lat/lon قد تكون Decimal — مرّرها كما هي؛ الطبقة النقيّة تتحقّق رقميّتها.
        out.append(d)
    return out


async def _fields_only_rows(conn, tenant_id) -> list[dict]:
    """احتياطيّ: الحقول وحدها (إن غاب جدول دليل) — كلّها ستُصنَّف needs_data بصدق."""
    rows = await conn.fetch(
        f"SELECT field_id, name, crop, gov, lat, lon FROM fields WHERE tenant_id=$1::uuid ORDER BY field_id LIMIT {_MAX_FIELDS}",
        tenant_id,
    )
    return [dict(r) for r in rows]


def _apply_owner_counts(fields: list[dict], response: dict, tenant_id: str) -> None:
    """Pure: copy decision-service field counts onto ``fields``, or raise 502.

    The owner must answer authoritatively, for this tenant, for exactly these fields, with
    non-negative integer counts where successes never exceed outcomes. Anything else is an
    owner failure, never an empty or verified field.
    """
    ids = [row["field_id"] for row in fields]
    counts = response.get("counts")
    if (
        response.get("authoritative") is not True
        or response.get("tenant_id") != tenant_id
        or not isinstance(counts, dict)
        or set(counts) != set(ids)
    ):
        raise HTTPException(502, "incomplete or mismatched field evidence")
    for row in fields:
        values = counts[row["field_id"]]
        if (
            not isinstance(values, dict)
            or any(
                type(values.get(k)) is not int or values[k] < 0
                for k in ("decisions", "outcomes", "successes")
            )
            or values["successes"] > values["outcomes"]
        ):
            raise HTTPException(502, "invalid field evidence counts")
        for key in ("decisions", "outcomes", "successes", "last_outcome_at"):
            row[key] = values.get(key)


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
    tenant_id = str(user.tenant_id)
    remote = get_platform_decision_sor_mode().strict_decision_service_required
    try:
        async with tenant_connection(user) as conn:
            if remote:
                fields = await _fields_only_rows(conn, tenant_id)
            else:
                try:
                    async with conn.transaction():
                        fields = await _field_evidence_rows(conn, tenant_id)
                except Exception as exc:
                    if getattr(exc, "sqlstate", None) not in {"42P01", "42703"}:
                        raise
                    fields = await _fields_only_rows(conn, tenant_id)
    except Exception as e:
        raise _db_unavailable("خريطة الدليل", e) from e

    if remote and fields:
        ids = [row["field_id"] for row in fields]
        response = await decision_post_json(
            "/v1/evidence/field-counts", {"field_ids": ids}, tenant_id=tenant_id
        )
        _apply_owner_counts(fields, response, tenant_id)

    out = shape_evidence_map(fields, generated_at=datetime.now(UTC).isoformat())
    out["provenance"]["decision_source"] = "decision-service" if remote else "sahool-platform"
    out["tenant_id"] = str(user.tenant_id)  # أثر: لِمن هذه الخريطة (RLS)
    return out
