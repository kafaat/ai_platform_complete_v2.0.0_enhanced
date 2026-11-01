"""سرد المستأجرين لمسوح المُجدوِل الدوريّة (التنبيهات/النضارة) — عبر مسبح المهامّ.

العطل (R1): المسحان كانا يسردان ``SELECT DISTINCT tenant_id FROM fields`` على مسبح
التطبيق (``sahool_app``، NOBYPASSRLS) **بلا سياق مستأجِر**. وسياسة ``tenant_isolation``
على ``fields`` (FORCE، ``migrations/v9_rls_tenant_isolation.sql``) فاشلةٌ-مغلقة: سياقٌ
فارغ ⇒ صفر صفوف ⇒ لا مستأجِر ⇒ لا تنبيه يُقيَّم أبداً، بصمت.

الآليّة القائمة لا الجديدة: مسبح المهامّ (``sahool_jobs``، BYPASSRLS، يُمنح SELECT على
كلّ الجداول في ``migrations/apply_in_compose.sh``) — نفسُ ما يستعمله مجدوِل الطقس
والصور والمرسِل. يُقرأ منه **المعرّف وحده**؛ قراءة الحقول نفسها تبقى بسياق المستأجِر
(``tenant_connection``، RLS) في المُستدعي.

وإن عاد المسبح إلى دورٍ مُقيَّد (لا ``JOBS_DATABASE_URL``) فالصفر لا يُقرأ «لا مستأجرين»:
يُقاس الدور كما في ``imagery_automation.bind_recovery_pool`` (مراجعة #1009) ويُعلَن حرجاً.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TENANTS_WITH_FIELDS_SQL = "SELECT DISTINCT tenant_id FROM fields WHERE tenant_id IS NOT NULL"


async def list_sweep_tenant_ids(pool, *, sweep: str) -> list[str]:
    """يُرجِع معرّفات المستأجرين ذوي الحقول عبر ``pool`` (مسبح المهامّ عابر المستأجرين).

    ``pool=None`` ⇒ قائمة فارغة. أخطاء الاتّصال/الاستعلام تُرفَع للمُستدعي (يتخطّى التكّة).
    صفرُ صفوفٍ تحت دورٍ مُقيَّد يُعلَن بمستوى حرج بدل أن يمرّ صمتاً.
    """
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(TENANTS_WITH_FIELDS_SQL)
        if not rows:
            await _declare_restricted_role_zero(conn, sweep)
    return [str(r["tenant_id"]) for r in rows]


async def _declare_restricted_role_zero(conn, sweep: str) -> None:
    from core.db_role_guard import ROLE_PROBE_SQL, role_can_bypass_rls

    try:
        row = await conn.fetchrow(ROLE_PROBE_SQL)
    except Exception as e:  # noqa: BLE001 — تعذّر القياس ⇒ لا حكم (كحارس الدور)
        logger.debug("%s: تعذّر فحص دور مسبح السرد: %s", sweep, type(e).__name__)
        return
    if row is None or role_can_bypass_rls(row["rolsuper"], row["rolbypassrls"]):
        return  # دورٌ عابر: الصفرُ حقيقيّ (لا حقول بعد)
    logger.critical(
        "🔓 %s: سرد المستأجرين أعاد صفراً بدورٍ مُقيَّد (NOBYPASSRLS) و`fields` تحت FORCE RLS "
        "⇒ لا شيء يُقيَّم. اضبط JOBS_DATABASE_URL على دور المهامّ (sahool_jobs).",
        sweep,
    )
