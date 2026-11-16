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
        from follow_up_runtime import configured_tenants, process, startup_check, store
        from follow_up_worker import serve

        tenants = configured_tenants()
        await startup_check(tenants)
        follow_up_task = asyncio.create_task(serve(tenants, store, process)) if tenants else None
        app.state.follow_up_ready = bool(tenants)
        # W1-11: the reconciliation sweep of published assets with no outbox row (same explicit
        # tenant-partition rule as the follow-up worker; idles and says why otherwise).
        import observation_sweep

        sweep_reason = observation_sweep.skip_reason()
        observation_sweep._STATE["last_skip_reason"] = sweep_reason
        sweep_task = (
            asyncio.create_task(observation_sweep.serve()) if sweep_reason is None else None
        )
        if sweep_reason is not None:
            logger.warning("observation reconciliation sweep not started: %s", sweep_reason)
        evict_task = None
        if layer_evict_enabled():
            evict_task = asyncio.create_task(layer_evict_subscriber())
        try:
            yield
        finally:
            app.state.follow_up_ready = False
            if follow_up_task is not None:
                follow_up_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await follow_up_task
            if sweep_task is not None:
                sweep_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await sweep_task
            if evict_task is not None:
                evict_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await evict_task
            logger.info("raster-service stopping")

    return lifespan
