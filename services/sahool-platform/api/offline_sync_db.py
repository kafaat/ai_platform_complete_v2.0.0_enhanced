"""offline_sync_db — كتابة DB فعليّة لعمليّات offline-first المُزامَنة.

النواة ‎sahool_core.offline_first‎ نقيّة (لا I/O بالتصميم)، فهذا الملف يعزل
الكتابة الفعليّة للقاعدة خلف دالّتين قابلتين للاختبار:

  • persist_synced_operation — يُدخِل عمليّة (idempotent على op_id) ضمن سياق
    RLS الذي يضبطه المستدعي (tenant_connection). إعادة الـsync لا تُكرّر الصفّ.
  • fetch_synced_operations — يقرأ عمليّات المستأجر (مُرشَّحة تلقائيّاً بـRLS).

كلاهما يعمل على conn جاهز (من tenant_connection)، فلا يفتح pool بنفسه —
يبقى الاختبار والاستخدام بسيطين وسياق المستأجر مضموناً من المستدعي.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - نوعيّ فقط
    import asyncpg
    from core.offline_first import PendingOperation


def _parse_ts(value: object) -> datetime | None:
    """يحوّل ISO string إلى datetime لعمود timestamptz (يتسامح مع القيم التالفة)."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


async def persist_synced_operation(
    conn: asyncpg.Connection, *, op: PendingOperation, tenant_id: str
) -> bool:
    """يكتب عمليّة مُزامَنة في offline_synced_operations (idempotent على op_id).

    يجب أن يكون ``conn`` ضمن سياق المستأجر (tenant_connection) ليُطبَّق RLS.
    يرفع استثناء عند خطأ قاعدة فعلي (يُترك للمستدعي ليُبقي العمليّة في الـqueue).

    Returns
    -------
    bool
        True إن كُتبت أو كانت موجودة سلفاً (ON CONFLICT DO NOTHING).
    """
    await conn.execute(
        """
        INSERT INTO offline_synced_operations
            (op_id, tenant_id, user_id, kind, payload, created_at, synced_at)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb, $6, NOW())
        ON CONFLICT (op_id) DO NOTHING
        """,
        op.op_id,
        tenant_id,
        str(op.user_id),
        op.kind.value if hasattr(op.kind, "value") else str(op.kind),
        json.dumps(op.payload or {}),
        _parse_ts(op.created_at),
    )
    return True


async def fetch_synced_operations(conn: asyncpg.Connection, limit: int = 100) -> list[dict]:
    """يقرأ عمليّات المستأجر الحالي (RLS يُرشّح حسب app.current_tenant)."""
    rows = await conn.fetch(
        """
        SELECT op_id, tenant_id, user_id, kind, payload, created_at, synced_at
        FROM offline_synced_operations
        ORDER BY synced_at DESC
        LIMIT $1
        """,
        limit,
    )
    out: list[dict] = []
    for r in rows:
        payload = r["payload"]
        out.append(
            {
                "op_id": str(r["op_id"]),
                "tenant_id": str(r["tenant_id"]),
                "user_id": r["user_id"],
                "kind": r["kind"],
                "payload": payload if isinstance(payload, dict) else json.loads(payload),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "synced_at": r["synced_at"].isoformat() if r["synced_at"] else None,
            }
        )
    return out
