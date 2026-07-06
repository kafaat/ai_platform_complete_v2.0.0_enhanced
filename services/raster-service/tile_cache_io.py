"""Small on-disk tile-cache IO helpers.

The path layout remains controlled by ``main.py`` through UPLOAD_DIR and cache key
inputs. This module deliberately contains no FastAPI or raster state.
"""

from __future__ import annotations

import os
from collections.abc import Callable


def tile_cache_key(
    upload_dir: str,
    safe_segment: Callable[[str | None], str],
    field_id: str,
    index: str,
    date: str,
    z: int,
    x: int,
    y: int,
    tenant_id: str | None,
    v: str | None = None,
) -> str:
    safe = safe_segment
    return os.path.join(
        upload_dir,
        "tile_cache",
        safe(tenant_id),
        safe(field_id),
        safe(index),
        safe(date),
        safe(v or "default"),
        str(z),
        f"{x}_{y}.png",
    )


def read_tile_cache(path: str, *, enabled: bool = True) -> bytes | None:
    if not enabled:
        return None
    try:
        if os.path.exists(path):
            with open(path, "rb") as fh:
                return fh.read()
    except OSError:
        return None
    return None


def write_tile_cache(path: str, data: bytes, *, enabled: bool = True) -> None:
    if not enabled or not data:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except OSError:
        return
