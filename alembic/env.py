"""alembic/env.py — بيئة تشغيل Alembic لـSAHOOL.

يقرأ DATABASE_URL من متغيّر البيئة (لا كلمة سرّ في الملفّات).
يعمل بنمط SQL خام (لا ORM) — متّسق مع هجرات المشروع الحاليّة.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context

# إعداد التسجيل من alembic.ini
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# اقرأ رابط القاعدة من البيئة (آمن — لا سرّ في الكود)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    os.getenv("ALEMBIC_DATABASE_URL", ""),
)
if not DATABASE_URL:
    sys.stderr.write(
        "\n⚠ DATABASE_URL غير مضبوط. اضبطه قبل تشغيل alembic:\n"
        "  export DATABASE_URL='postgresql://user:pass@host:5432/sahool'\n\n"
    )

config.set_main_option("sqlalchemy.url", DATABASE_URL)

# لا ORM metadata (هجرات SQL خام) — Alembic لا يولّد تلقائيّاً، نكتب يدويّاً.
target_metadata = None


def run_migrations_offline() -> None:
    """وضع offline: يولّد SQL دون اتّصال (للمراجعة)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """وضع online: يتّصل بالقاعدة ويطبّق الهجرات."""
    from sqlalchemy import engine_from_config, pool

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
