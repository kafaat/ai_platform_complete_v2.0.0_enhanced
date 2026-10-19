"""Bounded TiTiler transport for COGs selected by a tenant-authorized registry.

Callers must authorize the record before calling this adapter. A browser supplies
a record id and tile coordinates, never an upstream URL. Only explicitly trusted
public HTTPS source hosts may be read; private object-store access needs a separate
object-ownership contract and is deliberately not inferred from a bucket name.
"""

from __future__ import annotations

import os
import re
import struct
import zlib
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from shared.gis.cog_display_policy import validate_rescale

MAX_TILE_BYTES = 2 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_TILE_EDGE = 1024


def _validate_png_header(content: bytes | bytearray) -> None:
    """Bound the advertised pixel buffer without decompressing an upstream PNG.

    A 1024-square RGBA16 image is at most 8 MiB of sample data. This is
    header validation, not a complete PNG decoder or a bound on TiTiler's
    upstream COG reads. The request uses the ordinary 256-pixel tile endpoint.
    """
    if (
        len(content) < 33
        or content[:8] != PNG_SIGNATURE
        or content[8:16] != b"\x00\x00\x00\x0dIHDR"
    ):
        raise HTTPException(502, "cog_tile_backend_not_png")
    width, height, depth, color, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", content[16:29]
    )
    depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
    if (
        depth not in depths.get(color, set())
        or compression != 0
        or filtering != 0
        or interlace not in {0, 1}
        or zlib.crc32(content[12:29]) != struct.unpack(">I", content[29:33])[0]
    ):
        raise HTTPException(502, "cog_tile_backend_not_png")
    if not (0 < width <= MAX_TILE_EDGE and 0 < height <= MAX_TILE_EDGE):
        raise HTTPException(502, "cog_tile_backend_invalid_dimensions")


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
        params["rescale"] = validate_rescale(rescale)
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
                header_checked = False
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_TILE_BYTES:
                        raise HTTPException(502, "cog_tile_backend_response_too_large")
                    if len(content) >= 33 and not header_checked:
                        _validate_png_header(content)
                        header_checked = True
    except httpx.HTTPError:
        raise HTTPException(502, "cog_tile_backend_unavailable") from None
    if not header_checked:
        _validate_png_header(content)
    return bytes(content)
