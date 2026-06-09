"""
SAHOOL v9.1.0 — agents/base_agent.py
Base class for all SAHOOL agents.
"""
from __future__ import annotations
import asyncio
import logging
import os
from typing import Optional
import asyncpg

logger = logging.getLogger(__name__)

class BaseAgent:
    """Base agent: DB pool, NATS connection, graceful shutdown."""

    def __init__(self, service_name: str):
        self.service_name  = service_name
        self._pool: Optional[asyncpg.Pool] = None
        self._nc   = None
        self._js   = None

    async def init_db(self):
        dsn = os.getenv("DATABASE_URL", "")
        if dsn:
            self._pool = await asyncpg.create_pool(
                dsn, min_size=1, max_size=5,
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

    async def set_tenant(self, conn, tenant_id: str):
        """Set RLS tenant context for DB operations."""
        await conn.execute(
            "SELECT set_config('app.current_tenant', $1, true)",
            str(tenant_id) if tenant_id else ""
        )

    async def close(self):
        if self._pool:
            await self._pool.close()
        if self._nc:
            await self._nc.close()
        logger.info(f"[{self.service_name}] Shutdown complete")
