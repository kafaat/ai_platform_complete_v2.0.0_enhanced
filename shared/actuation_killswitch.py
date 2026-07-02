"""shared/actuation_killswitch.py — استشارة مفتاح إيقاف طوارئ التشغيل (fail-closed).

سطر v29.5-op-1. مصدر البيانات: جدول ``actuation_killswitch`` (migrations/v133) —
صفّ لكلّ مفتاح إيقاف مُشتبَك بنطاق (tenant/field/valve). يُستشار على المسار الساخن
**قبل** أيّ تنفيذ فيزيائيّ (``send_mqtt_command`` في actuator-service، إدراج طابور
التوزيع في decision_dispatch).

قاعدة المطابقة (نيّة إيقاف صريحة — لا اختراع):
  • ``tenant`` — يوقف كلّ تشغيل هذا المستأجِر (يُطابق أيّ استشارة).
  • ``field``  — يوقف الحقل المُحدَّد فقط (يُطابق إن كان ``field_id`` المُستشار = مفتاح الحقل).
  • ``valve``  — يوقف الصمّام المُحدَّد فقط (يُطابق إن كان ``valve_id`` المُستشار = مفتاح الصمّام).
تُهمَل المفاتيح غير الفعّالة (``active=false``) والمنتهية (``expires_at <= now``).

**fail-closed**: تعذّر القاعدة (لا اتّصال/خطأ استعلام) ⇒ يُعتبَر التشغيل **مُوقَفاً**
(``halted=True``) — تماثُلاً مع idiom actuator-service (``_authorize_device_control``:
تعذّر التحقّق ⇒ رفض). لا نُشغّل الجهاز ونحن عاجزون عن التأكّد من عدم وجود إيقاف طوارئ.

الدالّة النقيّة ``match_killswitch`` قابلة للاختبار وحدةً (بلا قاعدة)؛ والغلاف اللاتزامنيّ
``is_actuation_halted`` يستعلم القاعدة (مع ضبط سياق المستأجِر لتفعيل RLS) ثمّ يُفوّضها.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

# سبب افتراضيّ عند تعذّر القاعدة (fail-closed) — لا إيقاف صامت بلا نصّ مفهوم.
FAIL_CLOSED_REASON = "تعذّر التحقّق من مفتاح إيقاف الطوارئ — التشغيل مُوقَف بأمان (fail-closed)"


def match_killswitch(
    switches: Iterable[Mapping[str, Any]],
    *,
    field_id: str | None = None,
    valve_id: str | None = None,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    """منطق المطابقة النقيّ: هل يوقف أيّ مفتاح من ``switches`` هذه الاستشارة؟

    كلّ عنصر Mapping له المفاتيح: ``scope`` · ``field_id`` · ``valve_id`` · ``active``
    · ``reason`` · ``expires_at`` (aware أو None). يُعيد ``(halted, reason)`` — سبب أوّل
    مفتاح مُطابِق، أو ``(False, None)`` إن لم يُطابق شيء. لا يمسّ القاعدة (اختبار وحدة).
    """
    now = now or datetime.now(UTC)
    for sw in switches:
        if not sw.get("active", True):
            continue
        expires_at = sw.get("expires_at")
        if expires_at is not None and expires_at <= now:
            continue  # منتهٍ ⇒ لا يوقف
        scope = sw.get("scope")
        if scope == "tenant":
            return True, sw.get("reason")
        if scope == "field" and field_id is not None and sw.get("field_id") == field_id:
            return True, sw.get("reason")
        if scope == "valve" and valve_id is not None and sw.get("valve_id") == valve_id:
            return True, sw.get("reason")
    return False, None


async def is_actuation_halted(
    conn: Any,
    tenant_id: str,
    field_id: str | None = None,
    valve_id: str | None = None,
) -> tuple[bool, str | None]:
    """يستشير القاعدة: هل التشغيل مُوقَف لهذا (المستأجِر، الحقل، الصمّام)؟ (fail-closed).

    يضبط ``app.current_tenant`` ضمن معاملة (SET LOCAL) لتفعيل RLS ثمّ يقرأ المفاتيح
    الفعّالة غير المنتهية ويُفوّض ``match_killswitch``. أيّ استثناء (لا اتّصال/خطأ) ⇒
    ``(True, FAIL_CLOSED_REASON)`` — لا تشغيل بلا تأكّد من غياب إيقاف الطوارئ.

    ``conn``: اتّصال asyncpg (قد يكون داخل معاملة مستأجِر قائمة — نفتح savepoint آمناً).
    """
    try:
        async with conn.transaction():
            # SET LOCAL app.current_tenant — يُفعّل RLS (FORCE) كي تُرى صفوف المستأجِر.
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))
            rows = await conn.fetch(
                """SELECT scope, field_id, valve_id, active, reason, expires_at
                   FROM actuation_killswitch
                   WHERE active = TRUE
                     AND tenant_id = $1::uuid
                     AND (expires_at IS NULL OR expires_at > now())""",
                str(tenant_id),
            )
    except Exception:  # noqa: BLE001 — fail-closed: تعذّر التأكّد ⇒ يُعتبَر مُوقَفاً
        return True, FAIL_CLOSED_REASON
    return match_killswitch(rows, field_id=field_id, valve_id=valve_id)
