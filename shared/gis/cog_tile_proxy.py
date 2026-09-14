"""Bounded TiTiler transport for COGs selected by a tenant-authorized registry.

Callers must authorize the record before calling this adapter. A browser supplies
a record id and tile coordinates, never an upstream URL. Only explicitly trusted
public HTTPS source hosts may be read; private object-store access needs a separate
object-ownership contract and is deliberately not inferred from a bucket name.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

MAX_TILE_BYTES = 2 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


async def fetch_registered_cog_tile(
    cog_url: str,
    z: int,
    x: int,
    y: int,
    *,
    base_url: str,
    colormap: str | None = None,
    rescale: str | None = None,
) -> bytes:
    """Fetch one PNG after the caller has resolved and authorized its COG record."""
    if not 0 <= z <= 22 or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(422, "invalid_tile_coordinates")
    allowed = {
        host.strip().lower()
        for host in os.getenv("COG_TILE_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    }
    if not base_url or not allowed:
        raise HTTPException(503, "cog_tile_backend_not_configured")
    try:
        source = urlsplit(cog_url)
        backend = urlsplit(base_url)
        source_ok = (
            source.scheme == "https"
            and source.hostname in allowed
            and source.port in (None, 443)
            and not source.username
            and not source.password
            and not source.fragment
        )
        backend_ok = (
            backend.scheme in {"http", "https"}
            and bool(backend.hostname)
            and not backend.username
            and not backend.password
            and not backend.query
            and not backend.fragment
        )
    except ValueError:
        raise HTTPException(422, "invalid_cog_tile_url") from None
    if not source_ok:
        raise HTTPException(422, "cog_tile_source_not_allowed")
    if not backend_ok:
        raise HTTPException(503, "cog_tile_backend_not_configured")
    params = {"url": cog_url}
    if colormap is not None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", colormap):
            raise HTTPException(422, "invalid_tile_colormap")
        params["colormap_name"] = colormap
    if rescale is not None:
        if not re.fullmatch(r"-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?", rescale):
            raise HTTPException(422, "invalid_tile_rescale")
        params["rescale"] = rescale
    url = f"{base_url.rstrip('/')}/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png"
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=3), trust_env=False, follow_redirects=False
        ) as client:
            async with client.stream("GET", url, params=params) as response:
                if response.status_code != 200:
                    raise HTTPException(502, "cog_tile_backend_failed")
                if response.headers.get("content-type", "").split(";", 1)[0] != "image/png":
                    raise HTTPException(502, "cog_tile_backend_not_png")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_TILE_BYTES:
                        raise HTTPException(502, "cog_tile_backend_response_too_large")
    except httpx.HTTPError:
        raise HTTPException(502, "cog_tile_backend_unavailable") from None
    if not content.startswith(PNG_SIGNATURE):
        raise HTTPException(502, "cog_tile_backend_not_png")
    return bytes(content)
