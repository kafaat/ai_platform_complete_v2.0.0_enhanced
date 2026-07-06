"""Application lifespan wiring for raster-service.

This keeps main.py as a small FastAPI facade while preserving the exact startup
semantics: configure object storage, enforce RLS-safe DB role, start optional
layer-eviction subscriber, and cancel it gracefully on shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any


def make_lifespan(
    *,
    logger: Any,
    object_store_module: Any,
    database_url_getter: Callable[[], str],
    layer_evict_enabled: Callable[[], bool],
    layer_evict_subscriber: Callable[[], Awaitable[None]],
):
    """Build the FastAPI lifespan context manager for raster-service."""

    @asynccontextmanager
    async def lifespan(app):
        logger.info("raster-service starting (Element84 Earth Search)")
        object_store_module.gdal_configure()
        from shared.db_role_guard import assert_dsn_role_rls_safe

        await assert_dsn_role_rls_safe(database_url_getter(), service="raster-service")
        evict_task = None
        if layer_evict_enabled():
            evict_task = asyncio.create_task(layer_evict_subscriber())
        try:
            yield
        finally:
            if evict_task is not None:
                evict_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await evict_task
            logger.info("raster-service stopping")

    return lifespan
