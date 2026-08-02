"""SAHOOL raster-service ASGI entrypoint.

The raster logic, routers, runtime registries, STAC configuration, app factory,
security wrappers, and legacy compatibility exports live in focused modules.
This file intentionally remains a thin ``main:app`` bootstrap for deployment.
"""

from __future__ import annotations

import logging

import raster_app_factory
import raster_main_compat_exports as _compat_exports
import raster_main_runtime as _runtime_exports
import raster_settings
import raster_stac_runtime

globals().update({name: getattr(_compat_exports, name) for name in _compat_exports.__all__})
globals().update({name: getattr(_runtime_exports, name) for name in _runtime_exports.__all__})


def __getattr__(name: str):
    if name in _compat_exports.__all__:
        return getattr(_compat_exports, name)
    if name in _runtime_exports.__all__:
        return getattr(_runtime_exports, name)
    raise AttributeError(name)


def __dir__():
    return sorted(set(globals()) | set(_compat_exports.__all__) | set(_runtime_exports.__all__))


try:
    from shared.logging_config import setup_logging

    logger = setup_logging("raster-service")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","svc":"raster-service","msg":"%(message)s"}',
    )
    logger = logging.getLogger("raster-service")

CORS_ORIGINS = raster_settings.CORS_ORIGINS
EARTH_SEARCH_URL = raster_settings.EARTH_SEARCH_URL
HTTP_TIMEOUT = raster_settings.HTTP_TIMEOUT
TITILER_URL = raster_settings.TITILER_URL

_stac = raster_stac_runtime.configure_stac_search(logger=logger)
lifespan = _runtime_exports.make_raster_lifespan(logger=logger)

app = raster_app_factory.create_raster_app(
    title="SAHOOL Raster Service",
    version="9.2.0",
    lifespan=lifespan,
    cors_origins=CORS_ORIGINS,
)


# Runtime identity is read from a build-time generated, read-only image file.
# Mutable runtime environment values are deliberately not trusted.
@app.get("/runtime-identity", include_in_schema=True)
def runtime_evidence_identity():
    from shared.runtime_identity import load_build_identity

    return load_build_identity("raster-service")
