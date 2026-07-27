"""Immutable build identity reader for runtime evidence.

The metadata file is created during the container image build. Runtime environment
variables are intentionally ignored so a deployer cannot relabel an old image by
injecting a desired Git SHA or build identifier.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

BUILD_METADATA_PATH = Path("/app/.sahool-build-metadata.json")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_BUILD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class BuildIdentityError(RuntimeError):
    pass


@lru_cache(maxsize=8)
def load_build_identity(
    service: str, metadata_path: str | Path = BUILD_METADATA_PATH
) -> dict[str, Any]:
    path = Path(metadata_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise BuildIdentityError(f"immutable build metadata unavailable: {exc}") from exc
    if not isinstance(raw, dict):
        raise BuildIdentityError("immutable build metadata must be an object")
    if raw.get("service") != service:
        raise BuildIdentityError("immutable build metadata service mismatch")
    git_sha = raw.get("git_sha")
    build_id = raw.get("build_id")
    if not isinstance(git_sha, str) or not _SHA_RE.fullmatch(git_sha):
        raise BuildIdentityError("immutable git_sha must be 40 lowercase hex characters")
    if not isinstance(build_id, str) or not _BUILD_ID_RE.fullmatch(build_id):
        raise BuildIdentityError("immutable build_id has invalid format")
    return {
        "service": service,
        "git_sha": git_sha,
        "build_id": build_id,
        "source_repository": str(raw.get("source_repository") or ""),
        "source_ref": str(raw.get("source_ref") or ""),
        "metadata_source": "immutable-image-file",
    }
