"""Redis-driven in-memory layer eviction helpers for raster-service.

The invalidation worker can clear disk/DB state, but it cannot directly touch the
raster-service process memory.  This module subscribes to a Redis channel and
removes in-memory layers for a changed field.  All operations are best-effort so
Redis outages never drop the service.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

DEFAULT_LAYER_EVICT_CHANNEL = os.getenv("RASTER_LAYER_EVICT_CHANNEL", "raster:layer_evict")


def layer_evict_enabled() -> bool:
    return str(os.getenv("RASTER_LAYER_EVICT_ENABLED", "true")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def evict_field_layers(
    field_id: str,
    *,
    layers: dict[str, dict],
    field_layers: dict[str, list[str]],
    logger: Any,
) -> int:
    """Remove all in-memory layers for a field and return removed count."""
    if not field_id:
        return 0
    lids = field_layers.pop(field_id, [])
    for lid in lids:
        layers.pop(lid, None)
    if lids:
        logger.info(
            "evicted %d in-memory layer(s) for field %s (cache invalidation)",
            len(lids),
            field_id,
        )
    return len(lids)


async def layer_evict_subscriber(
    *,
    layers: dict[str, dict],
    field_layers: dict[str, list[str]],
    logger: Any,
    redis_url: str | None = None,
    channel: str = DEFAULT_LAYER_EVICT_CHANNEL,
) -> None:
    """Subscribe to Redis layer-eviction messages.

    Best-effort: missing Redis/client package or connection interruptions are
    logged and retried; they must not prevent raster-service startup.
    """
    url = redis_url or os.getenv("REDIS_URL")
    if not url:
        logger.info("layer-evict subscriber معطَّل (لا REDIS_URL)")
        return
    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.info("layer-evict subscriber معطَّل (حزمة redis.asyncio غائبة)")
        return
    while True:
        try:
            client = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(channel)
            logger.info("layer-evict subscriber مشترِك في %s", channel)
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                evict_field_layers(
                    str(message.get("data") or "").strip(),
                    layers=layers,
                    field_layers=field_layers,
                    logger=logger,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — Redis outage must not drop service
            logger.warning("layer-evict subscriber انقطع (إعادة محاولة خلال 5s): %s", exc)
            await asyncio.sleep(5)
