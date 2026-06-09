"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

ملاحظة: مشروع SAHOOL يستخدم SQL خام. اكتب الهجرة بـop.execute("""SQL""").
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# معرّفات Alembic
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    # مثال: op.execute("ALTER TABLE soil_readings ADD COLUMN ...")
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    # تراجع: op.execute("ALTER TABLE soil_readings DROP COLUMN ...")
    ${downgrades if downgrades else "pass"}
