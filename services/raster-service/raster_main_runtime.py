"""Runtime compatibility façade for raster-service main.py.

This module keeps legacy private symbols that older tests and a few staged
runtime adapters still access via ``main._*`` while keeping the application
entrypoint focused on bootstrap only.
"""

from __future__ import annotations

import logging
import os

import layer_cache_events
import object_store
import raster_app_lifecycle
import raster_runtime_state
import raster_security_context
import raster_settings
from fastapi import Header

# Shared mutable runtime registries.
_jobs = raster_runtime_state.JOBS
_layers = raster_runtime_state.LAYERS
_field_layers = raster_runtime_state.FIELD_LAYERS

# Tenant/security compatibility symbols.
_REQ_TENANT = raster_security_context.REQ_TENANT
_field_owner = raster_security_context.field_owner
_field_owner_cache = raster_security_context._field_owner_cache
_public_cog_url = raster_security_context.public_cog_url

# Service/runtime directories and constants.
UPLOAD_DIR = raster_settings.UPLOAD_DIR
AGENT_TOKEN = raster_settings.AGENT_TOKEN
OFFLINE_PACKS_DIR = raster_settings.OFFLINE_PACKS_DIR
_LAYER_EVICT_CHANNEL = layer_cache_events.DEFAULT_LAYER_EVICT_CHANNEL

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OFFLINE_PACKS_DIR, exist_ok=True)


def _layer_evict_enabled() -> bool:
    return layer_cache_events.layer_evict_enabled()


def _evict_field_layers(field_id: str, *, logger: logging.Logger | None = None) -> int:
    return layer_cache_events.evict_field_layers(
        field_id,
        layers=_layers,
        field_layers=_field_layers,
        logger=logger,
    )


async def _layer_evict_subscriber(*, logger: logging.Logger | None = None) -> None:
    return await layer_cache_events.layer_evict_subscriber(
        layers=_layers,
        field_layers=_field_layers,
        logger=logger,
        redis_url=os.getenv("REDIS_URL"),
        channel=_LAYER_EVICT_CHANNEL,
    )


def make_raster_lifespan(*, logger: logging.Logger):
    async def subscriber() -> None:
        await _layer_evict_subscriber(logger=logger)

    return raster_app_lifecycle.make_lifespan(
        logger=logger,
        object_store_module=object_store,
        database_url_getter=lambda: os.getenv("DATABASE_URL", ""),
        layer_evict_enabled=_layer_evict_enabled,
        layer_evict_subscriber=subscriber,
    )


async def _require_field_tenant(field_id: str, *, hide_existence: bool = False) -> None:
    return await raster_security_context.require_field_tenant(
        field_id,
        hide_existence=hide_existence,
        layers=_layers,
        field_layers=_field_layers,
        logger=logging.getLogger("raster-service"),
        owner_lookup=_field_owner,
    )


def _require_layer_tenant(layer_id: str) -> None:
    return raster_security_context.require_layer_tenant(layer_id, layers=_layers)


async def _require_layer_tenant_authorized(layer_id: str) -> None:
    return await raster_security_context.require_layer_tenant_authorized(
        layer_id,
        layers=_layers,
        logger=logging.getLogger("raster-service"),
    )


def _require_service_token(x_agent_token: str = Header(None)) -> None:
    return raster_security_context.require_service_token(x_agent_token, AGENT_TOKEN)


__all__ = [
    "object_store",
    "_jobs",
    "_layers",
    "_field_layers",
    "_REQ_TENANT",
    "_field_owner",
    "_field_owner_cache",
    "_public_cog_url",
    "UPLOAD_DIR",
    "AGENT_TOKEN",
    "OFFLINE_PACKS_DIR",
    "_LAYER_EVICT_CHANNEL",
    "_layer_evict_enabled",
    "_evict_field_layers",
    "_layer_evict_subscriber",
    "make_raster_lifespan",
    "_require_field_tenant",
    "_require_layer_tenant",
    "_require_layer_tenant_authorized",
    "_require_service_token",
]
