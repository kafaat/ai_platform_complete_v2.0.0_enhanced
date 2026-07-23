"""baseline — وسم الهجرات اليدويّة الـ20 الحاليّة كمُطبَّقة

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-08

هذه نقطة الأساس (baseline). مشروع SAHOOL بدأ بـ20 هجرة SQL يدويّة
(migrations/*.sql) طُبِّقت قبل اعتماد Alembic. هذه المراجعة **لا تُنشئ شيئاً**
— هي علامة تقول "كلّ ما قبل Alembic مُطبَّق". الهجرات الجديدة تأتي بعدها.

الاستخدام (مرّة واحدة على قاعدة موجودة):
  alembic stamp 0001_baseline

ثمّ الهجرات المستقبليّة:
  alembic revision -m "add irrigation_log table"
  alembic upgrade head

⚠ لا تُشغّل upgrade على هذه المراجعة على قاعدة جديدة فارغة — طبّق أوّلاً
الهجرات اليدويّة (migrations/*.sql بالترتيب) ثمّ stamp، أو حوّلها لمراجعات
Alembic لاحقاً. هذا baseline للقواعد القائمة.
"""

import sqlalchemy as sa  # noqa: F401

from alembic import op  # noqa: F401

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# سجلّ الهجرات اليدويّة التي يمثّلها هذا الـbaseline (توثيق)
MANUAL_MIGRATIONS = [
    "init_v8.sql",
    "v9_foundation.sql",
    "v9_new_tables.sql",
    "v9_auth_improvements.sql",
    "v9_append_only_enforcement.sql",
    "v9_rls_tenant_isolation.sql",
    "v9_automation.sql",
    "v9_automation_persistence.sql",
    "v9_edge_idempotency.sql",
    "v9_edge_occurred_at.sql",
    "v9_lifecycle_occurred_at.sql",
    "v9_market.sql",
    "v9_odoo_bridge.sql",
    "v9_onboarding.sql",
    "v10_command_store_lifecycle.sql",
    "v11_events_bus.sql",
    "v12_trueup_sharing.sql",
    "v13_geospatial_core.sql",
]


def upgrade() -> None:
    # baseline لا يُنشئ شيئاً — الهجرات اليدويّة طُبِّقت قبل Alembic.
    # (لو احتجتَ إعادة بناء قاعدة من الصفر، طبّق migrations/*.sql يدويّاً أوّلاً.)
    pass


def downgrade() -> None:
    # لا تراجع عن baseline (سيعني حذف كلّ المخطّط — خطير).
    pass
