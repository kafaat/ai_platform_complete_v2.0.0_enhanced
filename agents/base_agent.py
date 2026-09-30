"""
SAHOOL v9.1.0 — agents/base_agent.py
Base class for all SAHOOL agents.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import asyncpg

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base agent: DB pool, NATS connection, graceful shutdown."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self._pool: asyncpg.Pool | None = None
        self._nc = None
        self._js = None

    async def init_db(self):
        dsn = os.getenv("DATABASE_URL", "")
        if dsn:
            self._pool = await asyncpg.create_pool(
                dsn,
                min_size=1,
                max_size=5,
                server_settings={"statement_cache_size": "0"},
            )
            logger.info(f"[{self.service_name}] DB pool ready")

    async def init_nats(self):
        try:
            import nats

            nats_url = os.getenv("NATS_URL", "nats://sahool-nats:4222")
            self._nc = await nats.connect(nats_url)
            self._js = self._nc.jetstream()
            logger.info(f"[{self.service_name}] NATS connected")
        except Exception as e:
            logger.warning(f"[{self.service_name}] NATS unavailable: {e}")

    @asynccontextmanager
    async def tenant_transaction(self, conn, tenant_id: str):
        """معاملةٌ يحيا فيها سياقُ المستأجِر — **والسياقُ لا يُضبَط إلّا داخلها**.

        كانت هنا ``set_tenant(conn, tenant_id)`` تنفّذ ``set_config(…, true)`` على الاتّصال
        كما هو. و``true`` «محلّيٌّ للمعاملة»، وasyncpg بلا معاملةٍ صريحة في وضع autocommit:
        العبارةُ معاملةُ نفسِها فيزول الضبطُ قبل الاستعلام التالي. **مقيسٌ على PG16 بدورٍ
        مقيَّد (NOBYPASSRLS):** ``set_config`` يُعيد القيمةَ كأنّه نجح، والعبارةُ التالية
        تقرأ ``current_setting('app.current_tenant', true) = ''`` فتُعيد السياسةُ صفرَ صفوف
        بلا استثناء — ضبطٌ لا يضبط شيئاً. (ولم يكن لها مُستدعٍ واحد؛ فهي فخٌّ كامن لا عطلٌ
        جارٍ.) والصيغةُ الآمنة الوحيدة أن يملك المُساعِدُ المعاملةَ نفسَها، على نمط
        ``tenant_connection`` في المنصّة: فلا يمكن استعمالُه خارجها أصلاً.

        ومستأجِرٌ فارغ يُرفَض بدل ضبطه ``''``: الفراغُ في سياسات ``NULLIF`` صفرٌ صامت،
        وفي سياسات «فاشلٍ-مفتوحٍ عند الغياب» قراءةٌ عابرةٌ للمستأجرين.
        """
        if not tenant_id:
            raise ValueError("tenant_transaction يتطلّب مستأجِراً غير فارغ")
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(tenant_id))
            yield conn

    async def close(self):
        if self._pool:
            await self._pool.close()
        if self._nc:
            await self._nc.close()
        logger.info(f"[{self.service_name}] Shutdown complete")
