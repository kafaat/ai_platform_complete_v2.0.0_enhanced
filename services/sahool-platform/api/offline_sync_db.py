"""offline_sync_db — كتابة DB فعليّة لعمليّات offline-first المُزامَنة.

النواة ‎sahool_core.offline_first‎ نقيّة (لا I/O بالتصميم)، فهذا الملف يعزل
الكتابة الفعليّة للقاعدة خلف دوالّ قابلة للاختبار:

  • persist_synced_operation — يُدخِل عمليّة في السجلّ (ledger) idempotent على op_id
    ضمن سياق RLS الذي يضبطه المستدعي (tenant_connection). إعادة الـsync لا تُكرّر الصفّ.
  • fetch_synced_operations — يقرأ عمليّات المستأجر (مُرشَّحة تلقائيّاً بـRLS).
  • apply_field_update — توزيع (dispatch) شريحة ``field.update`` فقط: تُطبَّق فعليّاً
    على صفّ ``fields`` عبر مسار التحديث المُؤصدَر (``_build_versioned_update`` المُعاد
    استخدامه من ``api.main``) بسلطة الخادم. ``base_version`` قديم ⇒ **409 تعارض** (لا
    كتابة فوقيّة صامتة)؛ النجاح ⇒ ``applied``.

التوزيع بسلطة الخادم (server-authoritative):
  • ``field.update`` وحده يُطبَّق فعليّاً (يغيّر الحالة المرجعيّة في ``fields``). اصطدام
    الإصدار (row_version) ⇒ تُصيب الكتابة 0 صفّ ⇒ نُصنّفها ``conflict`` (409) ونتركها
    للعميل ليحسم — لا فقد صامت.
  • كلّ الأنواع الأخرى تبقى **سجلّ فقط** (ledger-only): تُدوَّن في
    ``offline_synced_operations`` بـ``ON CONFLICT (op_id) DO NOTHING`` (idempotency)، بلا
    تطبيق على جدول نطاقيّ هنا (مساراتها النطاقيّة الخاصّة تتكفّل بذلك). هذا يحافظ على
    العقد القائم بايتاً ببايت.

كلّها تعمل على conn جاهز (من tenant_connection)، فلا تفتح pool بنفسها —
يبقى الاختبار والاستخدام بسيطين وسياق المستأجر مضموناً من المستدعي.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from api.field_models import _FIELD_ADVANCED_COLUMNS, _FIELD_BASIC_COLUMNS

if TYPE_CHECKING:  # pragma: no cover - نوعيّ فقط
    import asyncpg
    from core.offline_first import PendingOperation


# نوع العمليّة الوحيد المُطبَّق فعليّاً (dispatch) بدل تدوينه في السجلّ فقط. سلسلة
# منقّطة كما يُرسلها العميل offline (لا قيمة في OperationKind — التوزيع يُطابَق نصّاً).
FIELD_UPDATE_KIND = "field.update"

# الأعمدة المسموح تحديثها عبر شريحة field.update — مصدر واحد مشترك مع PATCH /fields
# (_FIELD_BASIC_COLUMNS + _FIELD_ADVANCED_COLUMNS) فلا تتباعد قائمتا الأعمدة. أيّ مفتاح
# في الحمولة خارج هذه المجموعة يُتجاهَل (لا حقن أعمدة عشوائيّة من حمولة العميل).
_FIELD_UPDATE_ALLOWED_COLUMNS: frozenset[str] = frozenset(
    (*_FIELD_BASIC_COLUMNS, *_FIELD_ADVANCED_COLUMNS)
)


def dispatch_decision(kind: object) -> str:
    """يقرّر مسار التوزيع لعمليّة مُزامَنة — دالّة نقيّة (لا I/O، قابلة للاختبار offline).

    يُرجِع:
      • ``"apply"``  لشريحة ``field.update`` (تُطبَّق فعليّاً بسلطة الخادم).
      • ``"ledger"`` لكلّ نوع آخر (سجلّ فقط، idempotent — لا تطبيق نطاقيّ هنا).

    يقبل ``kind`` كسلسلة أو عضو enum (يقرأ ``.value`` إن وُجد) فيطابق ما يُرسله العميل.
    """
    value = kind.value if hasattr(kind, "value") else str(kind)
    return "apply" if value == FIELD_UPDATE_KIND else "ledger"


def _field_update_set_clause(payload: dict | None) -> tuple[str, list]:
    """يبني (set_clause, values) من حمولة ``field.update`` — دالّة نقيّة (لا DB).

    يقبل فقط الأعمدة ضمن ``_FIELD_UPDATE_ALLOWED_COLUMNS`` (allowlist صارمة) فلا تُحقَن
    أعمدة عشوائيّة من حمولة العميل، والقيم تُمرَّر كبارامترات ($1, $2 …) لا تُدخَل في
    نصّ الـSQL (لا string-formatting لمدخلات غير موثوقة). يرفع ``ValueError`` إن لم يبقَ
    عمود صالح (لا UPDATE فارغ).
    """
    data = payload or {}
    assignments: list[str] = []
    values: list = []
    idx = 1
    # ترتيب ثابت (حسب تعريف الأعمدة) ⇒ SQL حتميّ قابل للاختبار.
    for col in (*_FIELD_BASIC_COLUMNS, *_FIELD_ADVANCED_COLUMNS):
        if col in data and col in _FIELD_UPDATE_ALLOWED_COLUMNS:
            assignments.append(f"{col} = ${idx}")
            values.append(data[col])
            idx += 1
    if not assignments:
        raise ValueError("no field columns to update")
    return ", ".join(assignments), values


def _parse_ts(value: object) -> datetime:
    """يحوّل ISO string إلى datetime واعٍ بـUTC لعمود timestamptz (NOT NULL).

    offline_first يُنتج created_at عبر datetime.utcnow().isoformat() (naive)؛
    نعتبره UTC صراحةً (وإلّا فسّره الخادم بتوقيته المحلّي ⇒ انزياح زمني). ندعم
    اللاحقة 'Z'، ونرجع الآن (UTC) كقيمة آمنة بدل None حتّى لا يفشل الإدراج بسبب
    فرق تنسيق طفيف.
    """
    dt: datetime | None = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            dt = None
    if dt is None:
        dt = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


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


async def apply_field_update(
    conn: asyncpg.Connection, *, op: PendingOperation, tenant_id: str
) -> str:
    """يطبّق شريحة ``field.update`` فعليّاً على صفّ ``fields`` بسلطة الخادم.

    يقرأ من ``op.payload``: ``field_id`` (إلزاميّ) + الأعمدة المسموحة + ``base_version``
    (اختياريّ — حارس التزامن التفاؤليّ). يُعيد استخدام ``_build_versioned_update`` من
    ``api.main`` (استيراد متأخّر لتفادي الاستيراد الدائريّ) فيرفع ``row_version`` دائماً
    ويضيف ``AND row_version = base_version`` إن مُرِّر.

    Returns
    -------
    str
        • ``"applied"``  — أصابت الكتابة صفّاً (طُبِّق التحديث ورُفِع الإصدار).
        • ``"conflict"`` — مُرِّر ``base_version`` لكنّ الكتابة أصابت 0 صفّ ⇒ الإصدار
          القديم لا يطابق الحاليّ ⇒ **409** (سلطة الخادم، لا كتابة فوقيّة صامتة).

    يرفع ``ValueError`` إن غاب ``field_id`` أو لم تبقَ أعمدة صالحة للتحديث (حمولة فاسدة
    — يُترك للمستدعي ليُبقي العمليّة في الـqueue لا أن يُعلن نجاحاً زائفاً).
    """
    payload = op.payload or {}
    field_id = payload.get("field_id")
    if not field_id:
        raise ValueError("field.update payload missing field_id")

    base_version = payload.get("base_version")
    set_clause, values = _field_update_set_clause(payload)

    # استيراد متأخّر: _build_versioned_update يعيش في api.main (مساعِد التزامن التفاؤليّ
    # المشترك مع PATCH /fields والمواسم). تأخيره يكسر دورة الاستيراد (main يستورد
    # الموجِّهات في نهايته). نقيّ — يبني (sql, exec_values) فقط، لا I/O.
    from api.main import _build_versioned_update

    sql, exec_values = _build_versioned_update(set_clause, values, str(field_id), base_version)
    status_tag = await conn.execute(sql, *exec_values)

    # asyncpg يُرجِع وسماً مثل "UPDATE 1" (صفّ واحد) أو "UPDATE 0" (لا تطابق). مع
    # base_version مُمرَّر، 0 صفّ ⇒ الإصدار القديم لا يطابق ⇒ تعارض (409). بلا
    # base_version لا حارس إصدار، فـ0 صفّ يعني الحقل غير موجود لهذا المستأجِر (RLS) —
    # نتركه applied=False ⇒ conflict أيضاً (لا نخترع نجاحاً لصفّ لم يُمسّ).
    rows_affected = status_tag.rsplit(" ", 1)[-1] if status_tag else "0"
    return "applied" if rows_affected != "0" else "conflict"


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
